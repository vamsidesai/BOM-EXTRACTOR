"""Layout analysis: ruled-cell detection, cell grouping and automatic
identification of BOM tables, revision tables, title blocks and notes.

Nothing here relies on fixed pixel coordinates: regions are found from the
ruling-line structure of the sheet and the vocabulary printed in it.
"""
from __future__ import annotations

import itertools
import re
import statistics
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from .models import Cell, TextLine, Word, union_bbox, mean_conf
from .textutil import best_match, group_lines, match_label_prefix, norm_label, split_segments

_CAPTION = re.compile(r"BILL\s+OF\s+MATERIALS?|PARTS?\s+LIST|\bBOM\b|MATERIALS?\s+LIST|ITEM\s+LIST|PARTS\s+SCHEDULE", re.I)
UNIT_TOKENS = {"KG", "KGS", "G", "GM", "GMS", "LB", "LBS", "MM", "NOS", "PCS", "EA"}


@dataclass
class Column:
    key: str  # canonical field name, or "col_<n>" / raw header for unknown columns
    header: str
    x0: float
    x1: float
    unit: Optional[str] = None
    inferred: bool = False


@dataclass
class TableCellValue:
    text: str
    conf: float
    bbox: tuple
    src: str = "cell"  # cell | split (row rule lost) | multi (column rule lost) | free (cell lost)
    struct_conf: float = 1.0  # structural / column alignment confidence


@dataclass
class Table:
    kind: str  # bom | revision
    columns: list[Column]
    rows: list[dict[str, TableCellValue]]
    row_bboxes: list[tuple]
    bbox: tuple
    header_bbox: tuple
    header_position: str = "top"  # top | bottom
    caption: Optional[str] = None
    method: str = "grid"  # grid | text
    cells: list[Cell] = field(default_factory=list)


# ======================================================================
# cells
# ======================================================================

def detect_cells(grid: np.ndarray, dpi: float) -> tuple[list[Cell], Optional[tuple]]:
    """Find enclosed rectangular cells in a ruling-line mask.

    Returns (cells, inner_frame_bbox). The drawing frame (largest enclosed
    area) is returned separately so border zone-marker strips outside it can
    be ignored.
    """
    H, W = grid.shape
    g = cv2.dilate(grid, np.ones((3, 3), np.uint8))
    inv = cv2.bitwise_not(g)
    n, _, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    min_w, min_h = dpi * 0.08, dpi * 0.07
    frame = None
    frame_area = 0
    cells: list[Cell] = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        if x <= 1 or y <= 1 or x + w >= W - 1 or y + h >= H - 1:
            continue  # area outside the drawing border
        if w * h > 0.25 * W * H:
            if w * h > frame_area:
                frame, frame_area = (x, y, x + w, y + h), w * h
            continue
        if w < min_w or h < min_h:
            continue
        if area / float(w * h) < 0.82:
            continue  # not a clean rectangle (part geometry, dimension lines...)
        cells.append(Cell(float(x), float(y), float(x + w), float(y + h)))
    if frame is not None:
        fx0, fy0, fx1, fy1 = frame
        tol = dpi * 0.02
        cells = [c for c in cells if c.x0 >= fx0 - tol and c.y0 >= fy0 - tol
                 and c.x1 <= fx1 + tol and c.y1 <= fy1 + tol]
    for i, c in enumerate(cells):
        c.id = i
    return cells, frame


def assign_words(cells: list[Cell], words: list[Word]) -> list[Word]:
    """Attach words to the cell containing their centre. Returns words that
    fall in no cell."""
    for c in cells:
        c.words = []
    if not cells:
        return list(words)
    xs = np.array([[c.x0, c.y0, c.x1, c.y1] for c in cells])
    free = []
    for w in words:
        cx, cy = w.cx, w.cy
        hit = np.where((xs[:, 0] <= cx) & (xs[:, 2] >= cx) & (xs[:, 1] <= cy) & (xs[:, 3] >= cy))[0]
        if len(hit):
            # smallest containing cell
            j = min(hit, key=lambda k: (xs[k, 2] - xs[k, 0]) * (xs[k, 3] - xs[k, 1]))
            # Text never starts left of its own cell's rule: a word that does is
            # overflow from the cell to the left (long CAD text, substituted fonts).
            if w.x0 < xs[j, 0] - 0.3 * max(w.h, 1.0):
                lx = w.x0 + 0.25 * max(w.h, 1.0)
                left = np.where((xs[:, 0] <= lx) & (xs[:, 2] >= lx) & (xs[:, 1] <= cy) & (xs[:, 3] >= cy))[0]
                left = [k for k in left if abs(xs[k, 2] - xs[j, 0]) <= max(w.h, 1.0)]
                if left:
                    j = min(left, key=lambda k: (xs[k, 2] - xs[k, 0]) * (xs[k, 3] - xs[k, 1]))
            cells[j].words.append(w)
        else:
            # centre on a ruling line (e.g. text running over a cell border):
            # take the cell the word overlaps most, if it overlaps enough
            ix = np.clip(np.minimum(xs[:, 2], w.x1) - np.maximum(xs[:, 0], w.x0), 0, None)
            iy = np.clip(np.minimum(xs[:, 3], w.y1) - np.maximum(xs[:, 1], w.y0), 0, None)
            inter = ix * iy
            area = max((w.x1 - w.x0) * (w.y1 - w.y0), 1e-6)
            k = int(np.argmax(inter)) if len(inter) else -1
            if k >= 0 and inter[k] >= 0.3 * area:
                cells[k].words.append(w)
            else:
                free.append(w)
    return free


