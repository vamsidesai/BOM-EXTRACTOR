"""Load drawings into page images plus, where the file carries it, exact text.

Supported inputs
  * PDF  - digital (vector text layer), digital with vectorised (SHX) text,
           and scanned (image-only) pages, in any mix within one file
  * DXF  - native CAD text, or raster-to-vector traced drawings (OCR)
  * DWG  - converted to DXF in memory, then as DXF
  * TIFF (multi-page) / PNG / JPG / BMP / WEBP scans
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import numpy as np
from PIL import Image, ImageSequence

from .models import Word

PDF_EXT = {".pdf"}
IMAGE_EXT = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".webp"}
CAD_EXT = {".dxf", ".dwg"}
SUPPORTED_EXT = PDF_EXT | IMAGE_EXT | CAD_EXT

Image.MAX_IMAGE_PIXELS = None  # engineering sheets are legitimately huge


def sniff_format(path: str | Path) -> str:
    """Identify drawing file format from magic bytes and content, falling back to extension."""
    import re
    p = Path(path)
    try:
        with open(p, "rb") as f:
            header = f.read(512)
    except Exception:
        header = b""

    # PDF: %PDF-
    if header.startswith(b"%PDF-"):
        return "pdf"

    # DWG: AC10xx or MC0.0
    if header.startswith((b"AC10", b"MC0.0", b"AUTOCAD")):
        return "dwg"

    # DXF: ASCII starts with 0\nSECTION or binary DXF marker
    if header.startswith(b"AutoCAD Binary DXF") or b"SECTION" in header[:128] or b"HEADER" in header[:128]:
        return "dxf"

    # Images
    if header.startswith(b"\x89PNG"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return "tif"
    if header.startswith(b"BM"):
        return "bmp"
    if header.startswith(b"RIFF") and b"WEBP" in header[:16]:
        return "webp"

    # Fallback to extension
    ext = p.suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext == ".dwg":
        return "dwg"
    if ext == ".dxf":
        return "dxf"
    if ext in {".tif", ".tiff"}:
        return "tif"
    if ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
        return ext.lstrip(".")

    try:
        text_head = header.decode("latin1", errors="ignore")
        if re.search(r"^\s*0\s+SECTION", text_head, re.MULTILINE):
            return "dxf"
    except Exception:
        pass

    return "unknown"


@dataclass
class RawPage:
    index: int
    image: np.ndarray  # BGR uint8
    dpi: float
    native_words: Optional[list[Word]] = None  # exact text (digital PDF / CAD)
    notes: list[str] = field(default_factory=list)
    kind: str = ""  # pdf-vector | pdf-scan | pdf-outlined-text | image | dxf | dwg (+ "-traced")
    label: str = ""  # e.g. CAD layout name
    cad_fields: dict = field(default_factory=dict)  # title-block attributes from CAD blocks


def iter_pages(path: str | Path, dpi: int = 300, max_pixels: int = 80_000_000,
               force_ocr: bool = False, native_min_words: int = 15,
               cfg: Optional[dict] = None) -> Iterator[RawPage]:
    path = Path(path)
    ext = path.suffix.lower()
    fmt = sniff_format(path)
    if ext in PDF_EXT or fmt == "pdf":
        yield from _iter_pdf(path, dpi, max_pixels, force_ocr, native_min_words)
    elif ext in IMAGE_EXT or fmt in {"png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"}:
        yield from _iter_image(path, dpi, max_pixels)
    elif ext in CAD_EXT or fmt in {"dxf", "dwg"}:
        from .cad import iter_cad_pages
        yield from iter_cad_pages(path, dpi, max_pixels, force_ocr, native_min_words, cfg or {})
    else:
        raise ValueError(f"Unsupported file type: {path.suffix or fmt}")


# --------------------------------------------------------------------- PDF

def _iter_pdf(path, dpi, max_pixels, force_ocr, native_min_words):
    import pymupdf

    doc = pymupdf.open(str(path))
    try:
        if doc.needs_pass:
            if not doc.authenticate(""):
                raise ValueError("PDF is password protected")
        for i, page in enumerate(doc):
            notes: list[str] = []
            words, zoom_words = _pdf_words(page) if not force_ocr else ([], 1.0)
            meaningful = [w for w in words if any(c.isalnum() for c in w.text)]
            has_text = len(meaningful) >= native_min_words
            if has_text and not force_ocr:
                alpha = sum(c.isalpha() for w in meaningful for c in w.text)
                tot = max(1, sum(len(w.text) for w in meaningful))
                if alpha / tot < 0.20 and len(meaningful) < 40:
                    has_text = False
                    notes.append("PDF text layer appears degraded/noisy - using OCR")

            scan_dpi = None if has_text else _scan_resolution(page)
            if scan_dpi is not None:
                # Image-only page: render at the scan's own resolution (no
                # resampling blur) and judge scale from the lettering, exactly
                # as for a TIFF/PNG. The PDF page size of a scan often says
                # nothing about the drawing's real size.
                render = min(float(scan_dpi), 600.0)
                img = _render_pdf(page, render, max_pixels, notes)
                rgb = img[:, :, ::-1]
                img, eff_dpi = _normalise_raster(rgb, scan_dpi, dpi, max_pixels, notes,
                                                 already_capped=True)
                yield RawPage(i, img, eff_dpi, None, notes, kind="pdf-scan")
                continue

            w_in, h_in = page.rect.width / 72, page.rect.height / 72
            eff_dpi = _cap_dpi(dpi, w_in, h_in, max_pixels)
            if eff_dpi < dpi:
                notes.append(f"render DPI reduced to {eff_dpi:.0f} to respect max_pixels")
            img = _render_pdf(page, eff_dpi, max_pixels, notes)
            zoom = eff_dpi / 72
            if has_text:
                native = [Word(w.text, w.x0 * zoom, w.y0 * zoom, w.x1 * zoom, w.y1 * zoom, 1.0)
                          for w in words]
                yield RawPage(i, img, eff_dpi, native, notes, kind="pdf-vector")
            else:
                if words and not force_ocr:
                    notes.append(f"only {len(meaningful)} text objects in PDF layer "
                                 "(text may be vectorised) - using OCR")
                yield RawPage(i, img, eff_dpi, None, notes,
                              kind="pdf-outlined-text" if not force_ocr else "pdf-vector")
    finally:
        doc.close()


def _pdf_words(page):
    import pymupdf
    raw = page.get_text("words")
    rot = page.rotation_matrix
    words = []
    for x0, y0, x1, y1, txt, *_ in raw:
        txt = txt.strip()
        if not txt:
            continue
        r = pymupdf.Rect(x0, y0, x1, y1) * rot  # unrotated -> displayed coords (points)
        bx0, bx1 = min(r.x0, r.x1), max(r.x0, r.x1)
        by0, by1 = min(r.y0, r.y1), max(r.y0, r.y1)
        words.append(Word(txt, bx0, by0, bx1, by1, 1.0))
    return words, 1.0


def _scan_resolution(page) -> Optional[float]:
    """If the page is essentially one raster image (a scan), return that
    image's resolution in pixels per inch of the page; else None."""
    page_area = abs(page.rect)
    if page_area <= 0:
        return None
    best_area, best_dpi = 0.0, None
    try:
        infos = page.get_image_info()
    except Exception:
        return None
    for info in infos:
        bbox = info.get("bbox")
        w, h = info.get("width") or 0, info.get("height") or 0
        if not bbox or not w or not h:
            continue
        x0, y0, x1, y1 = bbox
        bw, bh = abs(x1 - x0), abs(y1 - y0)
        area = bw * bh
        if area <= best_area or bw < 1 or bh < 1:
            continue
        # images may be rotated on the page: compare the long sides
        res = max(w, h) / (max(bw, bh) / 72)
        best_area, best_dpi = area, res
    if best_dpi is None or best_area < 0.5 * page_area:
        return None
    # A digital drawing with a small logo is not a scan; a scan with a few
    # vector annotations still is.
    try:
        n_vec = len(page.get_drawings())
    except Exception:
        n_vec = 0
    if n_vec > 200:
        return None
    return float(best_dpi)


