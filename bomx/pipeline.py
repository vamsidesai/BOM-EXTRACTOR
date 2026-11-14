"""End-to-end processing of one drawing file."""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Optional

import numpy as np

from . import imaging
from .dimensions import dedupe_dimensions, extract_dimensions_from_words
from .extract import (latest_revision, normalise_title_fields, parse_title_block, table_to_bom,
                      table_to_revisions)
from .ingest import RawPage, iter_pages
from .layout import (Table, assign_words, complete_rows, detect_cells, find_grid_tables, find_notes,
                     find_text_tables, group_cells, split_numbered_notes, text_title_cells,
                     title_block_cells)
from .models import (Dimension, DrawingResult, FieldValue, PageResult, Region, SpecCallout, TextLine,
                     Word, mean_conf, union_bbox)
from .specs import find_specs, summarise
from .textutil import fix_ocr_confusions, group_lines, split_segments

log = logging.getLogger(__name__)
_NUMERIC = re.compile(r"\d+(?:[.,]\d+)?")
_AS_REQ = re.compile(r"^\s*(A/?R|AS\s+REQ\w*|REF|AR)\s*\.?$", re.I)


class PageAnalysis:
    """Everything learned about one page; kept for overlays / debugging."""

    def __init__(self, raw: RawPage):
        self.raw = raw
        self.image: np.ndarray = raw.image
        self.words: list[Word] = []
        self.cells = []
        self.bom_tables: list[Table] = []
        self.rev_tables: list[Table] = []
        self.tb_cells = []
        self.notes_blocks = []
        self.specs: list[SpecCallout] = []
        self.result: Optional[PageResult] = None