def group_cells(cells: list[Cell], dpi: float) -> list[list[Cell]]:
    """Union-find cells that share an edge into connected table groups."""
    tol = dpi * 0.035
    parent = list(range(len(cells)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(len(cells)), key=lambda i: cells[i].x0)
    for ii, i in enumerate(order):
        a = cells[i]
        for j in order[ii + 1:]:
            b = cells[j]
            if b.x0 > a.x1 + tol:
                break
            if _adjacent(a, b, tol):
                parent[find(i)] = find(j)
    groups: dict[int, list[Cell]] = {}
    for i, c in enumerate(cells):
        groups.setdefault(find(i), []).append(c)
    return list(groups.values())


def _adjacent(a: Cell, b: Cell, tol: float) -> bool:
    vo = min(a.y1, b.y1) - max(a.y0, b.y0)
    if vo > 0.3 * min(a.h, b.h) and (abs(a.x1 - b.x0) <= tol or abs(b.x1 - a.x0) <= tol):
        return True
    ho = min(a.x1, b.x1) - max(a.x0, b.x0)
    if ho > 0.3 * min(a.w, b.w) and (abs(a.y1 - b.y0) <= tol or abs(b.y1 - a.y0) <= tol):
        return True
    return False


# ======================================================================
# header matching
# ======================================================================

def match_header(text: str, vocab: dict[str, list[str]]) -> tuple[Optional[str], float, Optional[str]]:
    """Match a table header cell. Returns (field, score, unit)."""
    unit = None
    m = re.search(r"[\(\[]\s*([A-Za-z]{1,4})\s*[\)\]]", text)
    if m and m.group(1).upper() in UNIT_TOKENS:
        unit = m.group(1).upper()
    n = norm_label(text)
    toks = n.split()
    while len(toks) > 1 and toks[-1] in UNIT_TOKENS:
        unit = unit or toks[-1]
        toks.pop()
    n = " ".join(toks)
    if "/" in n:  # "WT/KG"
        a, _, b = n.partition("/")
        if b.strip() in UNIT_TOKENS:
            unit, n = unit or b.strip(), a.strip()
    if not n or len(n) > 40:
        return None, 0.0, None
    fld, score, _ = best_match(n, vocab, threshold=0.84, allow_prefix=False)
    if not fld:  # second chance with common OCR glyph confusions undone
        alt = n
        for a, b in _OCR_SWAPS:
            alt = alt.replace(a, b)
        if alt != n:
            fld, score, _ = best_match(alt, vocab, threshold=0.84, allow_prefix=False)
    return fld, score, unit


_OCR_SWAPS = [("VI", "M"), ("IVI", "M"), ("RN", "M"), ("NI", "M"), ("CL", "D"), ("0", "O"), ("1", "I"),
              ("5", "S"), ("8", "B"), ("$", "S"), ("VV", "W"), ("|", "I")]


# ======================================================================
# grid tables
# ======================================================================

def find_grid_tables(group: list[Cell], vocab: dict[str, list[str]], kind: str,
                     dpi: float, used: set[int], title_vocab: dict[str, list[str]]) -> list[Table]:
    tol = dpi * 0.035
    labelled = []
    group = list(group)
    for c in list(group):
        if c.id in used or not c.words:
            continue
        fld, score, unit = match_header(c.text, vocab)
        if fld:
            labelled.append((c, fld, unit))
            continue
        # a header cell whose column rule was lost holds two headers ('QTY  MATERIAL'):
        # split it at the gap between them
        parts = _split_header_cell(c, vocab, [e for o in group if o is not c and o.x0 >= c.x0 - tol
                                                 and o.x1 <= c.x1 + tol and o.y0 > c.y0
                                                 for e in (o.x0, o.x1)])
        if parts:
            group.remove(c)
            for pc in parts:
                group.append(pc)
                f2, _, u2 = match_header(pc.text, vocab)
                labelled.append((pc, f2, u2))
    if len(labelled) < 3:
        return []

    tables = []
    for band in _bands([x[0] for x in labelled], tol):
        bid = {c.id for c in band}
        flds = {f for c, f, _ in labelled if c.id in bid}
        if not _is_header(flds, kind):
            continue
        # full header band = all cells in the group on this band, contiguous
        y0 = statistics.median([c.y0 for c in band])
        y1 = statistics.median([c.y1 for c in band])
        work = [c for c in group if c.id not in used]
        row = [c for c in work if abs(c.y0 - y0) <= tol and abs(c.y1 - y1) <= tol]
        # a header cell whose rule to the first data row was lost (faint scan)
        # appears as one tall cell: split it on the header band's edge
        rid = {c.id for c in row}
        for c in list(work):
            if c.id in rid or c.x1 < min(x.x0 for x in row) - tol * 4 or \
                    c.x0 > max(x.x1 for x in row) + tol * 4:
                continue
            if abs(c.y0 - y0) <= tol and c.y1 > y1 + tol:
                head, rest = _split_cell(c, y1)
            elif abs(c.y1 - y1) <= tol and c.y0 < y0 - tol:
                rest, head = _split_cell(c, y0)
            else:
                continue
            if not head.words:
                continue
            work.remove(c)
            work += [head, rest]
            row.append(head)
        row = _contiguous_with(sorted(row, key=lambda c: c.x0), band, tol)
        if any(c.id in used for c in row):
            continue
        info = {c.id: (f, u) for c, f, u in labelled}
        cols, seen = [], set()
        for k, c in enumerate(row):
            f, u = info.get(c.id, (None, None))
            key = f if f and f not in seen else (f"{f}_{k}" if f else _slug(c.text) or f"col_{k + 1}")
            seen.add(key)
            cols.append(Column(key, c.text, c.x0, c.x1, u))
        table = _grow_table(cols, row, work, used, tol, kind, vocab, title_vocab)
        if table is not None:
            if kind == "bom":
                _infer_columns(table, vocab)
            tables.append(table)
            used.update(c.id for c in table.cells)
            used.update(c.parent for c in table.cells if c.parent >= 0)
    return tables


def _is_header(flds: set[str], kind: str) -> bool:
    if kind == "bom":
        return len(flds) >= 3 and bool(flds & {"item", "quantity"}) and \
            bool(flds & {"part_number", "description", "material"})
    if kind == "revision":
        return "rev" in flds and len(flds) >= 2 and bool(flds & {"description", "date"})
    return False


def _bands(cells: list[Cell], tol: float) -> list[list[Cell]]:
    bands: list[list[Cell]] = []
    for c in sorted(cells, key=lambda c: c.y0):
        for b in bands:
            if abs(b[0].y0 - c.y0) <= tol and abs(b[0].y1 - c.y1) <= tol:
                b.append(c)
                break
        else:
            bands.append([c])
    return bands


def _contiguous_with(row: list[Cell], seed: list[Cell], tol: float) -> list[Cell]:
    if not row:
        return row
    seed_ids = {c.id for c in seed}
    runs, cur = [], [row[0]]
    for a, b in zip(row, row[1:]):
        if b.x0 - a.x1 <= tol:
            cur.append(b)
        else:
            runs.append(cur)
            cur = [b]
    runs.append(cur)
    return max(runs, key=lambda r: sum(1 for c in r if c.id in seed_ids))


def _grow_table(cols, header_row, group, used, tol, kind, vocab, title_vocab) -> Optional[Table]:
    tx0, tx1 = cols[0].x0, cols[-1].x1
    width = tx1 - tx0
    hid = {c.id for c in header_row}
    pool = [c for c in group if c.id not in used and c.id not in hid
            and c.x0 >= tx0 - tol and c.x1 <= tx1 + tol]

    def aligned(c):
        return any(abs(c.x0 - col.x0) <= tol for col in cols) and \
            any(abs(c.x1 - col.x1) <= tol for col in cols)

    def take_band(edge, up):
        if up:
            cand = [c for c in pool if abs(c.y1 - edge) <= tol]
        else:
            cand = [c for c in pool if abs(c.y0 - edge) <= tol]
        if not cand:
            return None
        ref = statistics.median([c.y0 if up else c.y1 for c in cand])
        band = [c for c in cand if abs((c.y0 if up else c.y1) - ref) <= tol]
        # cells running past this row (a lost row rule) still belong to it
        spans = [c for c in cand if c not in band and aligned(c) and
                 ((up and c.y0 < ref - tol) or (not up and c.y1 > ref + tol))]
        cover = sum(c.w for c in band + spans if aligned(c))
        if cover < 0.6 * width:
            return None
        # cells spanning several rows here (a lost row rule): split at the row edge
        for c in cand:
            if c in band or not aligned(c):
                continue
            if up and c.y0 < ref - tol:
                rest, piece = _split_cell(c, ref)
            elif not up and c.y1 > ref + tol:
                piece, rest = _split_cell(c, ref)
            else:
                continue
            pool.remove(c)
            pool.append(rest)
            band.append(piece)
        return sorted(band, key=lambda c: c.x0)

    def is_stop(band):
        if len(band) == 1 and _spans(band[0], cols) >= min(3, len(cols)):
            return "caption" if _CAPTION.search(band[0].text) else "end"
        hits = 0
        for c in band:
            if c.words:
                f, lab, rest = match_label_prefix(c.text, title_vocab)
                if f in {"drawing_number", "drawn_by", "scale", "checked_by", "sheet",
                         "approved_by", "projection", "drawing_title", "date"}:
                    # a real title-block label stands alone or is followed by ':'
                    if not rest.strip() or lab.rstrip().endswith(":"):
                        return "title"
                    hits += 1
        if hits >= 2:
            return "title"
        flds = {match_header(c.text, vocab)[0] for c in band if c.words}
        if _is_header({f for f in flds if f}, kind):
            return "header"
        return None

    rows_up, rows_down, caption = [], [], None
    top, bottom = min(c.y0 for c in header_row), max(c.y1 for c in header_row)
    while True:
        b = take_band(top, up=True)
        if not b:
            break
        stop = is_stop(b)
        if stop:
            if stop == "caption":
                caption = b[0].text or None
                rows_up.append(("caption", b))
            break
        rows_up.append(("row", b))
        top = min(c.y0 for c in b)
        bids = {c.id for c in b}
        pool[:] = [c for c in pool if c.id not in bids]
    while True:
        b = take_band(bottom, up=False)
        if not b:
            break
        stop = is_stop(b)
        if stop:
            if stop == "caption" and not caption:
                caption = b[0].text or None
                rows_down.append(("caption", b))
            break
        rows_down.append(("row", b))
        bottom = max(c.y1 for c in b)
        bids = {c.id for c in b}
        pool[:] = [c for c in pool if c.id not in bids]

    data_up = [b for t, b in rows_up if t == "row"]
    data_down = [b for t, b in rows_down if t == "row"]
    n_up = sum(1 for b in data_up if any(c.words for c in b))
    n_down = sum(1 for b in data_down if any(c.words for c in b))
    if n_up == 0 and n_down == 0:
        return None
    header_pos = "bottom" if n_up > n_down else "top"
    # Rows nearest the header first (ISO bottom-header BOMs list upward)
    bands = data_up if header_pos == "bottom" else data_down
    split_bands = []
    for band in bands:
        subs = _split_multiline_band(band, cols)
        split_bands.extend(reversed(subs) if header_pos == "bottom" else subs)
    bands = split_bands
    rows, row_bbs = [], []
    for band in bands:
        vals = _band_to_values(band, cols)
        if any(v.text for v in vals.values()):
            rows.append(vals)
            row_bbs.append(union_bbox([c.bbox for c in band]))
    all_cells = list(header_row) + [c for _, b in rows_up + rows_down for c in b]
    return Table(kind=kind, columns=cols, rows=rows, row_bboxes=row_bbs,
                 bbox=union_bbox([c.bbox for c in all_cells]),
                 header_bbox=union_bbox([c.bbox for c in header_row]),
                 header_position=header_pos, caption=caption, method="grid", cells=all_cells)


_VID = itertools.count(10_000_000)
_ITEM_RX = re.compile(r"^[A-Z]?\d{1,4}[A-Z]?\.?$", re.I)


def _digitish(t: str) -> str:
    """OCR letters that stand for digits in an item number ('OL' -> '01')."""
    return t.translate(str.maketrans({"O": "0", "o": "0", "L": "1", "l": "1", "I": "1", "|": "1",
                                      "S": "5", "B": "8", "Z": "2"}))


def _split_multiline_band(band: list[Cell], cols) -> list[list[Cell]]:
    """A row band that holds several BOM lines because whole row rules were
    lost (faint scans, drawings traced to vectors). The item column decides:
    if its cell holds k >= 2 stacked item numbers, and most filled cells hold
    k lines too, the band is split at the gaps between the lines.
    A single row whose description merely wraps is left alone."""
    item_col = next((c for c in cols if c.key == "item"), None)
    filled = [c for c in band if c.words]
    if len(filled) < 2:
        return [band]
    lines = {c.id: [l for l in group_lines([w for w in c.words if not _JUNK.match(w.text)])
                    if any(ch.isalnum() for ch in l.text)] for c in filled}
    k = None
    item_cell = None
    if item_col is not None:
        icx = (item_col.x0 + item_col.x1) / 2
        item_cell = next((c for c in filled if c.x0 <= icx <= c.x1), None)
    if item_cell is not None:
        ls = lines[item_cell.id]
        items = [l for l in ls if _ITEM_RX.match(_digitish(l.text.replace(" ", "")))]
        other = [l for l in ls if l not in items]
        # specks between stacked item numbers may OCR as a stray 'ae' or '.'
        if len(items) >= 2 and all(sum(ch.isalnum() for ch in l.text) <= 2 and not
                                   any(ch.isdigit() for ch in l.text) for l in other):
            k = len(items)
            lines[item_cell.id] = items
    if k is None:
        return [band]
    # k distinct item numbers stacked in the item cell is strong evidence on its
    # own; ask only that one other cell shows the same k lines (OCR of the rest
    # of a cell with lost rules is often noisy)
    agree = sum(1 for c in filled if len(lines[c.id]) == k)
    if agree < 2:
        return [band]
    # cut between consecutive lines (median over the cells that agree)
    cuts = []
    for i in range(1, k):
        ys = []
        for c in filled:
            ls = lines[c.id]
            if len(ls) == k:
                ys.append((ls[i - 1].bbox[3] + ls[i].bbox[1]) / 2)
        cuts.append(statistics.median(ys))
    out, rest = [], list(band)
    for y in cuts:
        upper, lower = [], []
        for c in rest:
            a, b = _split_cell(c, y)
            upper.append(a)
            lower.append(b)
        out.append(upper)
        rest = lower
    out.append(rest)
    return out



def complete_rows(t: "Table", free_words: list[Word]) -> int:
    """Fill empty cells of a grid table from words that fell in no cell
    (a cell whose rules were lost entirely). Returns cells filled."""
    if t.method != "grid" or not free_words or not t.row_bboxes:
        return 0
    filled = 0
    used: set[int] = set()
    for row, rb in zip(t.rows, t.row_bboxes):
        for col in t.columns:
            v = row.get(col.key)
            if v is not None and v.text:
                continue
            ws = [w for w in free_words if id(w) not in used and col.x0 <= w.cx <= col.x1
                  and rb[1] <= w.cy <= rb[3]]
            txt = _cell_text(ws)
            if not txt:
                continue
            used.update(id(w) for w in ws)
            row[col.key] = TableCellValue(txt, mean_conf(ws), union_bbox([w.bbox for w in ws]), "free")
            filled += 1
    return filled


def _split_header_cell(c: Cell, vocab, edges: list[float] = ()) -> Optional[list[Cell]]:
    """Split a cell into side-by-side virtual cells if its words form 2+
    phrases separated by clear gaps that each match a column header. The cut
    goes where the rows below have their column rule, if they do."""
    ws = [w for w in c.words if not _JUNK.match(w.text)]  # rule fragments read as '=' '|'
    line = group_lines(ws)
    if len(line) != 1 or len(ws) < 2:
        return None
    segs = split_segments(line[0], gap_factor=1.2)
    if len(segs) < 2:
        return None
    if not all(match_header(sg.text, vocab)[0] for sg in segs):
        return None
    root = c.parent if c.parent >= 0 else c.id
    out, x = [], c.x0
    for i, sg in enumerate(segs):
        if i == len(segs) - 1:
            x1 = c.x1
        else:
            lo, hi = sg.bbox[2], segs[i + 1].bbox[0]
            inside = [e for e in edges if lo <= e <= hi]
            x1 = statistics.median(inside) if inside else (lo + hi) / 2
        out.append(Cell(x, c.y0, x1, c.y1, list(sg.words), id=next(_VID), parent=root))
        x = x1
    return out


def _split_cell(c: Cell, y: float) -> tuple[Cell, Cell]:
    """Split a cell horizontally at y into (upper, lower) virtual cells."""
    root = c.parent if c.parent >= 0 else c.id
    a = Cell(c.x0, c.y0, c.x1, y, [w for w in c.words if w.cy < y], id=next(_VID), parent=root)
    b = Cell(c.x0, y, c.x1, c.y1, [w for w in c.words if w.cy >= y], id=next(_VID), parent=root)
    return a, b


_NUM_RX = re.compile(r"^\d+(?:[.,]\d+)?$")
_MASS_NUM_RX = re.compile(r"^\d+(?:[.,]\d+)?(?:\s*(?:kg|kgs?|g|gms?|grams?|lbs?|pounds?|oz|t))?$", re.I)
_INT_RX = re.compile(r"^\d{1,4}$")
_PN_RX = re.compile(r"^(?=.*\d)(?=.*[A-Z])[A-Z0-9][A-Z0-9\-_/.]{3,}$", re.I)
_UNIT_HEADER_RX = re.compile(r"\b(KG|KGS|KILOGRAMS?|G|GM|GMS|GRAM|GRAMS|LB|LBS|POUND|POUNDS|OZ|TONNES?|T)\b", re.I)


def _extract_column_unit(header: str) -> Optional[str]:
    if not header:
        return None
    m = _UNIT_HEADER_RX.search(header)
    if m:
        u = m.group(1).upper()
        if u in ("KG", "KGS", "KILOGRAM", "KILOGRAMS"):
            return "KG"
        if u in ("G", "GM", "GMS", "GRAM", "GRAMS"):
            return "G"
        if u in ("LB", "LBS", "POUND", "POUNDS"):
            return "LB"
        if u in ("OZ",):
            return "OZ"
        if u in ("T", "TONNE", "TONNES"):
            return "T"
        return u
    return None


def _infer_columns(t: "Table", vocab) -> None:
    """Give unrecognised BOM columns a canonical field from their content
    (a misread header must not lose a whole column), and ensure units are
    correctly extracted for mass columns."""
    from .specs import find_specs
    have = {c.key for c in t.columns}

    # Ensure any existing mass column has unit extracted from header if missing
    for col in t.columns:
        if col.key == "mass" and not col.unit:
            col.unit = _extract_column_unit(col.header)

    for col in t.columns:
        if col.key in vocab:
            continue
        vals = [r[col.key].text.strip() for r in t.rows if r.get(col.key) and r[col.key].text.strip()]
        if len(vals) < 2:
            continue
        def frac(rx):
            return sum(1 for v in vals if rx.match(v)) / len(vals)
        guess = None

        head_upper = col.header.upper()
        has_mass_header = bool(re.search(r"\b(MASS|WEIGHT|WT|GEWICHT|MASSE|POIDS|PESO)\b", head_upper))
        has_unit_header = bool(re.search(r"[\(\[]?\b(KG|KGS|G|GMS|LBS?)\b[\)\]]?", head_upper))
        is_mat_data = sum(1 for v in vals if find_specs(v, "bom", categories={"material"})) / len(vals) >= 0.5

        if "material" not in have and (is_mat_data or (re.search(r"\bMATERIAL\b", head_upper) and not frac(_MASS_NUM_RX) >= 0.8)):
            guess = "material"
        elif "mass" not in have and not is_mat_data and (
            ((has_mass_header or has_unit_header) and frac(_MASS_NUM_RX) >= 0.5) or
            (frac(_MASS_NUM_RX) >= 0.80 and (any("." in v or "," in v for v in vals) or any(re.search(r"\b(?:kg|lbs?|gms?)\b", v, re.I) for v in vals)))
        ):
            guess = "mass"
        elif frac(_INT_RX) >= 0.85 and "quantity" not in have and "item" in have:
            guess = "quantity"
        elif "part_number" not in have and frac(_PN_RX) >= 0.75:
            guess = "part_number"
        if guess:
            for r in t.rows:
                if col.key in r:
                    old_val = r.pop(col.key)
                    old_val.struct_conf = min(old_val.struct_conf, 0.80)
                    r[guess] = old_val
            col.key = guess
            col.inferred = True
            if guess == "mass" and not col.unit:
                col.unit = _extract_column_unit(col.header)
                if not col.unit:
                    m_units = [re.search(r"\b(KG|G|LBS?)\b", v, re.I) for v in vals]
                    if all(m_units) and len(set(m.group(1).upper() for m in m_units)) == 1:
                        col.unit = m_units[0].group(1).upper()
            have.add(guess)


def _spans(cell: Cell, cols: list[Column]) -> int:
    return sum(1 for col in cols if min(cell.x1, col.x1) - max(cell.x0, col.x0) > 0.5 * (col.x1 - col.x0))


_JUNK = re.compile(r"^(?:[|!¦\\_—–~`'\".,:;=]+|[-=]{2,})$")  # rule fragments, specks


_EDGE_JUNK = re.compile(r"^[\s_|~—=]+|[\s_|~—=]+$")


def _cell_text(words: list[Word]) -> str:
    ws = [w for w in words if not _JUNK.match(w.text)] if len(words) > 1 else list(words)
    txt = " ".join(l.text for l in group_lines(ws)) if ws else ""
    return _EDGE_JUNK.sub("", txt)  # a rule fragment glued to the text ('_PN-2026-A3')


def _band_to_values(band: list[Cell], cols: list[Column]) -> dict[str, TableCellValue]:
    vals: dict[str, TableCellValue] = {}
    for c in band:
        # a cell covering several columns (vertical rule lost): split its words
        # by column if they really fall into more than one
        if c.words and _spans(c, cols) >= 2:
            per: dict[str, list[Word]] = {}
            for w in c.words:
                col = next((k for k in cols if k.x0 <= w.cx <= k.x1), None)
                if col is not None:
                    per.setdefault(col.key, []).append(w)
            per = {k: v for k, v in per.items() if _cell_text(v)}
            if len(per) >= 2:
                for k, ws in per.items():
                    txt = _cell_text(ws)
                    if k in vals and vals[k].text:
                        txt = vals[k].text + " " + txt
                    vals[k] = TableCellValue(txt.strip(), mean_conf(ws),
                                             union_bbox([w.bbox for w in ws]), "multi", struct_conf=0.85)
                continue
        best, best_score = None, 0.0
        # Determine effective text center if words exist, else cell center
        cx = np.median([w.cx for w in c.words]) if c.words else (c.x0 + c.x1) / 2.0
        c_width = max(c.x1 - c.x0, 1e-3)
        for col in cols:
            ov = min(c.x1, col.x1) - max(c.x0, col.x0)
            if ov <= 0:
                continue
            col_width = max(col.x1 - col.x0, 1e-3)
            # Prioritize column that encloses the text center
            center_bonus = col_width if (col.x0 <= cx <= col.x1) else 0.0
            score = ov + center_bonus
            if score > best_score:
                best, best_score = col, score
        if best is None:
            continue
        txt = _cell_text(c.words) if c.words else c.text
        if best.key in vals and vals[best.key].text:
            txt = vals[best.key].text + " " + txt
        ov = min(c.x1, best.x1) - max(c.x0, best.x0)
        ov_frac = min(1.0, max(0.5, ov / c_width))
        struct_conf = round(0.85 if c.parent >= 0 else ov_frac, 3)
        if getattr(best, "inferred", False):
            struct_conf = round(min(struct_conf, 0.80), 3)
        vals[best.key] = TableCellValue(txt.strip(), c.conf if c.words else 1.0, c.bbox,
                                        "split" if c.parent >= 0 else "cell", struct_conf=struct_conf)
    for col in cols:
        vals.setdefault(col.key, TableCellValue("", 1.0, (col.x0, 0, col.x1, 0), struct_conf=1.0))
    return vals


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:30]


