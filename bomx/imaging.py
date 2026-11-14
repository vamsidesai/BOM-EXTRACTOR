"""Image preprocessing (orientation, deskew, binarisation, ruling-line
detection) and Tesseract OCR wrappers."""
from __future__ import annotations

import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable, Optional

import cv2
import numpy as np
import pytesseract

from .models import Word

log = logging.getLogger(__name__)


def to_gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def binarize(gray: np.ndarray, scanned: bool, dpi: float) -> np.ndarray:
    """Return an inverted binary image (ink = 255)."""
    if scanned:
        g = cv2.medianBlur(gray, 3)
        block = int(dpi / 8) | 1
        return cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY_INV, max(block, 15), 15)
    _, b = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return b


# ------------------------------------------------------------ resolution

REF_GLYPH_MM = 2.4  # median glyph height of drawing lettering (calibrated on known-DPI scans)


def estimate_dpi_from_text(gray: np.ndarray) -> Optional[float]:
    """Estimate the effective resolution of a drawing image from the size of
    its lettering. Used when an image has no DPI metadata or carries a
    screen value (72/96 dpi) that says nothing about the drawing's scale -
    typical of screenshots, phone photos and exported/generated images."""
    h, w = gray.shape[:2]
    g = cv2.medianBlur(gray, 3)
    b = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    _, _, st, _ = cv2.connectedComponentsWithStats(b, connectivity=8)
    big = max(h, w)
    hs = [ch for x, y, cw, ch, a in st[1:]
          if big * 0.004 < ch < big * 0.04 and 0.15 < cw / ch < 1.5 and a > 0.15 * cw * ch]
    if len(hs) < 60:
        return None
    med = float(np.median(hs))
    return float(min(600.0, max(100.0, med / (REF_GLYPH_MM / 25.4))))


# ------------------------------------------------------------ orientation

