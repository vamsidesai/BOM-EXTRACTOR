"""2D CAD drawings (DXF, DWG).

A CAD file is turned into the same thing the rest of bomx works on: a page
image plus a list of words with pixel boxes. The difference from a scan is
that the words come straight from the CAD text entities (TEXT, MTEXT,
block attributes, dimension text, tables, text seen through paper-space
viewports), so they are exact - no OCR, confidence 1.0.

How a layout becomes a page
  1. ezdxf's drawing frontend decomposes every entity (blocks, dimensions,
     hatches, MTEXT layout, viewports, linetypes) into primitives.
  2. A hook on its text stage records each text run with the transform the
     renderer used, so word boxes match the rendered glyphs exactly.
  3. The primitives are rasterised here with OpenCV at a resolution chosen
     from the drawing's own lettering, so table rules and cells come out the
     same as on a 300 dpi scan whatever units the CAD file uses.

Drawings without text entities
  Legacy drawings are often raster scans traced to vectors: every letter and
  line is a closed outline polyline. These are detected, rendered *filled*
  (even-odd, so letter counters stay open) and passed to OCR like a scan,
  but from a clean, sharp, upscaled vector render.

DWG
  DWG is converted to an in-memory DXF document by the first available of
    * ODA File Converter (free, best fidelity)       - via ezdxf.addons.odafc
    * LibreDWG ``dwgread`` (free, open source)        - via its JSON output
    * aspose-cad (commercial; render-only fallback)   - image then OCR
"""
from __future__ import annotations

import glob
import json
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import cv2
import numpy as np

from .models import Word

log = logging.getLogger(__name__)

TEXT_ENTITIES = {"TEXT", "MTEXT", "ATTRIB", "DIMENSION", "ARC_DIMENSION", "LARGE_RADIAL_DIMENSION",
                 "ACAD_TABLE", "MULTILEADER", "MLEADER", "TOLERANCE", "ATTDEF"}
_PAD_PX = 24


class CadError(RuntimeError):
    pass


@dataclass
class _Text:
    text: str
    pts: np.ndarray  # 4x2 corners in layout units (after viewport transform)
    angle: float  # reading direction, degrees


# ====================================================================== loading

def load_document(path: Path, cfg: dict):
    """Return (ezdxf document or None, kind, notes, raster_fallback_image)."""
    ext = path.suffix.lower()
    if ext == ".dxf":
        doc, notes = _read_dxf(path)
        return doc, "dxf", notes, None
    if ext == ".dwg":
        return _read_dwg(path, cfg)
    raise CadError(f"not a CAD file: {path.name}")


def _read_dxf(path: Path):
    import ezdxf
    from ezdxf import recover
    notes: list[str] = []
    try:
        doc = ezdxf.readfile(str(path))
    except IOError as e:
        raise CadError(f"cannot read DXF: {e}") from e
    except Exception as e:  # structure errors: let the recover module repair what it can
        try:
            doc, auditor = recover.readfile(str(path))
        except Exception as e2:
            raise CadError(f"DXF file is damaged and could not be recovered: {e2}") from e
        notes.append(f"DXF structure errors repaired while loading ({len(auditor.fixes)} fixes)")
    return doc, notes


# ------------------------------------------------------------------ DWG

def dwg_backends(cfg: dict | None = None) -> dict[str, Optional[str]]:
    """Which DWG converters are available: name -> location (or None)."""
    cfg = cfg or {}
    return {"oda": _find_oda(cfg), "libredwg": _find_dwgread(cfg), "aspose": _find_aspose()}


def _find_oda(cfg: dict) -> Optional[str]:
    cand = []
    if cfg.get("oda_converter"):
        cand.append(str(cfg["oda_converter"]))
    w = shutil.which("ODAFileConverter")
    if w:
        cand.append(w)
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.environ.get("LOCALAPPDATA", ""),
                     str(Path.home() / "AppData" / "Local" / "Programs")):
            if base:
                cand += sorted(glob.glob(os.path.join(base, "ODA", "ODAFileConverter*",
                                                      "ODAFileConverter.exe")), reverse=True)
                cand += sorted(glob.glob(os.path.join(base, "ODAFileConverter*",
                                                      "ODAFileConverter.exe")), reverse=True)
    else:
        cand += ["/usr/bin/ODAFileConverter", "/usr/local/bin/ODAFileConverter"]
        cand += sorted(glob.glob("/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"))
    for c in cand:
        if c and Path(c).is_file():
            return c
    return None