# ======================================================================
# lineless (text-aligned) tables
# ======================================================================

def find_text_tables(words: list[Word], vocab: dict[str, list[str]], kind: str,
                     dpi: float) -> list[Table]:
    """Detect tables with no (or only horizontal) ruling, from word alignment."""
    lines = group_lines(words)
    tables = []
    used_lines: set[int] = set()
    for li, line in enumerate(lines):
        if li in used_lines:
            continue
        cols = _header_tokens(line, vocab)
        if not cols:
            continue
        if not _is_header({c.key for c in cols}, kind):
            continue
        # expand header column extents to midpoints between neighbours
        bounds = []
        for k, c in enumerate(cols):
            left = (cols[k - 1].x1 + c.x0) / 2 if k else c.x0 - dpi * 0.3
            right = (c.x1 + cols[k + 1].x0) / 2 if k + 1 < len(cols) else c.x1 + dpi * 1.5
            bounds.append((left, right))
        pitch = statistics.median([l.bbox[3] - l.bbox[1] for l in lines]) * 1.9 or dpi * 0.2
        hx0, hx1 = bounds[0][0], bounds[-1][1]
        rows, row_bbs = [], []
        last_y = line.bbox[3]
        for lj in range(li + 1, len(lines)):
            ln = lines[lj]
            if ln.bbox[1] - last_y > pitch * 1.6:
                break
            ws = [w for w in ln.words if hx0 <= w.cx <= hx1]
            if not ws:
                break
            if _header_tokens(TextLine(ws), vocab):
                break
            vals = _words_to_columns(ws, cols, bounds)
            filled = [k for k, v in vals.items() if v.text]
            first = cols[0].key
            if rows and not vals[first].text and len(filled) <= 2:
                # continuation line (wrapped description etc.)
                for k in filled:
                    prev = rows[-1][k]
                    rows[-1][k] = TableCellValue((prev.text + " " + vals[k].text).strip(),
                                                 min(prev.conf, vals[k].conf), prev.bbox)
                row_bbs[-1] = union_bbox([row_bbs[-1], TextLine(ws).bbox])
            else:
                rows.append(vals)
                row_bbs.append(TextLine(ws).bbox)
            used_lines.add(lj)
            last_y = ln.bbox[3]
        if rows:
            hb = union_bbox([(c.x0, line.bbox[1], c.x1, line.bbox[3]) for c in cols])
            tables.append(Table(kind=kind, columns=cols, rows=rows, row_bboxes=row_bbs,
                                bbox=union_bbox([hb] + row_bbs), header_bbox=hb,
                                header_position="top", method="text"))
    return tables