def analyse_page(raw: RawPage, cfg: dict) -> PageAnalysis:
    pa = PageAnalysis(raw)
    dpi = raw.dpi
    native = raw.native_words is not None
    img = raw.image
    gray = imaging.to_gray(img)
    rotation, skew = 0, 0.0

    if not native:
        if imaging.tesseract_available() is None:
            raise RuntimeError(
                "OCR needed but Tesseract was not found: this page has no readable text layer "
                "(scanned drawing, or CAD text exported as lines). Install Tesseract OCR "
                "(Windows: 'UB Mannheim Tesseract') or give its path with --tesseract / UI Settings. "
                "Run 'python -m bomx check' to test.")
        if cfg.get("auto_rotate", True):
            rotation = imaging.detect_orientation(gray)
            if rotation:
                gray = imaging.rotate_quadrant(gray, rotation)
                img = imaging.rotate_quadrant(img, rotation)
        binv = imaging.binarize(gray, True, dpi)
        if cfg.get("deskew", True):
            skew = imaging.estimate_skew(binv, dpi)
            if abs(skew) >= 0.05:
                gray = imaging.rotate_small(gray, skew)
                img = imaging.rotate_small(img, skew)
                binv = imaging.binarize(gray, True, dpi)
    else:
        binv = imaging.binarize(gray, False, dpi)
    if raw.kind.endswith("-traced"):  # faint rules survive the trace only as dashes
        binv, specks = imaging.bridge_dashed_rules(binv, dpi)
        gray = gray.copy()
        gray[specks > 0] = 255  # rule remnants are not text: keep them from OCR
    pa.image = img

    hm, vm = imaging.line_masks(binv, dpi)
    hm, vm = imaging.close_open_table_sides(hm, vm, dpi)  # tables cut off at the sheet edge
    grid = hm | vm
    cells, frame = detect_cells(grid, dpi)

    if native:
        words = list(raw.native_words)
        free = assign_words(cells, words)
        clean = None
    else:
        clean = imaging.remove_lines(gray, grid)
        words = imaging.ocr_image(clean, dpi, cfg["ocr_lang"], psm=11, min_conf=cfg["min_word_conf"])
        if raw.native_words:
            n_boxes = [w.bbox for w in raw.native_words]
            words = list(raw.native_words) + [
                w for w in words
                if not any(_box_overlap(w.bbox, nb) > 0.4 for nb in n_boxes)
            ]
        free = assign_words(cells, words)
        if cfg.get("cell_ocr", True) and cells:
            groups0 = group_cells(cells, dpi)
            targets = [c for g in groups0 if len(g) >= 3 for c in g]
            cell_workers = int(cfg.get("ocr_workers", 1 if cfg.get("_parallel") else 4))
            redo = imaging.ocr_cells(clean, targets, dpi, cfg["ocr_lang"], cfg["min_word_conf"],
                                     workers=cell_workers)
            for c in targets:
                new = redo.get(c.id) or []
                if new and (not c.words or mean_conf(new) >= mean_conf(c.words) - 0.05
                            or len("".join(w.text for w in new)) > len("".join(w.text for w in c.words))):
                    c.words = new
            words = free + [w for c in cells for w in c.words]
    pa.words, pa.cells = words, cells

    groups = group_cells(cells, dpi)
    used: set[int] = set()
    bom_tables, rev_tables = [], []
    for g in groups:
        bom_tables += find_grid_tables(g, cfg["bom_headers"], "bom", dpi, used, cfg["title_labels"])
    for g in groups:
        rev_tables += find_grid_tables(g, cfg["revision_headers"], "revision", dpi, used,
                                       cfg["title_labels"])
    tb_cells = title_block_cells(groups, used, cfg["title_labels"])
    tb_ids = {c.id for c in tb_cells}

    def outside(boxes):
        return [w for w in words if not any(_inside(w, b) for b in boxes)]

    if not bom_tables:
        pool = outside([t.bbox for t in rev_tables])
        bom_tables = find_text_tables(pool, cfg["bom_headers"], "bom", dpi)
        if bom_tables:  # the text table may have been swallowed by a title-block group
            tb_cells = [c for c in tb_cells
                        if not any(_box_overlap(c.bbox, t.bbox) > 0.5 for t in bom_tables)]
    if not rev_tables:
        tb_box = [c.bbox for c in tb_cells]
        pool = outside([t.bbox for t in bom_tables] + tb_box)
        rev_tables = find_text_tables(pool, cfg["revision_headers"], "revision", dpi)

    if not tb_cells:  # title-block rules too broken to form cells: read it from text layout
        tb_cells = text_title_cells(outside([t.bbox for t in bom_tables + rev_tables]),
                                    cfg["title_labels"], dpi)
    else:  # part of the title block may not have closed into cells
        tbb = union_bbox([c.bbox for c in tb_cells])
        m = dpi * 0.5
        in_cells = {id(w) for c in cells for w in c.words}
        near = [w for w in outside([t.bbox for t in bom_tables + rev_tables])
                if id(w) not in in_cells and tbb[0] - m <= w.cx <= tbb[2] + m
                and tbb[1] - m <= w.cy <= tbb[3] + m]
        if near:
            tb_cells = tb_cells + text_title_cells(near, cfg["title_labels"], dpi, min_fields=1)
    for t in bom_tables + rev_tables:  # cells whose rules were lost entirely
        complete_rows(t, free)
        if not native and cfg.get("cell_ocr", True):
            _reread_reconstructed(t, clean, dpi, cfg)
    pa.bom_tables, pa.rev_tables, pa.tb_cells = bom_tables, rev_tables, tb_cells
    if not native and clean is not None:
        for t in bom_tables:
            t.clean_image = clean
            t.dpi = dpi
            t.lang = cfg.get("ocr_lang", "eng")

    if not native:  # digit-constrained re-read of numeric columns that don't look numeric or have low confidence
        for t in bom_tables:
            if t.method != "grid":
                continue
            for row in t.rows:
                for key in ("item", "quantity", "mass"):
                    v = row.get(key)
                    if v is None or not v.text:
                        continue
                    if key != "item" and (re.search(r"\d", v.text) and v.conf >= cfg["low_conf_threshold"] or _AS_REQ.match(v.text)):
                        continue  # '4 NOS', '1.2 kg', 'A/R' - leave to the normaliser
                    if _NUMERIC.fullmatch(v.text) and v.conf >= cfg["low_conf_threshold"]:
                        continue
                    got = imaging.ocr_numeric(clean, v.bbox, dpi, cfg["ocr_lang"], orig_text=v.text)
                    if got and _NUMERIC.fullmatch(got[0]):
                        if not _NUMERIC.fullmatch(v.text) or got[1] > v.conf:
                            v.text, v.conf = got[0], max(v.conf, got[1])
                        else:
                            v.text, v.conf = got[0], max(min(v.conf, got[1]), 0.5)

    if not native:  # letter/digit confusions that only make sense one way
        for t in bom_tables + rev_tables:
            for row in t.rows:
                for v in row.values():
                    if v.text:
                        v.text = fix_ocr_confusions(v.text)
        for t in bom_tables:  # a lost leading zero: '1' among '02', '03', ...
            items = [r.get("item") for r in t.rows if r.get("item") is not None and r["item"].text]
            padded = [v for v in items if re.fullmatch(r"0\d", v.text)]
            if len(items) >= 3 and len(padded) >= len(items) - 1:
                for v in items:
                    if re.fullmatch(r"[1-9]", v.text):
                        v.text = "0" + v.text

    table_boxes = [t.bbox for t in bom_tables + rev_tables]
    tb_bbox = union_bbox([c.bbox for c in tb_cells]) if tb_cells else None
    free_words = [w for w in words if not any(_inside(w, b) for b in table_boxes)
                  and not (tb_bbox and _inside(w, tb_bbox))]
    if frame is not None:  # zone markers etc. between the outer and inner border
        free_words = [w for w in free_words if _inside(w, frame)]
    pa.notes_blocks = find_notes(free_words, dpi)
    if not native and pa.notes_blocks:
        masks = [t.bbox for t in bom_tables + rev_tables] + ([tb_bbox] if tb_bbox else [])
        pa.notes_blocks = [_reread_notes(lines, bb, clean, dpi, cfg, masks)
                           for lines, bb in pa.notes_blocks]

    regions = []
    if tb_cells:
        regions.append(Region("title_block", tb_bbox, raw.index,
                              _avg([c.conf for c in tb_cells if c.words]), tb_cells))
    for t in bom_tables:
        regions.append(Region("bom", t.bbox, raw.index, _avg([v.conf for r in t.rows for v in r.values()
                                                              if v.text])))
    for t in rev_tables:
        regions.append(Region("revision", t.bbox, raw.index,
                              _avg([v.conf for r in t.rows for v in r.values() if v.text])))
    for lines, bb in pa.notes_blocks:
        regions.append(Region("notes", bb, raw.index, _avg([l.conf for l in lines])))

    h, w = img.shape[:2]
    pa.result = PageResult(index=raw.index, source="native" if native else "ocr", width=w,
                           height=h, dpi=round(dpi, 1), skew_deg=round(skew, 3),
                           rotation_deg=rotation, regions=regions, kind=raw.kind, layout=raw.label)
    pa.free_words = free_words
    return pa