def _find_dwgread(cfg: dict) -> Optional[str]:
    exe = "dwgread.exe" if os.name == "nt" else "dwgread"
    cand = []
    if cfg.get("libredwg_path"):
        p = Path(cfg["libredwg_path"])
        cand += [p, p / exe, p / "bin" / exe]
    w = shutil.which("dwgread")
    if w:
        cand.append(Path(w))
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.environ.get("LOCALAPPDATA", ""),
                     str(Path.home() / "AppData" / "Local" / "Programs"),
                     str(Path.home() / "Downloads")):
            if base and Path(base).is_dir():
                cand += [Path(base) / "LibreDWG" / exe, Path(base) / "libredwg" / exe,
                         Path(base) / "LibreDWG" / "bin" / exe, Path(base) / "libredwg" / "bin" / exe]
                cand += [Path(p) for p in glob.glob(os.path.join(base, "libredwg*", exe))]
                cand += [Path(p) for p in glob.glob(os.path.join(base, "libredwg*", "bin", exe))]
    for c in cand:
        if c.is_file():
            return str(c)
    return None


def _find_aspose() -> Optional[str]:
    try:
        import importlib.util
        return "aspose-cad" if importlib.util.find_spec("aspose.cad") else None
    except (ImportError, ValueError):
        return None


def _read_dwg(path: Path, cfg: dict):
    order = cfg.get("dwg_converter", "auto")
    order = ["oda", "libredwg", "aspose"] if order in (None, "", "auto") else [order]
    avail = dwg_backends(cfg)
    errors = []
    for name in order:
        loc = avail.get(name)
        if not loc:
            continue
        try:
            if name == "oda":
                return _dwg_via_oda(path, loc), "dwg", [f"DWG converted with ODA File Converter"], None
            if name == "libredwg":
                doc, notes = _dwg_via_libredwg(path, loc, cfg)
                return doc, "dwg", ["DWG read with LibreDWG"] + notes, None
            if name == "aspose":
                doc, notes_asp, img = _dwg_via_aspose(path)
                if doc is not None:
                    return doc, "dwg", ["DWG converted via aspose-cad (vector/text)"] + notes_asp, None
                return None, "dwg", ["DWG rendered with aspose-cad (no CAD text available - OCR used)"], img
        except Exception as e:  # try the next converter
            log.warning("DWG converter %s failed on %s: %s", name, path.name, e)
            errors.append(f"{name}: {e}")
    if errors:
        raise CadError("could not read DWG - " + "; ".join(errors))
    raise CadError(
        "no DWG converter found. Install one of: ODA File Converter (free, "
        "https://www.opendesign.com/guestfiles/oda_file_converter) or LibreDWG "
        "(free, https://github.com/LibreDWG/libredwg/releases - put dwgread on PATH "
        "or set libredwg_path). Alternatively save the drawing as DXF from your CAD program.")


def _dwg_via_oda(path: Path, exe: str):
    import ezdxf
    from ezdxf.addons import odafc
    key = "win_exec_path" if os.name == "nt" else "unix_exec_path"
    ezdxf.options.set("odafc-addon", key, exe)
    return odafc.readfile(str(path))


def _run_dwgread(exe: str, fmt: str, src: Path, out: Path, timeout: int) -> Optional[str]:
    """Run dwgread; return an error string or None."""
    try:
        proc = subprocess.run([exe, "-O", fmt, "-o", str(out), str(src)], capture_output=True,
                              timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return f"dwgread {fmt} timed out after {timeout}s"
    except OSError as e:
        return f"dwgread could not run: {e}"
    if not out.exists() or out.stat().st_size == 0:
        err = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-2:]
        return f"dwgread {fmt} produced no output " + " | ".join(err)
    return None


def _dwg_via_libredwg(path: Path, exe: str, cfg: dict):
    """DXF output for text/names, JSON output to restore dropped geometry
    (see dwgjson.py for why both are needed)."""
    import ezdxf
    from ezdxf import recover
    from .dwgjson import load_json, supplement
    notes: list[str] = []
    timeout = int(cfg.get("cad_timeout", 600))
    with tempfile.TemporaryDirectory(prefix="bomx_dwg_") as td:
        src = Path(td) / "in.dwg"  # plain ASCII path: dwgread on Windows dislikes some names
        shutil.copyfile(path, src)
        dxf, js = Path(td) / "out.dxf", Path(td) / "out.json"
        err_dxf = _run_dwgread(exe, "DXF", src, dxf, timeout)
        doc = None
        if err_dxf is None:
            try:
                doc, auditor = recover.readfile(str(dxf))
            except Exception as e:
                err_dxf = f"converted DXF unreadable: {e}"
        err_js = _run_dwgread(exe, "JSON", src, js, timeout)
        data = None
        if err_js is None:
            try:
                data = load_json(js.read_bytes())
            except Exception as e:
                err_js = f"JSON unreadable: {e}"
    if doc is None and data is None:
        raise CadError(f"{err_dxf}; {err_js}")
    if doc is None:
        doc = ezdxf.new("R2010")
        notes.append("LibreDWG DXF conversion failed - geometry only, CAD text unavailable")
    if data is not None:
        st = supplement(doc, data)
        if st["added"]:
            notes.append(f"LibreDWG DXF conversion dropped {st['added']} of {st['json_entities']} "
                         "entities - restored from its JSON dump")
        if st["text_lost"]:
            notes.append(f"{st['text_lost']} text entities could not be recovered from the DWG")
    else:
        notes.append(f"LibreDWG JSON dump unavailable ({err_js}); completeness not verified")
    return doc, notes


def _dwg_via_aspose(path: Path) -> tuple[Any, list[str], Optional[np.ndarray]]:
    import io
    import aspose.cad as cad
    from aspose.cad import Image as CadImage
    from aspose.cad.imageoptions import CadRasterizationOptions, PngOptions
    import ezdxf
    from ezdxf import recover
    img = CadImage.load(str(path))
    doc = None
    notes = []
    try:
        try:
            dxf_opts_cls = getattr(cad.imageoptions, "DxfOptions", None)
            if dxf_opts_cls is not None:
                dxf_buf = io.BytesIO()
                img.save(dxf_buf, dxf_opts_cls())
                raw_bytes = dxf_buf.getvalue()
                if raw_bytes and len(raw_bytes) > 100:
                    doc, _ = recover.read(raw_bytes)
                    notes.append("DXF vector/text entities exported via aspose-cad")
        except Exception as e:
            log.debug("aspose DXF vector export skipped: %s", e)

        w = float(img.width) if img.width > 0 else 2400.0
        h = float(img.height) if img.height > 0 else 1800.0
        tw = 7000.0
        opts = CadRasterizationOptions()
        opts.page_width, opts.page_height = tw, tw * h / w
        opts.background_color = cad.Color.white
        opts.draw_type = cad.imageoptions.CadDrawTypeMode.USE_OBJECT_COLOR
        png = PngOptions()
        png.vector_rasterization_options = opts
        buf = io.BytesIO()
        img.save(buf, png)
    finally:
        img.close()
    arr = cv2.imdecode(np.frombuffer(buf.getvalue(), np.uint8), cv2.IMREAD_COLOR)
    if doc is not None:
        return doc, notes, arr
    if arr is None:
        raise CadError("aspose-cad returned no image")
    return None, notes, arr


# ====================================================================== pages

def iter_cad_pages(path: Path, dpi: int, max_pixels: int, force_ocr: bool,
                   native_min_words: int, cfg: dict) -> Iterator:
    from .ingest import RawPage, _normalise_raster
    path = Path(path)
    doc, kind, notes, raster = load_document(path, cfg)
    if doc is None:  # render-only converter
        n = list(notes)
        img, eff = _normalise_raster(raster[:, :, ::-1], None, dpi, max_pixels, n)
        yield RawPage(0, img, eff, None, n, kind=f"{kind}-raster")
        return

    layouts = select_layouts(doc, cfg.get("cad_layouts", "auto"))
    if not layouts:
        raise CadError("drawing contains no visible entities")
    for i, layout in enumerate(layouts):
        page_notes = list(notes) if i == 0 else []
        img, ppi, words, traced, fields, extra = render_layout(
            doc, layout, dpi, max_pixels, cfg)
        page_notes += extra
        if len(layouts) > 1 or not layout.is_modelspace:
            page_notes.append(f"layout '{layout.name}'")
        meaningful = [w for w in words if any(c.isalnum() for c in w.text)]
        native = None
        if not force_ocr and not traced and len(meaningful) >= native_min_words:
            native = words
        elif traced:
            page_notes.append("no CAD text entities - drawing is traced vector outlines; "
                              "rendered filled and read with OCR")
        elif not force_ocr:
            page_notes.append(f"only {len(meaningful)} CAD text entities (text may be exploded "
                              "to lines) - using OCR supplemented with native CAD text")
        k = kind + ("-traced" if traced else "")
        # Pass words as native_words even if falling back to OCR, so remaining native CAD text isn't lost
        yield RawPage(i, img, ppi, native if native is not None else (words if words else None),
                      page_notes, kind=k, label=layout.name, cad_fields=fields)