def _header_tokens(line: TextLine, vocab) -> list[Column]:
    ws = line.words
    cols: list[Column] = []
    i = 0
    seen = set()
    while i < len(ws):
        hit = None
        for n in (3, 2, 1):
            if i + n > len(ws):
                continue
            seg = ws[i:i + n]
            # words in a header phrase must be close together
            if any(b.x0 - a.x1 > 1.2 * max(a.h, b.h) for a, b in zip(seg, seg[1:])):
                continue
            txt = " ".join(w.text for w in seg)
            fld, score, unit = match_header(txt, vocab)
            if fld and fld not in seen:
                hit = (n, fld, txt, seg, unit)
                break
        if hit:
            n, fld, txt, seg, unit = hit
            cols.append(Column(fld, txt, seg[0].x0, seg[-1].x1, unit))
            seen.add(fld)
            i += n
        else:
            i += 1
    return cols if len(cols) >= 3 else []


def _words_to_columns(ws, cols, bounds) -> dict[str, TableCellValue]:
    buckets: dict[str, list[Word]] = {c.key: [] for c in cols}
    for seg in split_segments(TextLine(sorted(ws, key=lambda w: w.x0)), gap_factor=1.6):
        sx0 = seg.words[0].x0
        best, best_ov = None, -1e9
        for c, (l, r) in zip(cols, bounds):
            ov = min(seg.bbox[2], r) - max(sx0, l)
            if l <= sx0 <= r:
                ov += 1e6  # left edge inside column wins (left-aligned text)
            if ov > best_ov:
                best, best_ov = c, ov
        buckets[best.key].extend(seg.words)
    out = {}
    for c in cols:
        b = buckets[c.key]
        out[c.key] = TableCellValue(" ".join(w.text for w in sorted(b, key=lambda w: w.x0)),
                                    mean_conf(b) if b else 1.0,
                                    union_bbox([w.bbox for w in b]) if b else (c.x0, 0, c.x1, 0),
                                    src="text", struct_conf=0.85)
    return out