class _Box:
    """Minimal cell-like rectangle for imaging.ocr_cells."""

    def __init__(self, i, x0, y0, x1, y1):
        self.id, self.x0, self.y0, self.x1, self.y1 = i, x0, y0, x1, y1


def _reread_reconstructed(t: Table, clean, dpi: float, cfg: dict) -> None:
    """Values whose cell had to be reconstructed (row or column rule lost,
    or no cell at all) were read from a crop covering several rows/columns,
    or from the page-level OCR. Re-read each as its exact row x column box."""
    if t.method != "grid" or clean is None:
        return
    jobs = {}
    for ri, (row, rb) in enumerate(zip(t.rows, t.row_bboxes)):
        if not any(v.src != "cell" for v in row.values()):
            continue
        for ci, col in enumerate(t.columns):
            v = row.get(col.key)
            if v is not None and v.src == "cell" and v.text:
                continue
            jobs[len(jobs)] = (row, col.key, _Box(len(jobs), col.x0, rb[1], col.x1, rb[3]))
    if not jobs:
        return
    cell_workers = int(cfg.get("ocr_workers", 1 if cfg.get("_parallel") else 4))
    got = imaging.ocr_cells(clean, [b for *_, b in jobs.values()], dpi, cfg["ocr_lang"],
                            cfg["min_word_conf"], workers=cell_workers)
    from .layout import _cell_text, TableCellValue
    for i, (row, key, box) in jobs.items():
        ws = got.get(i) or []
        txt = _cell_text(ws)
        if not txt:
            continue
        old = row.get(key)
        conf = mean_conf(ws)
        # the exact cell box beats text pieced together from a merged crop
        if old is None or not old.text or conf >= old.conf - 0.1 or \
                (old.src != "cell" and conf >= 0.5 and len(txt) >= len(old.text)):
            row[key] = TableCellValue(txt, conf, union_bbox([w.bbox for w in ws]), "reread")


_NOTE_NUM = re.compile(r"^\s*\d{1,2}\s*[.)\]]\s")