def select_layouts(doc, mode: str = "auto") -> list:
    """Model space, paper-space layouts, or both.
    In 'auto' mode, evaluates entity counts and textual content to select
    the layout(s) actually containing drawing data (BOM, title block, geometry),
    avoiding empty/default paper-space templates."""
    msp = doc.modelspace()
    has_model = len(msp) > 0

    def _content_weight(lay) -> tuple[int, int]:
        n_text = sum(1 for e in lay if e.dxftype() in TEXT_ENTITIES or (e.dxftype() == "INSERT" and getattr(e, "attribs", None)))
        n_tot = sum(1 for e in lay if e.dxftype() != "VIEWPORT")
        return n_text, n_tot

    msp_text, msp_tot = _content_weight(msp) if has_model else (0, 0)

    papers = []
    active_tab = getattr(doc.header, "get", lambda k, d=None: None)("$CTAB") if hasattr(doc, "header") else None

    for name in doc.layouts.names_in_taborder():
        lay = doc.layouts.get(name)
        if lay.is_modelspace:
            continue
        p_text, p_tot = _content_weight(lay)
        vps = [e for e in lay if e.dxftype() == "VIEWPORT" and e.dxf.get("status", 1) not in (0,)]
        shows_model = len(vps) > 1 and has_model
        # Ignore empty default paper-space layouts when model space has significant text/content
        if p_text > 0 or (p_tot >= 5 and (not has_model or msp_tot < 10)) or (shows_model and p_tot > 0):
            papers.append(lay)

    if mode == "model":
        return [msp] if has_model else []
    if mode == "paper":
        return papers
    if mode == "all":
        return ([msp] if has_model else []) + papers

    # 'auto' mode:
    # If active tab was explicitly set to Model and model space has substantial content, prefer model space
    if active_tab == "Model" and msp_text > 0:
        return [msp]

    # If paper layouts were found, verify they aren't dummy templates compared to model space
    if papers:
        total_paper_text = sum(_content_weight(lay)[0] for lay in papers)
        if total_paper_text == 0 and msp_text >= 5:
            return [msp]
        return papers

    return [msp] if has_model else []


# ====================================================================== render

def _is_traced(doc, layout) -> bool:
    """True if the layout looks like a raster traced to vectors: no text
    entities at all and the geometry is mostly small closed outlines."""
    spaces = [layout] if layout.is_modelspace else [layout, doc.modelspace()]
    n_text = n_closed = n_curves = 0
    for sp in spaces:
        for e in sp:
            t = e.dxftype()
            if t in TEXT_ENTITIES:
                n_text += 1
            elif t == "INSERT":
                if e.attribs:
                    n_text += 1
                blk = doc.blocks.get(e.dxf.name)
                if blk is not None and any(x.dxftype() in TEXT_ENTITIES for x in blk):
                    n_text += 1
            elif t in ("LWPOLYLINE", "POLYLINE"):
                n_curves += 1
                if e.is_closed:
                    n_closed += 1
            elif t in ("LINE", "ARC", "CIRCLE", "SPLINE", "ELLIPSE"):
                n_curves += 1
                if t in ("CIRCLE",):
                    n_closed += 1
            if n_text:
                return False
    return n_closed >= 50 and n_closed >= 0.6 * max(n_curves, 1)