# ======================================================================
# title block
# ======================================================================

def title_block_cells(groups: list[list[Cell]], used: set[int],
                      title_vocab: dict[str, list[str]]) -> list[Cell]:
    picked: list[Cell] = []
    scored = []
    for g in groups:
        rem = [c for c in g if c.id not in used]
        flds = set()
        for c in rem:
            if c.words:
                f, _, _ = match_label_prefix(c.text, title_vocab)
                if f:
                    flds.add(f)
        scored.append((len(flds), rem, flds))

    # Primary selection: groups with >= 2 fields including a key title field
    for n, rem, flds in sorted(scored, key=lambda x: -x[0]):
        if n >= 2 and (flds & {"drawing_number", "drawing_title", "drawn_by", "scale", "date"}):
            picked.extend(rem)

    # Spatially associated secondary selection:
    # If a title block was detected, include separate adjacent cell groups that contain
    # title fields (such as a separate revision-only box containing REV label and value)
    if picked:
        tb_box = union_bbox([c.bbox for c in picked])
        tb_h = max(tb_box[3] - tb_box[1], 10.0)
        tb_w = max(tb_box[2] - tb_box[0], 10.0)
        max_dist_x = max(tb_w * 0.75, 400.0)
        max_dist_y = max(tb_h * 1.5, 400.0)

        picked_ids = {c.id for c in picked}
        for n, rem, flds in scored:
            if not rem or any(c.id in picked_ids for c in rem):
                continue
            # Include if group contains revision or another title field and sits near the title block
            if flds & {"revision", "sheet", "scale", "date", "drawn_by", "checked_by", "approved_by"}:
                g_box = union_bbox([c.bbox for c in rem])
                dx = max(0.0, max(tb_box[0], g_box[0]) - min(tb_box[2], g_box[2]))
                dy = max(0.0, max(tb_box[1], g_box[1]) - min(tb_box[3], g_box[3]))
                if dx <= max_dist_x and dy <= max_dist_y:
                    picked.extend(rem)
                    picked_ids.update(c.id for c in rem)
    return picked