def _reread_notes(lines, bb, clean, dpi: float, cfg: dict, masks):
    """Tesseract's sparse mode can skip list numbers set in their own column
    ('1.', '2.' ...), which merges all notes into one. Re-read the block as a
    uniform text block and keep that when it recovers more numbered items
    without losing text."""
    from .layout import _NOTES_HEAD, _NOTES_HEAD_INLINE
    if clean is None:
        return lines, bb
    old_num = sum(1 for l in lines if _NOTE_NUM.match(l.text))
    pad = int(dpi * 0.04)
    H, W = clean.shape[:2]
    x0, y0 = max(int(bb[0]) - pad, 0), max(int(bb[1]) - pad, 0)
    x1, y1 = min(int(bb[2]) + pad, W), min(int(bb[3]) + pad, H)
    crop = clean[y0:y1, x0:x1].copy()
    for m in masks:  # keep neighbouring tables out of the block
        a0, b0 = max(int(m[0]) - x0, 0), max(int(m[1]) - y0, 0)
        a1, b1 = min(int(m[2]) - x0, crop.shape[1]), min(int(m[3]) - y0, crop.shape[0])
        if a1 > a0 and b1 > b0:
            crop[b0:b1, a0:a1] = 255
    ws = imaging.ocr_image(crop, dpi, cfg["ocr_lang"], psm=6, min_conf=cfg["min_word_conf"],
                           offset=(x0, y0))
    new = [l for l in group_lines(ws)
           if not (_NOTES_HEAD.match(l.text) or _NOTES_HEAD_INLINE.match(l.text))]
    new_num = sum(1 for l in new if _NOTE_NUM.match(l.text))
    alnum = lambda ls: sum(ch.isalnum() for l in ls for ch in l.text)
    if not (new_num > old_num and alnum(new) >= 0.9 * alnum(lines)):
        return lines, bb
    # block mode gives the line structure and the numbers; keep the sparse-mode
    # words (usually the better read) wherever they cover the same line
    sparse = [w for l in lines for w in l.words]
    merged = []
    for l in new:
        x0, y0, x1, y1 = l.bbox
        mine = sorted((w for w in sparse if y0 <= w.cy <= y1 and x0 - 1 <= w.cx <= x1 + 1),
                      key=lambda w: w.x0)
        lead = []
        for w in l.words:
            if re.fullmatch(r"\d{1,2}\s*[.)\]]?", w.text) and not any(m.x0 <= w.cx <= m.x1 for m in mine):
                lead.append(w)
            else:
                break
        body_alnum = sum(ch.isalnum() for w in l.words[len(lead):] for ch in w.text)
        if mine and sum(ch.isalnum() for w in mine for ch in w.text) >= 0.8 * body_alnum:
            merged.append(TextLine(lead + mine))
        else:
            merged.append(l)
    return merged, bb