def render_layout(doc, layout, dpi: int, max_pixels: int, cfg: dict):
    """Rasterise one layout. Returns (BGR image, effective dpi, words,
    traced?, title-block attribute fields, notes)."""
    from ezdxf.addons.drawing import RenderContext
    from ezdxf.addons.drawing.config import (BackgroundPolicy, ColorPolicy, Configuration,
                                             HatchPolicy, LinePolicy, ProxyGraphicPolicy)
    from ezdxf.addons.drawing.frontend import UniversalFrontend
    from ezdxf.addons.drawing.recorder import Recorder

    notes: list[str] = []
    traced = _is_traced(doc, layout)
    rec = Recorder()
    pipe = _capture_pipeline(rec)
    ctx = RenderContext(doc)
    ctx.set_current_layout(layout)
    conf = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.COLOR,
                         proxy_graphic_policy=ProxyGraphicPolicy.SHOW,
                         hatch_policy=HatchPolicy.NORMAL, line_policy=LinePolicy.ACCURATE,
                         hatching_timeout=10.0)
    fe = UniversalFrontend(ctx, pipe, conf)
    try:
        fe.draw_layout(layout, finalize=True)
    except Exception as e:
        log.warning("CAD render of layout %s failed during batch draw: %s; falling back to entity-by-entity rendering", layout.name, e)
        failed_entities = 0
        for entity in layout:
            try:
                fe.draw_entity(entity)
            except Exception:
                failed_entities += 1
        try:
            fe.finalize()
        except Exception:
            pass
        if failed_entities > 0:
            notes.append(f"warning: {failed_entities} entity/entities could not be rendered ({type(e).__name__}) - layout may be incomplete")
        else:
            notes.append(f"layout rendered via entity recovery ({type(e).__name__})")
    player = rec.player()
    records = list(player.recordings())
    if not records and not pipe.texts:
        raise CadError(f"layout '{layout.name}' has nothing to draw")

    x0, y0, x1, y1, dropped = _robust_extents(records, pipe.texts)
    if dropped:
        notes.append(f"{dropped} far-away CAD object(s) left outside the rendered sheet")
    W, H = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)

    # ---- choose pixels per drawing unit
    from .imaging import REF_GLYPH_MM
    if traced:  # outlines of thin rules are slivers: give them pixels to survive
        dpi = max(dpi, int(cfg.get("cad_traced_dpi", 400)))
    target_glyph_px = REF_GLYPH_MM / 25.4 * dpi
    horiz = [t for t in pipe.texts if abs(_wrap(t.angle)) < 5 and t.text.strip()]
    s = None
    if horiz and not traced:
        caps = [_text_height(t) / 1.45 for t in horiz]  # word box -> cap height
        s = target_glyph_px / float(np.median(caps))
    else:
        probe_s = 3000.0 / max(W, H)
        probe = _rasterise(records, x0, y1, probe_s, int(W * probe_s) + 2 * _PAD_PX,
                           int(H * probe_s) + 2 * _PAD_PX, traced, dpi)
        from .imaging import estimate_dpi_from_text
        est = estimate_dpi_from_text(cv2.cvtColor(probe, cv2.COLOR_BGR2GRAY))
        if est:
            s = probe_s * dpi / est
        else:
            notes.append("drawing scale could not be judged from its lettering - "
                         "rendered to a 7000 px long side")
            s = 7000.0 / max(W, H)
    s = min(s, 12000.0 / max(W, H))  # never absurdly large
    s = max(s, 1500.0 / max(W, H))  # nor too small to read
    eff_dpi = float(dpi)
    px = (W * s + 2 * _PAD_PX) * (H * s + 2 * _PAD_PX)
    if px > max_pixels:
        f = (max_pixels / px) ** 0.5
        s *= f
        eff_dpi *= f
        notes.append(f"render resolution reduced to ~{eff_dpi:.0f} dpi to respect max_pixels")
    w_px, h_px = int(math.ceil(W * s)) + 2 * _PAD_PX, int(math.ceil(H * s)) + 2 * _PAD_PX
    img = _rasterise(records, x0, y1, s, w_px, h_px, traced, eff_dpi)

    # ---- words in pixel space
    words: list[Word] = []
    seen = set()
    n_rot = 0
    for t in pipe.texts:
        angle_deg = abs(_wrap(t.angle))
        if angle_deg >= 5:
            n_rot += 1
        xs = (t.pts[:, 0] - x0) * s + _PAD_PX
        ys = (y1 - t.pts[:, 1]) * s + _PAD_PX
        conf = 0.99
        if angle_deg >= 5:
            conf = max(0.88, round(0.98 - 0.08 * (min(angle_deg, 90.0) / 90.0), 3))
        if any(ch in t.text for ch in ("\ufffd", "?")):
            conf = max(0.5, conf - 0.2)
        w = Word(t.text, float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max()), conf)
        key = (w.text, round(w.x0), round(w.y0))
        if key in seen:
            continue
        seen.add(key)
        words.append(w)
    if n_rot:
        notes.append(f"{n_rot} rotated CAD text item(s) (e.g. vertical dimensions/headers) extracted")

    fields = block_attributes(layout, lambda x, y: ((x - x0) * s + _PAD_PX, (y1 - y) * s + _PAD_PX),
                              cfg)
    return img, eff_dpi, words, traced, fields, notes