_TB_KEY = {"drawing_number", "drawing_title", "drawn_by", "scale", "sheet", "revision", "date",
           "checked_by", "approved_by", "projection", "size"}


def text_title_cells(words: list[Word], vocab: dict[str, list[str]], dpi: float,
                     min_fields: int = 2) -> list[Cell]:
    """Title block read from text layout alone, for sheets whose title-block
    rules are too broken to form cells (faint scans, traced drawings).
    Each label phrase ('DRAWING NO:', 'SCALE', 'DRAWN BY / DATE:') becomes a
    pseudo-cell holding the label and its value - the rest of its segment, or
    else the line directly below it. Only a tight cluster of such labels that
    includes a drawing number or title is accepted."""
    lines = group_lines(words)
    segs = []
    for l in lines:
        segs.extend(split_segments(l, gap_factor=2.0))
    lab = []
    for sg in segs:
        f, label, rest = match_label_prefix(sg.text, vocab)
        rest = rest.strip()
        if f in _TB_KEY and re.fullmatch(r"[/&+]\s*[A-Z .]{2,12}:?", rest, re.I):
            rest = ""  # combined label such as 'DRAWN BY / DATE:' - value below
        if f in _TB_KEY and (label.rstrip().endswith(":") or not rest or f in ("scale", "sheet")):
            lab.append((sg, f, rest))
    if len(lab) < min_fields:
        return []
    # cluster labels: link when boxes are within ~1 inch
    link = dpi * 1.0
    n = len(lab)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        a = lab[i][0].bbox
        for j in range(i + 1, n):
            b = lab[j][0].bbox
            dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
            dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
            if dx <= link and dy <= link:
                parent[find(i)] = find(j)
    comps: dict[int, list[int]] = {}
    for i in range(n):
        comps.setdefault(find(i), []).append(i)
    best = max(comps.values(), key=lambda ix: len({lab[i][1] for i in ix}))
    flds = {lab[i][1] for i in best}
    if len(flds) < min_fields or not flds & {"drawing_number", "drawing_title"}:
        return []

    # Associate nearby isolated REV label/value if it sat slightly outside the initial cluster link
    if "revision" not in flds:
        best_bb = union_bbox([lab[i][0].bbox for i in best])
        for idx in range(n):
            if idx not in best and lab[idx][1] == "revision":
                rev_bb = lab[idx][0].bbox
                dx = max(0.0, max(best_bb[0], rev_bb[0]) - min(best_bb[2], rev_bb[2]))
                dy = max(0.0, max(best_bb[1], rev_bb[1]) - min(best_bb[3], rev_bb[3]))
                if dx <= dpi * 3.5 and dy <= dpi * 2.5:
                    best.append(idx)
                    flds.add("revision")
                    break

    used = {id(lab[i][0]) for i in best}
    out = []
    for i in best:
        sg, f, rest = lab[i]
        ws = list(sg.words)
        if not rest:
            x0, y0, x1, y1 = sg.bbox
            h = max(y1 - y0, 1.0)
            # Try right neighbour on the same line first (e.g. 'REV: 1' or 'REV' [gap] 'A')
            right = [o for o in segs if id(o) not in used
                     and o.bbox[0] >= x0 and o.bbox[0] - x1 <= 4.0 * h
                     and abs((o.bbox[1] + o.bbox[3]) - (y0 + y1)) <= 1.2 * h]
            right = [o for o in right if not match_label_prefix(o.text, vocab)[0]]
            if right:
                v = min(right, key=lambda o: o.bbox[0])
                used.add(id(v))
                ws += list(split_segments(v, gap_factor=1.2)[0].words)
            else:
                # Value on the line below, overlapping the label horizontally
                below = [o for o in segs if id(o) not in used and o.bbox[1] > y1 - 0.2 * h
                         and o.bbox[1] - y1 <= 2.5 * h
                         and min(x1 + 4 * h, o.bbox[2]) - max(x0 - h, o.bbox[0]) > 0]
                below = [o for o in below if not match_label_prefix(o.text, vocab)[0]]
                if below:
                    v = min(below, key=lambda o: (o.bbox[1], abs(o.bbox[0] - x0)))
                    used.add(id(v))
                    # a value is one phrase: stop at the first wide gap
                    ws += list(split_segments(v, gap_factor=1.2)[0].words)
        bb = union_bbox([w.bbox for w in ws])
        out.append(Cell(*bb, words=ws, id=next(_VID)))
    return out