def _extract_page_content(pa: PageAnalysis, raw: RawPage, cfg: dict, page_no: int,
                          title: dict[str, FieldValue], bom_cols: list[str],
                          res: DrawingResult, all_specs: list[SpecCallout],
                          all_dims: list[Dimension]) -> None:
    """Stage 3: Extract structured records (title block, BOM, revisions, notes, specs, dimensions)."""
    pr = pa.result

    # ---------------- title block
    page_text = "\n".join(l.text for l in group_lines(pa.words))
    tb = parse_title_block(pa.tb_cells, cfg["title_labels"], raw.dpi, page_text, cfg["date_order"])
    _merge_cad_fields(tb, raw.cad_fields, cfg, res.warnings, page_no)
    for k, v in tb.items():
        if k not in title and v.value:
            title[k] = v

    # ---------------- BOM
    for t in pa.bom_tables:
        rows, warns = table_to_bom(t, page_no, cfg["low_conf_threshold"])
        res.bom.extend(rows)
        res.warnings.extend(f"page {page_no}: {w}" for w in warns)
        for c in t.columns:
            if c.key not in bom_cols:
                bom_cols.append(c.key)
        if t.method == "text":
            res.warnings.append(f"page {page_no}: BOM read from text alignment (no ruling lines) "
                                "- verify column assignment")

    # ---------------- revisions
    for t in pa.rev_tables:
        res.revisions.extend(table_to_revisions(t, page_no, cfg["date_order"]))

    # ---------------- notes & specs
    for lines, bb in pa.notes_blocks:
        for item in split_numbered_notes(lines):
            if pr.source == "ocr":
                item["text"] = fix_ocr_confusions(item["text"])
            res.notes.append({"page": page_no, "number": item["number"], "text": item["text"],
                              "confidence": round(item["conf"], 3),
                              "bbox": [round(v, 1) for v in item["bbox"]]})
            all_specs += find_specs(item["text"], "notes", page_no, item["bbox"], item["conf"])
    for k in ("material", "finish", "heat_treatment"):
        fv = tb.get(k)
        if fv and fv.value:
            found = find_specs(fv.value, "title_block", page_no, fv.bbox, fv.confidence)
            if not found:
                cat = {"material": "material", "finish": "surface_finish",
                       "heat_treatment": "heat_treatment"}[k]
                found = [SpecCallout(cat, fv.value.upper(), fv.value, "title_block", "unrecognised",
                                     fv.confidence, fv.bbox, page_no)]
            all_specs += found
    for r in [r for r in res.bom if r.page == page_no]:
        if r.material:
            found = find_specs(r.material, "bom", page_no, r.bbox, r.confidence,
                               categories={"material", "heat_treatment", "standard"})
            if not found and len(r.material.strip()) >= 2:
                found = [SpecCallout("material", r.material.strip().upper(), r.material.strip(),
                                     "bom", "custom", r.confidence, r.bbox, page_no)]
            all_specs += found
        if r.extra.get("finish"):
            all_specs += find_specs(r.extra["finish"], "bom", page_no, r.bbox, r.confidence,
                                    categories={"surface_finish", "heat_treatment"})
    note_boxes = [bb for _, bb in pa.notes_blocks]
    loose = [w for w in pa.free_words if not any(_inside(w, b) for b in note_boxes)]
    for line in group_lines(loose):
        for seg in split_segments(line, 3.0):
            all_specs += find_specs(seg.text, "page_text", page_no, seg.bbox, seg.conf,
                                    categories={"material", "surface_finish", "heat_treatment"})

    # ---------------- dimensions
    all_dims += extract_dimensions_from_words(pa.words, page_no)


def _consolidate_and_validate(res: DrawingResult, title: dict[str, FieldValue],
                              bom_cols: list[str], all_specs: list[SpecCallout],
                              all_dims: list[Dimension], cfg: dict, t0: float) -> DrawingResult:
    """Stage 4: Consolidate multi-page findings, cross-check revisions, and build validated summary."""
    res.title_block = title
    res.bom_columns = bom_cols
    res.specs = _dedupe_specs(all_specs)
    res.dimensions = dedupe_dimensions(all_dims)
    latest = latest_revision(res.revisions)
    if "revision" not in title and latest:
        title["revision"] = FieldValue(latest.rev, latest.confidence, latest.bbox,
                                       raw=latest.rev, normalized=latest.rev)
        res.warnings.append("revision taken from latest row of revision table")
    elif "revision" in title and latest and title["revision"].normalized and \
            latest.rev and latest.rev.upper() != str(title["revision"].normalized).upper():
        res.warnings.append(f"title block revision '{title['revision'].normalized}' differs from latest "
                            f"revision-table entry '{latest.rev}'")
    res.summary = build_summary(res, cfg)
    res.processing_seconds = time.time() - t0
    return res


def process_file(path: str | Path, cfg: dict, force_ocr: bool = False,
                 overlay_dir: Optional[Path] = None) -> DrawingResult:
    """Stage 5: Main orchestrator coordinating ingestion, analysis, extraction, and validation."""
    t0 = time.time()
    path = Path(path)
    imaging.find_tesseract(cfg.get("tesseract_cmd"))
    res = DrawingResult(source_file=str(path))
    title: dict[str, FieldValue] = {}
    all_specs: list[SpecCallout] = []
    all_dims: list[Dimension] = []
    bom_cols: list[str] = []

    # Stage 1: Ingestion & Iteration
    for raw in iter_pages(path, cfg["dpi"], cfg["max_pixels"], force_ocr, cfg["native_min_words"], cfg):
        res.warnings.extend(f"page {raw.index + 1}: {n}" for n in raw.notes)
        # Stage 2: Page Layout & Detection
        pa = analyse_page(raw, cfg)
        pr = pa.result
        res.pages.append(pr)
        page_no = raw.index + 1

        # Stage 3: Extraction
        _extract_page_content(pa, raw, cfg, page_no, title, bom_cols, res, all_specs, all_dims)

        if overlay_dir is not None:
            from .overlay import render_page
            overlay_dir.mkdir(parents=True, exist_ok=True)
            out = overlay_dir / f"{path.stem}_p{page_no}_overlay.png"
            render_page(pa, [s for s in all_specs if s.page == page_no],
                        [r for r in res.bom if r.page == page_no], out)
            pr.overlay_path = str(out)

    # Stage 4: Consolidation & Validation
    return _consolidate_and_validate(res, title, bom_cols, all_specs, all_dims, cfg, t0)