def detect_orientation(gray: np.ndarray) -> int:
    """Use Tesseract OSD to find a 0/90/180/270 rotation. Returns the
    clockwise rotation (degrees) to apply to make the page upright."""
    h, w = gray.shape
    s = min(1.0, 3500 / max(h, w))
    small = cv2.resize(gray, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else gray
    osd_rot, osd_conf = 0, 0.0
    try:
        osd = pytesseract.image_to_osd(small, config="--psm 0 -c min_characters_to_try=20")
        rot = re.search(r"Rotate:\s+(\d+)", osd)
        conf = re.search(r"Orientation confidence:\s+([\d.]+)", osd)
        if rot and conf:
            osd_rot, osd_conf = int(rot.group(1)) % 360, float(conf.group(1))
    except pytesseract.TesseractError as e:  # not enough text, etc.
        log.debug("OSD failed: %s", e)
    if osd_conf >= 2.0:
        return osd_rot
    # OSD unsure (sparse text is typical of drawings): compare OCR quality
    # of the candidate orientations on a reduced image.
    s2 = min(1.0, 2200 / max(h, w))
    probe = cv2.resize(gray, (int(w * s2), int(h * s2)), interpolation=cv2.INTER_AREA)
    cands = sorted({0, osd_rot, 90, 270})
    scores = {r: _orientation_score(rotate_quadrant(probe, r)) for r in cands}
    best = max(scores, key=scores.get)
    log.debug("orientation scores %s (osd %s @ %.2f)", scores, osd_rot, osd_conf)
    if best != 0 and scores[best] > 1.3 * scores[0] + 5:
        return best
    return 0


def _orientation_score(img: np.ndarray) -> float:
    try:
        d = pytesseract.image_to_data(img, config="--psm 11", output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractError:
        return 0.0
    sc = 0.0
    for t, c in zip(d["text"], d["conf"]):
        t = (t or "").strip()
        try:
            c = float(c)
        except (TypeError, ValueError):
            continue
        if c >= 70 and len(t) >= 3 and sum(ch.isalnum() for ch in t) >= 3:
            sc += c / 100 * len(t)
    return sc


def rotate_quadrant(img: np.ndarray, deg_cw: int) -> np.ndarray:
    if deg_cw == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if deg_cw == 180:
        return cv2.rotate(img, cv2.ROTATE_180)
    if deg_cw == 270:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


# ------------------------------------------------------------ deskew

def estimate_skew(bin_inv: np.ndarray, dpi: float) -> float:
    """Estimate page skew (degrees, + = counter-clockwise) from long ruling
    lines (border, table rules), which every engineering drawing has."""
    h, w = bin_inv.shape
    s = min(1.0, 3000 / max(h, w))
    b = cv2.resize(bin_inv, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else bin_inv
    _, b = cv2.threshold(b, 127, 255, cv2.THRESH_BINARY)
    min_len = int(b.shape[1] * 0.12)
    lines = cv2.HoughLinesP(b, 1, math.pi / 1800, threshold=max(80, min_len // 2),
                            minLineLength=min_len, maxLineGap=int(dpi * s * 0.02) + 2)
    if lines is None:
        return 0.0
    angles, weights = [], []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        dx, dy = x2 - x1, y2 - y1
        ang = math.degrees(math.atan2(dy, dx))
        if ang > 90:
            ang -= 180
        if ang < -90:
            ang += 180
        if abs(ang) <= 10:  # near-horizontal
            angles.append(-ang)
            weights.append(math.hypot(dx, dy))
        elif abs(abs(ang) - 90) <= 10:  # near-vertical
            a = ang - 90 if ang > 0 else ang + 90
            angles.append(-a)
            weights.append(math.hypot(dx, dy))
    if len(angles) < 3:
        return 0.0
    order = np.argsort(angles)
    a, wt = np.array(angles)[order], np.array(weights)[order]
    cum = np.cumsum(wt)
    return float(a[np.searchsorted(cum, cum[-1] / 2)])  # weighted median


def rotate_small(img: np.ndarray, angle_deg: float) -> np.ndarray:
    if abs(angle_deg) < 0.05:
        return img
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), -angle_deg, 1.0)
    border = 255 if img.ndim == 2 else (255, 255, 255)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=border)


# ------------------------------------------------------------ ruling lines

def line_masks(bin_inv: np.ndarray, dpi: float) -> tuple[np.ndarray, np.ndarray]:
    """Isolate horizontal and vertical ruling lines with morphology."""
    hk = max(20, int(dpi * 0.30))  # 7.5 mm
    vk = max(15, int(dpi * 0.16))  # 4 mm  (taller than drawing text strokes)
    hm = cv2.morphologyEx(bin_inv, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (hk, 1)))
    vm = cv2.morphologyEx(bin_inv, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, vk)))
    # bridge small breaks at junctions / scan dropouts
    gap = max(3, int(dpi * 0.015))
    hm = cv2.morphologyEx(hm, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (gap, 1)))
    vm = cv2.morphologyEx(vm, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, gap)))
    # Large/bold lettering has strokes as long as short ruling lines. A real
    # ruling line is either long, or meets a perpendicular ruling at an end.
    hm0, vm0 = hm.copy(), vm.copy()
    vm = _keep_connected(vm0, hm0, dpi, vertical=True)
    hm = _keep_connected(hm0, vm0, dpi, vertical=False)
    # hand-drawn / scanned tables: a rule often stops a little short of the
    # rule it should meet, which leaves neighbouring cells merged. Extend
    # line ends to a perpendicular rule found within a small reach.
    hm = _bridge_ends(hm, vm, dpi, vertical=False)
    vm = _bridge_ends(vm, hm, dpi, vertical=True)
    return hm, vm


def _bridge_ends(mask: np.ndarray, other: np.ndarray, dpi: float, vertical: bool) -> np.ndarray:
    reach = max(6, int(dpi * 0.12))  # ~3 mm
    min_len = dpi * 0.15
    out = mask.copy()
    H, W = mask.shape
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    for i in range(1, n):
        x, y, w, h, _ = (int(v) for v in stats[i])
        if (h if vertical else w) < min_len:
            continue
        if not vertical:
            band = slice(max(y - 1, 0), min(y + h + 1, H))
            # right end
            seg = other[band, x + w: min(x + w + reach, W)]
            cols = np.where(seg.any(axis=0))[0]
            if len(cols) and cols[0] > 0:
                out[y:y + h, x + w: x + w + cols[0] + 1] = 255
            # left end
            seg = other[band, max(x - reach, 0): x]
            cols = np.where(seg.any(axis=0))[0]
            if len(cols) and cols[-1] < seg.shape[1] - 1:
                out[y:y + h, max(x - reach, 0) + cols[-1]: x] = 255
        else:
            band = slice(max(x - 1, 0), min(x + w + 1, W))
            seg = other[y + h: min(y + h + reach, H), band]
            rows = np.where(seg.any(axis=1))[0]
            if len(rows) and rows[0] > 0:
                out[y + h: y + h + rows[0] + 1, x:x + w] = 255
            seg = other[max(y - reach, 0): y, band]
            rows = np.where(seg.any(axis=1))[0]
            if len(rows) and rows[-1] < seg.shape[0] - 1:
                out[max(y - reach, 0) + rows[-1]: y, x:x + w] = 255
    return out


def _keep_connected(mask: np.ndarray, other: np.ndarray, dpi: float, vertical: bool) -> np.ndarray:
    long_len = dpi * (0.45 if vertical else 0.8)
    reach = max(4, int(dpi * 0.02))
    probe = cv2.dilate(other, np.ones((reach * 2 + 1, reach * 2 + 1), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros(n, dtype=bool)
    H, W = mask.shape
    for i in range(1, n):
        x, y, w, h, _ = stats[i]
        length = h if vertical else w
        if length >= long_len:
            keep[i] = True
            continue
        if vertical:
            ends = [(slice(y, min(y + reach, H)), slice(x, x + w)),
                    (slice(max(y + h - reach, 0), y + h), slice(x, x + w))]
        else:
            ends = [(slice(y, y + h), slice(x, min(x + reach, W))),
                    (slice(y, y + h), slice(max(x + w - reach, 0), x + w))]
        keep[i] = any(probe[e].any() for e in ends)
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def remove_lines(gray: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """Paint ruling lines white so OCR is not confused by table borders."""
    clean = gray.copy()
    clean[cv2.dilate(grid, np.ones((3, 3), np.uint8)) > 0] = 255
    return clean


# ------------------------------------------------------------ OCR

_ALNUM = re.compile(r"[A-Za-z0-9]")


def ocr_image(gray: np.ndarray, dpi: float, lang: str = "eng", psm: int = 11,
              min_conf: float = 25, offset: tuple[float, float] = (0, 0),
              whitelist: Optional[str] = None) -> list[Word]:
    """Run Tesseract and return words in the coordinate frame of the input
    (plus *offset*)."""
    scale = 1.0
    img = gray
    if dpi < 280:  # tesseract is happiest around 300 DPI
        scale = 300 / dpi
        img = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    cfg = f"--psm {psm} --dpi {int(dpi * scale)} -c preserve_interword_spaces=1"
    if whitelist:
        cfg += f" -c tessedit_char_whitelist={whitelist}"
    data = pytesseract.image_to_data(img, lang=lang, config=cfg,
                                     output_type=pytesseract.Output.DICT)
    words = []
    for i, txt in enumerate(data["text"]):
        txt = (txt or "").strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if not txt or conf < 0:
            continue
        if conf < min_conf and not _ALNUM.search(txt):
            continue
        if conf < min_conf * 0.6:
            continue
        x, y, w, h = (data[k][i] / scale for k in ("left", "top", "width", "height"))
        words.append(Word(txt, x + offset[0], y + offset[1], x + w + offset[0], y + h + offset[1],
                          conf / 100.0))
    return words


def ocr_cells(clean_gray: np.ndarray, cells: Iterable, dpi: float, lang: str,
              min_conf: float, workers: int = 4) -> dict[int, list[Word]]:
    """OCR each table cell crop individually (block mode). Returns {cell.id: words}."""
    cells = list(cells)
    inset = max(2, int(dpi * 0.008))
    pad = max(8, int(dpi * 0.04))

    def run(cell):
        x0, y0 = int(cell.x0) + inset, int(cell.y0) + inset
        x1, y1 = int(cell.x1) - inset, int(cell.y1) - inset
        if x1 - x0 < 5 or y1 - y0 < 5:
            return cell.id, []
        crop = clean_gray[y0:y1, x0:x1]
        if crop.size == 0 or crop.min() > 160:  # blank cell
            return cell.id, []
        # crop to the ink (ignores speckle and leftovers of the ruling lines)
        ink = cv2.medianBlur(crop, 3) < 150
        ys, xs = np.where(ink)
        if len(ys) < 6:
            return cell.id, []
        ix0, ix1, iy0, iy1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        inkw, inkh = ix1 - ix0, iy1 - iy0
        m = max(2, int(dpi * 0.01))
        sub = crop[max(iy0 - m, 0):iy1 + m, max(ix0 - m, 0):ix1 + m]
        ix0, iy0 = max(ix0 - m, 0), max(iy0 - m, 0)
        # pad with the paper colour (pure white next to grey scan paper creates
        # an artificial edge that confuses Tesseract's segmentation)
        paper = int(np.median(crop))
        sub = cv2.copyMakeBorder(sub, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=paper)
        off = (x0 + ix0 - pad, y0 + iy0 - pad)
        if inkh < dpi * 0.2:  # single line
            ws = ocr_image(sub, dpi, lang, psm=7, min_conf=min_conf, offset=off)
            if inkw <= 1.8 * inkh:  # one or two characters: try char mode too
                alt = ocr_image(sub, dpi, lang, psm=10, min_conf=min_conf, offset=off)
                if alt and (not ws or _score(alt) > _score(ws)):
                    ws = alt
                txt = "".join(w.text for w in ws)
                if len(txt) == 2 and txt[0].upper() == txt[1].upper() and txt[0].isalpha():
                    ws = [Word(txt[0].upper(), ws[0].x0, ws[0].y0, ws[-1].x1, ws[-1].y1,
                               min(w.conf for w in ws))]
        else:  # multi-line / mixed sizes (e.g. small label + large value)
            ws = ocr_image(sub, dpi, lang, psm=11, min_conf=min_conf, offset=off)
            blk = ocr_image(sub, dpi, lang, psm=6, min_conf=min_conf, offset=off)
            if _score(blk) > _score(ws) * 1.1:
                ws = blk
        return cell.id, ws

    out: dict[int, list[Word]] = {}
    if workers <= 1 or len(cells) <= 1:
        for cell in cells:
            cid, ws = run(cell)
            out[cid] = ws
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for cid, ws in ex.map(run, cells):
                out[cid] = ws
    return out


def tesseract_available() -> Optional[str]:
    try:
        return str(pytesseract.get_tesseract_version())
    except Exception:  # pragma: no cover
        return None


def _score(ws: list[Word]) -> float:
    """Confidence-weighted amount of recognised text."""
    return sum(w.conf * sum(ch.isalnum() for ch in w.text) for w in ws)


def ocr_numeric(clean_gray: np.ndarray, bbox, dpi: float, lang: str,
                orig_text: Optional[str] = None) -> Optional[tuple[str, float]]:
    """Re-read one cell restricted to digits and decimals (for item / qty / mass columns).
    Tests multiple image preprocessing variants (scaled, contrast-enhanced, thresholded)
    to recover faint decimal points that standard single-pass OCR easily drops."""
    inset = max(2, int(dpi * 0.008))
    x0, y0, x1, y1 = int(bbox[0]) + inset, int(bbox[1]) + inset, int(bbox[2]) - inset, int(bbox[3]) - inset
    orig_crop = clean_gray[max(y0, 0):y1, max(x0, 0):x1]
    if orig_crop.size == 0:
        return None

    pad = max(8, int(dpi * 0.04))
    crop = cv2.copyMakeBorder(orig_crop, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=int(np.median(orig_crop)))

    # Generate preprocessing variants:
    # 1. Base padded crop
    # 2. Scaled up 2x (helps Tesseract preserve small 1-2px dots)
    # 3. CLAHE contrast enhanced (boosts faint decimal marks near numbers)
    # 4. Otsu binarized
    variants = [crop]
    try:
        scaled = cv2.resize(crop, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        variants.append(scaled)
    except Exception:
        scaled = crop

    try:
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4))
        variants.append(clahe.apply(scaled))
    except Exception:
        pass

    try:
        _, otsu = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        variants.append(otsu)
    except Exception:
        pass

    candidates: list[tuple[str, float, bool]] = []
    for var in variants:
        var_dpi = dpi * 2.0 if var.shape[0] > crop.shape[0] else dpi
        for psm in (7, 8):
            ws = ocr_image(var, var_dpi, lang, psm=psm, min_conf=0, whitelist="0123456789.,")
            if ws:
                txt = "".join(w.text for w in ws).strip()
                if txt:
                    conf = min(w.conf for w in ws)
                    has_dot = "." in txt or "," in txt
                    candidates.append((txt, conf, has_dot))

    if not candidates:
        return None

    def _digits(s: str) -> str:
        s_fixed = s.translate(str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8"}))
        return re.sub(r"\D", "", s_fixed)

    orig_digits = _digits(orig_text) if orig_text else None
    if not orig_digits and candidates:
        # If no explicit orig_text provided, baseline digits come from untransformed base crop
        orig_digits = _digits(candidates[0][0])

    # Compare OCR outputs:
    # Do not blindly prefer a decimal candidate unless its digits agree with the original OCR digits.
    # A preprocessing variant producing a different number must not win simply because it contains a dot.
    matching_decimal_cands = []
    for c in candidates:
        if c[2] and re.search(r"\d+[.,]\d+", c[0]):
            c_digits = _digits(c[0])
            if orig_digits and c_digits == orig_digits:
                matching_decimal_cands.append(c)

    if matching_decimal_cands:
        matching_decimal_cands.sort(key=lambda x: x[1], reverse=True)
        return (matching_decimal_cands[0][0], matching_decimal_cands[0][1])

    # If no digit-matching decimal candidate exists, prefer candidates matching orig_digits
    if orig_digits:
        matching_cands = [c for c in candidates if _digits(c[0]) == orig_digits]
        if matching_cands:
            matching_cands.sort(key=lambda x: x[1], reverse=True)
            return (matching_cands[0][0], matching_cands[0][1])

    # Fallback to highest confidence candidate among all
    candidates.sort(key=lambda x: x[1], reverse=True)
    return (candidates[0][0], candidates[0][1])


def find_tesseract(explicit: Optional[str] = None) -> Optional[str]:
    """Locate the tesseract executable (explicit path, PATH, then the usual
    Windows / macOS install folders) and point pytesseract at it."""
    import os
    import shutil
    cands = [explicit] if explicit else []
    cands.append(shutil.which("tesseract"))
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""))):
        if base:
            cands.append(os.path.join(base, "Tesseract-OCR", "tesseract.exe"))
    home = os.path.expanduser("~")
    cands += [os.path.join(home, "scoop", "shims", "tesseract.exe"),
              os.path.join(home, "scoop", "apps", "tesseract", "current", "tesseract.exe"),
              os.path.join(home, "AppData", "Local", "Programs", "Tesseract-OCR", "tesseract.exe"),
              os.path.join(home, "Tesseract-OCR", "tesseract.exe"),
              r"C:\Tesseract-OCR\tesseract.exe",
              "/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract", "/usr/bin/tesseract"]
    for c in cands:
        if c and os.path.isfile(c):
            pytesseract.pytesseract.tesseract_cmd = c
            # Ensure TESSDATA_PREFIX is valid
            curr_prefix = os.environ.get("TESSDATA_PREFIX")
            if not curr_prefix or not os.path.exists(curr_prefix):
                proj_tessdata = Path(__file__).resolve().parents[1] / "tessdata"
                if proj_tessdata.is_dir() and (proj_tessdata / "eng.traineddata").exists():
                    os.environ["TESSDATA_PREFIX"] = str(proj_tessdata)
                else:
                    cand_tess = Path(c).parent / "tessdata"
                    if cand_tess.is_dir() and (cand_tess / "eng.traineddata").exists():
                        os.environ["TESSDATA_PREFIX"] = str(cand_tess)
            return c
    return None


def bridge_dashed_rules(binv: np.ndarray, dpi: float, max_gap_mm: float = 3.5,
                        min_len_mm: float = 12.0) -> tuple[np.ndarray, np.ndarray]:
    """Repair ruling lines that were found only in part because the rest
    survives as dash fragments (faint rules lost by a raster-to-vector trace
    or a light scan).

    Only thin, flat ink fragments are bridged - lettering strokes belong to
    their glyphs and are not separate thin components. Rules already found in
    the other direction are set aside first, so a fragment touching a border
    still counts. A bridged run is kept only if it is long and continues a
    rule that was already detected: a rule is repaired, never invented from
    specks (that would split some cells of a table row and not others)."""
    px = dpi / 25.4
    thick = max(2, int(round(0.5 * px)))
    gap = max(3, int(round(max_gap_mm * px)))
    min_len = int(round(min_len_mm * px))
    hm, vm = line_masks(binv, dpi)
    out = binv.copy()
    specks = np.zeros_like(binv)
    for horiz in (True, False):
        own = hm if horiz else vm
        src = binv.copy()
        src[(vm if horiz else hm) > 0] = 0
        n, lab, st, _ = cv2.connectedComponentsWithStats((src > 0).astype(np.uint8), connectivity=8)
        if n <= 1:
            continue
        w, h = st[:, 2], st[:, 3]
        sel = (h <= thick) & (w >= 2 * h) if horiz else (w <= thick) & (h >= 2 * w)
        sel[0] = False
        if not sel.any():
            continue
        frag = (sel[lab]).astype(np.uint8) * 255
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (gap, 1) if horiz else (1, gap))
        closed = cv2.morphologyEx(frag, cv2.MORPH_CLOSE, k)
        m2, lab2, st2, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
        if m2 <= 1:
            continue
        length = st2[:, 2] if horiz else st2[:, 3]
        # which runs contain part of an already-detected rule
        has_rule = np.zeros(m2, bool)
        has_rule[np.unique(lab2[(own > 0) & (closed > 0)])] = True
        # a dashed run: long, made of several fragments
        nfrag = np.bincount(lab2[frag > 0], minlength=m2)
        dashed = (length >= min_len) & (nfrag >= 3)
        dashed[0] = False
        specks[(frag > 0) & dashed[lab2]] = 255
        keep = (length >= min_len) & has_rule
        keep[0] = False
        if keep.any():
            out[keep[lab2]] = 255
    return out, specks


def close_open_table_sides(hm: np.ndarray, vm: np.ndarray, dpi: float,
                           min_rules: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Add the missing outer rule of a table drawn open on one side - typically
    a parts list that runs to the edge of a scan or trace, so its right (or
    top) border was never captured. Three or more rules ending at the same
    place with no perpendicular rule there get one drawn along their ends."""
    px = dpi / 25.4
    tol = max(3, int(round(1.0 * px)))
    t = max(2, int(round(0.35 * px)))
    hm, vm = hm.copy(), vm.copy()
    for horiz in (True, False):
        own, perp = (hm, vm) if horiz else (vm, hm)
        n, lab, st, _ = cv2.connectedComponentsWithStats((own > 0).astype(np.uint8), connectivity=8)
        if n <= 1:
            continue
        min_len = 8 * px
        segs = []
        for i in range(1, n):
            x, y, w, h, _ = st[i]
            if (w if horiz else h) >= min_len:
                segs.append((x, y, w, h))
        for end in (0, 1):  # start / end of the rules
            pos = [((s[0] + s[2] - 1) if end else s[0]) if horiz else ((s[1] + s[3] - 1) if end else s[1])
                   for s in segs]
            order = np.argsort(pos)
            i = 0
            while i < len(order):
                grp = [order[i]]
                j = i + 1
                while j < len(order) and pos[order[j]] - pos[grp[0]] <= tol:
                    grp.append(order[j])
                    j += 1
                i = j
                # only rules of one table: consecutive rules close together
                cross = (lambda k: segs[k][1]) if horiz else (lambda k: segs[k][0])
                grp.sort(key=cross)
                runs, cur = [], [grp[0]]
                for k in grp[1:]:
                    if cross(k) - cross(cur[-1]) <= 25 * px:
                        cur.append(k)
                    else:
                        runs.append(cur)
                        cur = [k]
                runs.append(cur)
                for run in runs:
                    _close_run(run, segs, pos, perp, horiz, min_rules, tol, t, px)
    return hm, vm


def _close_run(grp, segs, pos, perp, horiz, min_rules, tol, t, px):
    """Draw the missing closing rule along the ends of one table's rules."""
    if len(grp) < min_rules:
        return
    at = int(np.median([pos[k] for k in grp]))
    if horiz:
        lo = min(segs[k][1] for k in grp)
        hi = max(segs[k][1] + segs[k][3] for k in grp)
        region = perp[lo:hi, max(at - tol, 0):at + tol + 1]
    else:
        lo = min(segs[k][0] for k in grp)
        hi = max(segs[k][0] + segs[k][2] for k in grp)
        region = perp[max(at - tol, 0):at + tol + 1, lo:hi]
    span = hi - lo
    covered = (region > 0).any(axis=1 if horiz else 0).mean() if region.size else 0
    if span < 6 * px or covered > 0.6:
        return  # the closing rule is there already
    if horiz:
        cv2.line(perp, (at, lo), (at, hi - 1), 255, t)
    else:
        cv2.line(perp, (lo, at), (hi - 1, at), 255, t)