# ======================================================================
# notes
# ======================================================================

_NOTES_HEAD = re.compile(r"^\s*((?:GENERAL|TECHNICAL|DRAWING|MANUFACTURING|ASSEMBLY)\s+NOTES?|NOTES|NOTE|"
                         r"TECHNICAL\s+REQUIREMENTS|SPECIFICATIONS?)\s*[:.\-_'\"‘'’`]*\s*$", re.I)
_NOTES_HEAD_INLINE = re.compile(r"^\s*((?:GENERAL|TECHNICAL)\s+NOTES|NOTES)\s*[:.\-]\s*\S", re.I)
_HEAD_PREFIX = re.compile(r"^(GENERAL|TECHNICAL|DRAWING|MANUFACTURING|ASSEMBLY)$", re.I)
_NUM = re.compile(r"^\s*(\d{1,2})\s*[.)\]]\s*")


def find_notes(words: list[Word], dpi: float) -> list[tuple[list[TextLine], tuple]]:
    """Find NOTES blocks among free (non-table) words.
    Returns [(lines, bbox)]; the heading line is excluded from lines."""
    lines = group_lines(words)
    segs: list[TextLine] = []
    for l in lines:
        segs.extend(split_segments(l, gap_factor=3.0))
    segs.sort(key=lambda s: (s.bbox[1], s.bbox[0]))
    blocks = []
    taken: set[int] = set()
    for i, s in enumerate(segs):
        if i in taken:
            continue
        head = _NOTES_HEAD.match(s.text) or _NOTES_HEAD_INLINE.match(s.text)
        if not head:
            continue
        hx0 = s.bbox[0]
        h = min(w.h for w in s.words) or dpi * 0.1
        # an underlined heading is often read as two lines ("TECHNICAL" / "NOTES:"):
        # take a qualifier word just left of the heading as part of it
        for k, o in enumerate(segs):
            if k == i or k in taken or not _HEAD_PREFIX.match(o.text.strip()):
                continue
            if o.bbox[2] <= hx0 and hx0 - o.bbox[2] < 3 * h and \
                    min(o.bbox[3], s.bbox[3]) - max(o.bbox[1], s.bbox[1]) > 0:
                hx0 = o.bbox[0]
                taken.add(k)
                h = min(h, min(w.h for w in o.words))
        body: list[TextLine] = []
        if _NOTES_HEAD_INLINE.match(s.text) and not _NOTES_HEAD.match(s.text):
            rest = re.sub(r"^\s*(GENERAL\s+NOTES|NOTES)\s*[:.\-]\s*", "", s.text, flags=re.I)
            body.append(TextLine([Word(rest, s.bbox[0], s.bbox[1], s.bbox[2], s.bbox[3],
                                       s.conf)]))
        last = s.bbox[3]
        x_right = None
        for j in range(i + 1, len(segs)):
            t = segs[j]
            if j in taken:
                continue
            if t.bbox[1] - last > 2.8 * h:
                if t.bbox[1] > last:
                    # segments are sorted by y; once a gap appears, stop scanning
                    if all(segs[k].bbox[1] - last > 2.8 * h for k in range(j, min(j + 3, len(segs)))):
                        break
                continue
            if t.bbox[0] < hx0 - 1.5 * h or t.bbox[0] > hx0 + 6 * h:
                continue  # different column of text
            if x_right and t.bbox[0] > x_right:
                continue
            body.append(t)
            taken.add(j)
            last = max(last, t.bbox[3])
            x_right = max(x_right or 0, t.bbox[2])
        if body:
            blocks.append((body, union_bbox([s.bbox] + [b.bbox for b in body])))
    return blocks


def split_numbered_notes(lines: list[TextLine]) -> list[dict]:
    items: list[dict] = []
    numbered = any(_NUM.match(l.text) for l in lines)
    num_x = min((l.bbox[0] for l in lines if _NUM.match(l.text)), default=None)
    prev = None
    for l in lines:
        m = _NUM.match(l.text)
        lh = statistics.median([w.h for w in l.words]) if l.words else 1
        new_unnumbered = False
        if not m and items and numbered and prev is not None:
            # a continuation line is indented past the number and follows closely;
            # an unnumbered line at the number column after a gap is its own note
            at_num_col = num_x is not None and l.bbox[0] <= num_x + 0.6 * lh
            gap = l.bbox[1] - prev.bbox[3]
            new_unnumbered = at_num_col and (gap > 0.3 * lh or items[-1].get("standalone"))
        prev = l
        if m or not items or new_unnumbered:
            num = m.group(1) if m else None
            text = _NUM.sub("", l.text, count=1) if m else l.text
            items.append({"number": num, "text": text.strip(), "conf": l.conf, "bbox": l.bbox,
                          "standalone": bool(new_unnumbered)})
        else:
            items[-1]["text"] = (items[-1]["text"] + " " + l.text).strip()
            items[-1]["conf"] = min(items[-1]["conf"], l.conf)
            items[-1]["bbox"] = union_bbox([items[-1]["bbox"], l.bbox])
    return items