def _merge_cad_fields(tb: dict[str, FieldValue], cad_fields: dict, cfg: dict,
                      warnings: list[str], page_no: int) -> None:
    """Title-block values stored as CAD block attributes (exact, tagged)
    fill fields the layout analysis did not find. Where both exist and
    disagree, the layout value is kept and the difference reported."""
    if not cad_fields:
        return
    add: dict[str, FieldValue] = {}
    for k, d in cad_fields.items():
        val = (d.get("value") or "").strip()
        if not val:
            continue
        if k in tb and tb[k].value:
            a = re.sub(r"[^A-Z0-9]", "", tb[k].value.upper())
            b = re.sub(r"[^A-Z0-9]", "", val.upper())
            if a != b and b not in a:
                warnings.append(f"page {page_no}: title block {k} '{tb[k].value}' differs from CAD "
                                f"attribute {d.get('tag')}='{val}'")
            continue
        bb = tuple(d["bbox"]) if d.get("bbox") else None
        add[k] = FieldValue(val, 1.0, bb, raw=f"{d.get('tag')}={val}")
    normalise_title_fields(add, cfg["date_order"])
    tb.update(add)


def build_summary(res: DrawingResult, cfg: dict) -> dict:
    tb = res.title_block

    def v(k, norm=False):
        f = tb.get(k)
        if not f:
            return None
        return (f.normalized or f.value) if norm else f.value

    s = {
        "file": Path(res.source_file).name,
        "pages": len(res.pages),
        "input_type": ",".join(sorted({p.source for p in res.pages})),
        "file_format": Path(res.source_file).suffix.lstrip(".").upper() or None,
        "page_kinds": ",".join(sorted({p.kind for p in res.pages if p.kind})) or None,
        "drawing_number": v("drawing_number", True),
        "drawing_title": v("drawing_title"),
        "revision": v("revision", True),
        "drawn_by": v("drawn_by"),
        "date": v("date", True) or v("date"),
        "scale": v("scale", True) or v("scale"),
        "projection": v("projection", True) or v("projection"),
        "sheet": v("sheet"),
    }
    s["author_date"] = " / ".join(x for x in (s["drawn_by"], s["date"]) if x) or None
    s.update(summarise(res.specs))
    # A note or title-block field that is explicitly labelled MATERIAL /
    # SURFACE FINISH / HEAT TREATMENT is the drawing's own callout: report it
    # as written rather than the fragments the pattern library recognises.
    for key, val in labelled_callouts(res).items():
        s[key] = val
    if tb.get("weight"):
        s["assembly_weight"] = tb["weight"].value
        s["assembly_weight_kg"] = tb["weight"].normalized
    s["bom_items"] = len(res.bom)
    qtys = [r.quantity_value for r in res.bom if isinstance(r.quantity_value, (int, float))]
    s["bom_total_quantity"] = sum(qtys) if qtys else None
    s["revisions"] = len(res.revisions)
    s["notes"] = len(res.notes)

    reasons = []
    for k in ("drawing_number", "drawing_title", "revision"):
        if not tb.get(k):
            reasons.append(f"missing {k}")
    lc = cfg["low_conf_threshold"]
    low_tb = [k for k, f in tb.items() if f.confidence < lc]
    if low_tb:
        reasons.append("low-confidence title fields: " + ", ".join(sorted(low_tb)))
    flagged = [r for r in res.bom if r.flags and set(r.flags) - {"mass_unit_assumed_kg"}]
    if flagged:
        reasons.append(f"{len(flagged)} BOM row(s) flagged")
    if not res.bom:
        reasons.append("no BOM table found")

    # Calculate text confidence independently across recognized text elements
    tb_confs = [f.confidence for f in tb.values() if f.confidence is not None]
    bom_text_confs = [r.confidence for r in res.bom if r.confidence is not None]
    notes_confs = [n["confidence"] for n in res.notes if "confidence" in n and n["confidence"] is not None]
    rev_confs = [r.confidence for r in res.revisions if r.confidence is not None]
    dim_confs = [d.confidence for d in res.dimensions if d.confidence is not None]
    text_confs = tb_confs + bom_text_confs + notes_confs + rev_confs + dim_confs

    s["text_confidence"] = round(sum(text_confs) / len(text_confs), 3) if text_confs else None

    # Structural confidence across BOM table layout
    struct_confs = [r.structural_confidence for r in res.bom]
    s["structural_confidence"] = round(sum(struct_confs) / len(struct_confs), 3) if struct_confs else 1.0

    # Overall combined mean confidence
    all_confs = text_confs + struct_confs
    s["mean_confidence"] = round(sum(all_confs) / len(all_confs), 3) if all_confs else None

    # Avoid hiding a bad row behind a high average by evaluating critical minimums
    min_row_struct_conf = min(struct_confs) if struct_confs else 1.0
    min_row_text_conf = min(bom_text_confs) if bom_text_confs else 1.0
    s["min_structural_confidence"] = round(min_row_struct_conf, 3)
    s["min_text_confidence"] = round(min(text_confs), 3) if text_confs else None

    if min_row_struct_conf < lc:
        reasons.append(f"low structural / column assignment confidence on row (min {min_row_struct_conf:.2f})")
    elif s["structural_confidence"] < lc:
        reasons.append(f"low mean structural confidence ({s['structural_confidence']:.2f})")

    if min_row_text_conf < lc:
        reasons.append(f"low text OCR confidence on row (min {min_row_text_conf:.2f})")

    s["review_required"] = bool(reasons)
    s["review_reasons"] = "; ".join(reasons) or None
    return s


_CALLOUT_LABELS = [
    ("material_callout", r"MATERIAL\s+CALL[\s-]?OUT|MATERIAL\s+SPEC(?:IFICATION)?|MATERIALS?|MAT'?L"),
    ("surface_finish", r"SURFACE\s+FINISH|SURFACE\s+TREATMENT|SURFACE\s+ROUGHNESS|FINISH|COATING"),
    ("heat_treatment", r"HEAT\s+TREATMENT|HEAT\s+TREAT(?:ED)?|H\s*/\s*T"),
]
_UOS_TAIL = re.compile(r"[\s,;]*\b(?:UNLESS\s+OTHERWISE\s+(?:SPECIFIED|STATED|NOTED)|U\.?O\.?S\.?)\b.*$", re.I)


def _callout_value(text: str, label_rx: str) -> Optional[str]:
    m = re.match(rf"^\s*(?:{label_rx})\s*[:\-=]\s*(.+)$", text or "", re.I | re.S)
    if not m:
        return None
    v = _UOS_TAIL.sub("", m.group(1))
    v = re.sub(r"\s+", " ", v).strip(" .;,")
    return v or None


def labelled_callouts(res: DrawingResult) -> dict[str, str]:
    """Explicitly labelled material / finish / heat-treatment callouts, from
    the title block first, then the notes (first labelled note wins)."""
    out: dict[str, str] = {}
    tb_map = {"material_callout": "material", "surface_finish": "finish",
              "heat_treatment": "heat_treatment"}
    for key, tbk in tb_map.items():
        f = res.title_block.get(tbk)
        if f and f.value and len(f.value.strip(" -/.")) > 1:
            out[key] = re.sub(r"\s+", " ", f.value).strip(" .;,")
    for n in res.notes:
        for key, rx in _CALLOUT_LABELS:
            if key in out:
                continue
            v = _callout_value(n["text"], rx)
            if v:
                out[key] = v
                break
    return out


def _dedupe_specs(specs: list[SpecCallout]) -> list[SpecCallout]:
    seen, out = set(), []
    for s in specs:
        k = (s.category, s.value.upper(), s.source, s.page)
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def _inside(w: Word, b) -> bool:
    return b[0] <= w.cx <= b[2] and b[1] <= w.cy <= b[3]


def _box_overlap(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = max((a[2] - a[0]) * (a[3] - a[1]), 1)
    return ix * iy / area


def _avg(xs) -> float:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if xs else 0.0