def _wrap(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def _text_height(t: _Text) -> float:
    a = math.radians(t.angle)
    nx, ny = -math.sin(a), math.cos(a)
    proj = t.pts[:, 0] * nx + t.pts[:, 1] * ny
    return float(proj.max() - proj.min())


def _record_bbox(rec):
    try:
        bb = rec.bbox()
        if not bb.has_data:
            return None
        return bb.extmin.x, bb.extmin.y, bb.extmax.x, bb.extmax.y
    except Exception:
        return None


def _robust_extents(records, texts):
    """Extents of the drawing, ignoring a few far-away strays (a block left at
    the origin, a construction line miles away) that would shrink the sheet."""
    boxes = [b for b in (_record_bbox(r) for r, _ in records) if b]
    boxes += [(t.pts[:, 0].min(), t.pts[:, 1].min(), t.pts[:, 0].max(), t.pts[:, 1].max())
              for t in texts]
    if not boxes:
        raise CadError("nothing to render")
    a = np.array(boxes, dtype=float)
    full = a[:, 0].min(), a[:, 1].min(), a[:, 2].max(), a[:, 3].max()
    if len(a) < 20:
        return (*full, 0)
    cx, cy = (a[:, 0] + a[:, 2]) / 2, (a[:, 1] + a[:, 3]) / 2
    qx0, qx1 = np.quantile(cx, [0.002, 0.998])
    qy0, qy1 = np.quantile(cy, [0.002, 0.998])
    mx, my = (qx1 - qx0) * 0.15 + 1e-9, (qy1 - qy0) * 0.15 + 1e-9
    keep = (a[:, 2] >= qx0 - mx) & (a[:, 0] <= qx1 + mx) & (a[:, 3] >= qy0 - my) & (a[:, 1] <= qy1 + my)
    k = a[keep]
    core = k[:, 0].min(), k[:, 1].min(), k[:, 2].max(), k[:, 3].max()
    fw, fh = full[2] - full[0], full[3] - full[1]
    cw, ch = core[2] - core[0], core[3] - core[1]
    if cw * ch >= 0.5 * fw * fh:  # strays don't matter much: keep everything
        return (*full, 0)
    return (*core, int((~keep).sum()))


# ------------------------------------------------------------------ text capture

def _capture_pipeline(backend):
    from ezdxf.addons.drawing.pipeline import RenderPipeline2d, prepare_string_for_rendering
    from ezdxf.math import Vec2
    from ezdxf.npshapes import NumpyPoints2d

    class CapturePipeline(RenderPipeline2d):
        """Render as usual, and also record every text run with its exact
        placement so words can be given pixel boxes."""

        def __init__(self, be):
            super().__init__(be)
            self.texts: list[_Text] = []

        def draw_text(self, text, transform, properties, cap_height, dxftype="TEXT"):
            super().draw_text(text, transform, properties, cap_height, dxftype)
            try:
                self._capture(text, transform, properties, cap_height, dxftype)
            except Exception as e:  # never let bookkeeping break rendering
                log.debug("text capture failed: %s", e, exc_info=True)

        def _capture(self, text, transform, properties, cap_height, dxftype):
            s = prepare_string_for_rendering(text, dxftype)
            if not s.strip() or cap_height <= 0:
                return
            face = properties.font or self.default_font_face
            eng = self.text_engine
            for m in re.finditer(r"\S+", s):
                xa = eng.get_text_line_width(s[:m.start()], face, cap_height) if m.start() else 0.0
                xb = eng.get_text_line_width(s[:m.end()], face, cap_height)
                if xb <= xa:
                    xb = xa + cap_height * 0.7 * len(m.group())
                lo, hi = -0.3 * cap_height, 1.15 * cap_height
                corners = [(xa, lo), (xb, lo), (xb, hi), (xa, hi)]
                pts = np.array([(v.x, v.y) for v in transform.fast_2d_transform(corners)])
                if self.clipping_portal.is_active:  # inside a paper-space viewport
                    ring = [Vec2(*p) for p in pts] + [Vec2(*pts[0])]
                    parts = self.clipping_portal.clip_polyline(NumpyPoints2d(ring))
                    if not parts:
                        continue  # outside the viewport window
                    allp = np.vstack([p.np_vertices()[:, :2] for p in parts if len(p)])
                    if len(allp) < 2:
                        continue
                    # use the full (transformed) word box; drop words mostly cut off
                    pts = _apply_portal(self.clipping_portal, pts)
                    area_c = np.ptp(allp[:, 0]) * np.ptp(allp[:, 1])
                    area_f = np.ptp(pts[:, 0]) * np.ptp(pts[:, 1])
                    if area_f > 0 and area_c < 0.5 * area_f:
                        continue
                d = pts[1] - pts[0]
                ang = math.degrees(math.atan2(d[1], d[0])) if np.hypot(*d) > 0 else 0.0
                self.texts.append(_Text(_plain(m.group()), pts, ang))

    return CapturePipeline(backend)


def _apply_portal(portal, pts: np.ndarray) -> np.ndarray:
    """Transform points through the active viewport stages (no clipping),
    in the same order ClippingPortal applies them."""
    from ezdxf.math import Vec2
    out = [np.array(pts, dtype=float)]

    def do(stage) -> bool:
        if stage.transform:
            out[0] = np.array([(v.x, v.y) for v in stage.transform.fast_2d_transform(
                [Vec2(*p) for p in out[0]])])
        return True

    portal.foreach_stage(do)
    return out[0]


_SPECIAL = {"%%C": "Ø", "%%c": "Ø", "%%D": "°", "%%d": "°", "%%P": "±", "%%p": "±", "%%%": "%"}


def _plain(s: str) -> str:
    for k, v in _SPECIAL.items():
        s = s.replace(k, v)
    s = re.sub(r"%%[uUoO]", "", s)
    return s.replace("\u2205", "Ø")


# ------------------------------------------------------------------ rasteriser

_SHIFT = 3
_ONE = 1 << _SHIFT


def _rasterise(records, x0, y1, s, w_px, h_px, traced, dpi) -> np.ndarray:
    """Draw recorded primitives (black on white). In traced mode closed
    outlines are filled together with the even-odd rule."""
    img = np.full((h_px, w_px), 255, np.uint8)
    lw = max(1, int(round(dpi / 150)))
    flat = 0.3 / s  # flattening tolerance: 0.3 px

    def P(v: np.ndarray) -> np.ndarray:
        x = (v[:, 0] - x0) * s + _PAD_PX
        y = (y1 - v[:, 1]) * s + _PAD_PX
        return np.round(np.stack([x, y], axis=1) * _ONE).astype(np.int32)

    def ink(props) -> int:
        c = (props.color or "#000000").lstrip("#")[:6]
        return 255 if c.lower() == "ffffff" else 0

    def thick(props) -> int:
        lwmm = props.lineweight or 0.25
        return int(max(lw, min(round(lwmm / 25.4 * dpi), 4 * lw)))

    traced_polys: list[np.ndarray] = []
    for rec, props in records:
        name = type(rec).__name__
        col = ink(props)
        try:
            if name == "PointsRecord":
                v = rec.points.np_vertices()
                if len(v) == 0:
                    continue
                p = P(v)
                if len(v) == 1:
                    cv2.circle(img, tuple(p[0]), lw * _ONE, col, -1, cv2.LINE_8, _SHIFT)
                elif len(v) == 2:
                    cv2.line(img, tuple(p[0]), tuple(p[1]), col, thick(props), cv2.LINE_8, _SHIFT)
                else:
                    cv2.fillPoly(img, [p], col, cv2.LINE_AA, _SHIFT)
            elif name == "SolidLinesRecord":
                v = rec.lines.np_vertices()
                p = P(v)
                t = thick(props)
                for a, b in zip(p[0::2], p[1::2]):
                    cv2.line(img, tuple(a), tuple(b), col, t, cv2.LINE_8, _SHIFT)
            elif name == "PathRecord":
                for sub in _subpaths(rec.path):
                    v = _flatten(sub, flat)
                    if len(v) < 2:
                        continue
                    p = P(v)
                    closed = sub.is_closed or np.allclose(v[0], v[-1])
                    if traced and closed and len(v) >= 3:
                        traced_polys.append(p)
                    else:
                        cv2.polylines(img, [p], closed, col, thick(props), cv2.LINE_8, _SHIFT)
            elif name == "FilledPathsRecord":
                polys = []
                for path in rec.paths:
                    for sub in _subpaths(path):
                        v = _flatten(sub, flat)
                        if len(v) >= 3:
                            polys.append(P(v))
                if polys:
                    cv2.fillPoly(img, polys, col, cv2.LINE_AA, _SHIFT)
            elif name == "ImageRecord":
                _draw_image(img, rec.image_data, x0, y1, s)
        except (cv2.error, ValueError, OverflowError) as e:
            log.debug("skip primitive: %s", e)
    if traced_polys:
        cv2.fillPoly(img, traced_polys, 0, cv2.LINE_AA, _SHIFT)
        # a 1 px edge keeps hairline rules (outlined as sub-pixel slivers) continuous
        cv2.polylines(img, traced_polys, True, 0, 1, cv2.LINE_8, _SHIFT)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def _subpaths(path):
    try:
        return path.sub_paths() if path.has_sub_paths else [path]
    except Exception:
        return [path]


def _flatten(path, dist) -> np.ndarray:
    try:
        if not path.has_curves:
            return path.np_vertices()[:, :2]
        return np.array([(v.x, v.y) for v in path.flattening(dist)], dtype=float)
    except Exception:
        return np.zeros((0, 2))


def _draw_image(img: np.ndarray, data, x0, y1, s):
    """Paste a raster IMAGE entity (common in legacy DWGs: a scan placed in
    model space) onto the page, darkening only."""
    src = data.image
    if src is None or src.size == 0:
        return
    if src.ndim == 3:
        gray = cv2.cvtColor(src[:, :, :3], cv2.COLOR_RGB2GRAY)
        alpha = src[:, :, 3] if src.shape[2] == 4 else None
    else:
        gray, alpha = src, None
    m = data.transform  # image pixel -> layout
    h, w = gray.shape[:2]
    corners = [(0, 0), (w, 0), (0, h)]
    dst = []
    for cx, cy in corners:
        v = m.transform((cx, cy, 0))
        dst.append(((v.x - x0) * s + _PAD_PX, (y1 - v.y) * s + _PAD_PX))
    A = cv2.getAffineTransform(np.float32(corners), np.float32(dst))
    H, W = img.shape
    warped = cv2.warpAffine(gray, A, (W, H), flags=cv2.INTER_AREA, borderValue=255)
    if alpha is not None:
        a = cv2.warpAffine(alpha, A, (W, H), flags=cv2.INTER_NEAREST, borderValue=0)
        warped = np.where(a > 0, warped, 255).astype(np.uint8)
    np.minimum(img, warped, out=img)


# ====================================================================== attributes

_DEFAULT_TAGS = {
    "drawing_number": ["DWGNO", "DWG", "DRGNO", "DRAWINGNO", "DRAWINGNUMBER", "DWGNUMBER", "DOCNO",
                       "DOCUMENTNO", "DOCNUMBER", "DRAWING", "DWGNUM", "NUMBER"],
    "drawing_title": ["TITLE", "DWGTITLE", "DRAWINGTITLE", "TITLE1", "TITLE2", "TITLE3",
                      "TITLELINE1", "TITLELINE2", "TITLELINE3", "DESCRIPTION", "DESC", "PARTNAME"],
    "revision": ["REV", "REVISION", "REVNO", "REVLEVEL", "ISSUE", "CURRENTREV"],
    "drawn_by": ["DRAWN", "DRAWNBY", "DRN", "DRNBY", "AUTHOR", "DESIGNER", "DESIGNEDBY", "CREATEDBY"],
    "checked_by": ["CHECKED", "CHECKEDBY", "CHKD", "CHK", "CHKBY"],
    "approved_by": ["APPROVED", "APPROVEDBY", "APPD", "APPR", "APPBY"],
    "date": ["DATE", "DRAWNDATE", "DRNDATE", "DATEDRAWN", "CREATEDATE"],
    "scale": ["SCALE", "SCL", "DWGSCALE"],
    "sheet": ["SHEET", "SHT", "SHEETNO", "SHEETNUM"],
    "size": ["SIZE", "SHEETSIZE", "PAPERSIZE", "FORMAT"],
    "projection": ["PROJECTION", "PROJ"],
    "material": ["MATERIAL", "MATL", "MAT"],
    "finish": ["FINISH", "SURFACEFINISH", "SURFFINISH", "COATING", "TREATMENT"],
    "heat_treatment": ["HEATTREATMENT", "HEATTREAT", "HT"],
    "weight": ["WEIGHT", "MASS", "WT"],
    "part_number": ["PARTNO", "PARTNUMBER", "PN"],
    "company": ["COMPANY", "CUSTOMER", "CLIENT"],
}


def _norm_tag(t: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (t or "").upper())


def tag_map(cfg: dict) -> dict[str, str]:
    """Attribute tag (normalised) -> title-block field."""
    m: dict[str, str] = {}
    for f, labels in (cfg.get("title_labels") or {}).items():
        for lab in labels:
            m.setdefault(_norm_tag(lab), f)
    for f, tags in {**_DEFAULT_TAGS, **(cfg.get("cad_attribute_tags") or {})}.items():
        for t in tags:
            m[_norm_tag(t)] = f
    return m


def block_attributes(layout, to_px, cfg: dict) -> dict[str, dict]:
    """Title-block fields stored as block attributes (INSERT/ATTRIB), the
    usual way AutoCAD title blocks carry their data. Returns field ->
    {value, tag, bbox}. Multi-line titles (TITLE1, TITLE2 ...) are joined."""
    import ezdxf.bbox
    tm = tag_map(cfg)
    found: dict[str, list] = {}
    for ins in layout.query("INSERT"):
        for att in getattr(ins, "attribs", []):
            try:
                tag = att.dxf.get("tag", "")
                if att.has_embedded_mtext_entity:
                    val = att.virtual_mtext_entity().plain_text()
                else:
                    val = att.dxf.get("text", "")
            except Exception:
                continue
            val = _plain(re.sub(r"\s+", " ", val or "")).strip()
            nt = _norm_tag(tag)
            f = tm.get(nt) or tm.get(re.sub(r"\d+$", "", nt))
            if not f or not val or val in ("-", "--", "?", "XX", "XXX"):
                continue
            bb = None
            try:
                e = ezdxf.bbox.extents([att], fast=True)
                if e.has_data:
                    ax0, ay0 = to_px(e.extmin.x, e.extmax.y)
                    ax1, ay1 = to_px(e.extmax.x, e.extmin.y)
                    bb = tuple(float(v) for v in (min(ax0, ax1), min(ay0, ay1), max(ax0, ax1), max(ay0, ay1)))
            except Exception:
                pass
            found.setdefault(f, []).append((nt, val, bb, tag))
    out = {}
    for f, items in found.items():
        if f == "drawing_title" and len(items) > 1:
            items = sorted(items, key=lambda x: x[0])
            val = " ".join(v for _, v, _, _ in items)
            boxes = [b for _, _, b, _ in items if b]
            bb = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                  max(b[2] for b in boxes), max(b[3] for b in boxes)) if boxes else None
            out[f] = {"value": val, "tag": "+".join(t for *_, t in items), "bbox": bb}
        else:
            _, val, bb, tag = items[0]
            out[f] = {"value": val, "tag": tag, "bbox": bb}
    return out