def _render_pdf(page, dpi, max_pixels, notes):
    import pymupdf
    w_in, h_in = page.rect.width / 72, page.rect.height / 72
    d = _cap_dpi(dpi, w_in, h_in, max_pixels)
    if d < dpi - 0.5 and not any("max_pixels" in n for n in notes):
        notes.append(f"render DPI reduced to {d:.0f} to respect max_pixels")
    zoom = d / 72
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False, colorspace=pymupdf.csRGB)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return img[:, :, ::-1].copy()  # RGB -> BGR


# ------------------------------------------------------------------ images

def _iter_image(path, dpi, max_pixels):
    with Image.open(str(path)) as im:
        for i, frame in enumerate(ImageSequence.Iterator(im)):
            notes: list[str] = []
            info_dpi = frame.info.get("dpi")
            src_dpi = float(info_dpi[0]) if info_dpi and info_dpi[0] and info_dpi[0] > 30 else None
            rgb = np.asarray(frame.convert("RGB"))
            arr, eff = _normalise_raster(rgb, src_dpi, dpi, max_pixels, notes)
            yield RawPage(i, arr, eff, None, notes, kind="image")


def _normalise_raster(rgb: np.ndarray, src_dpi: Optional[float], dpi: int, max_pixels: int,
                      notes: list[str], already_capped: bool = False) -> tuple[np.ndarray, float]:
    """Decide the effective resolution of a raster drawing and cap its size.
    72/96 dpi (or none) is a screen value, not the drawing's scale: measure the
    lettering instead. Also catch metadata that is far off."""
    from .imaging import estimate_dpi_from_text
    import cv2
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    est = estimate_dpi_from_text(gray)
    if src_dpi is None or src_dpi < 150 or (est and not 0.5 <= est / src_dpi <= 2.0):
        if est:
            if src_dpi:
                notes.append(f"image resolution {src_dpi:.0f} dpi does not match the lettering "
                             f"size - using estimated {est:.0f} dpi")
            src_dpi = est
        elif src_dpi is None:
            src_dpi = float(dpi)
            notes.append(f"image has no DPI metadata - assuming {dpi}")
    h, w = rgb.shape[:2]
    if w * h > max_pixels:
        s = (max_pixels / (w * h)) ** 0.5
        rgb = cv2.resize(rgb, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        src_dpi *= s
        notes.append("image downscaled to respect max_pixels")
    return np.ascontiguousarray(rgb[:, :, ::-1]), float(src_dpi)


def _cap_dpi(dpi, w_in, h_in, max_pixels):
    px = (w_in * dpi) * (h_in * dpi)
    if px <= max_pixels:
        return float(dpi)
    return float((max_pixels / (w_in * h_in)) ** 0.5)


def discover_inputs(paths: list[str], recursive: bool = True) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            it = pp.rglob("*") if recursive else pp.glob("*")
            out.extend(sorted(f for f in it if f.is_file() and f.suffix.lower() in SUPPORTED_EXT))
        elif pp.is_file():
            out.append(pp)
        else:
            raise FileNotFoundError(p)
    # de-duplicate, keep order
    seen, uniq = set(), []
    for f in out:
        k = f.resolve()
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq
