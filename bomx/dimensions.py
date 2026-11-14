"""Dimension extraction and normalization for engineering drawings.

Extracts linear dimensions, diameters, radii, threads, chamfers, angles,
and toleranced dimensions from CAD entities, digital vector text, and OCR.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Optional

from .models import BBox, Dimension, Measurement, Word

# DimensionCallout is an alias for Dimension model
DimensionCallout = Dimension

# Common engineering dimension symbols
_SYM_MAP = {
    "%%C": "Ø", "%%c": "Ø", "\\U+2205": "Ø", "\u2205": "Ø",
    "%%P": "±", "%%p": "±", "\\U+00B1": "±", "\u00b1": "±",
    "%%D": "°", "%%d": "°", "\\U+00B0": "°", "\u00b0": "°",
    "%%127": "°", "DEG": "°",
}

# Regex patterns for dimension callouts
_PREFIX_RX = r"(?:(?P<qty>\d{1,3})\s*[xX]\s*)?(?P<pfx>Ø|DIA|DIAM|R|SR|M|G|TR|UNC|UNF)?\s*"
_NUM_RX = r"(?P<nom>\d+(?:\.\d+)?)"
_TOL_PM_RX = r"(?:\s*(?:±|\+/-)\s*(?P<tol_pm>\d+(?:\.\d+)?))"
_TOL_LIMIT_RX = r"(?:\s*(?P<tol_plus>\+\d+(?:\.\d+)?)\s*/\s*(?P<tol_minus>-\d+(?:\.\d+)?))"
_FIT_RX = r"(?:\s*(?P<fit>[A-Za-z]{1,2}\d{1,2}))"
_SUFFIX_RX = r"(?:\s*(?P<sfx>THRU|TYP|TYPICAL|MIN|MAX|REF|EQ\s*SP|EQUISPACED|PLCS|PLACES|DEEP|DP|\↧|\|\⌵))?"

_FULL_DIM_RX = re.compile(
    rf"^{_PREFIX_RX}{_NUM_RX}(?:{_TOL_PM_RX}|{_TOL_LIMIT_RX}|{_FIT_RX})?{_SUFFIX_RX}$",
    re.I
)

# Thread pattern: M10x1.5, M12 - 6H, G 1/2", 1/4-20 UNC
_THREAD_RX = re.compile(
    r"\b(?P<thread>(?:M\d+(?:\s*[xX×]\s*\d+(?:\.\d+)?)?|G\s*\d+/\d+\"?|\d+/\d+-\d+\s*(?:UNC|UNF|UNEF|UN))"
    r"(?:\s*-\s*[4-8][HhGg](?:[4-8][HhGg])?)?)"
    r"(?:\s*(?:THRU|DEEP|DP|x\s*\d+(?:\.\d+)?|\↧\s*\d+))?",
    re.I
)

# Chamfer pattern: 2x45°, C2, 1.5 x 45 DEG
_CHAMFER_RX = re.compile(
    r"\b(?:(?P<c1>C\s*\d+(?:\.\d+)?)|(?P<c2>\d+(?:\.\d+)?\s*[xX×]\s*45\s*(?:°|DEG)?))\b",
    re.I
)

# Angular dimension: 45°, 30.5°, 90° 30'
_ANGLE_RX = re.compile(
    r"\b(?P<ang>\d+(?:\.\d+)?)\s*°(?:\s*(?P<min>\d+)['′])?\b"
)


def normalize_dim_symbols(text: str) -> str:
    """Replace CAD formatting codes (%%c, %%p, %%d) with standard symbols."""
    t = text
    for k, v in _SYM_MAP.items():
        t = t.replace(k, v)
    # AutoCAD MTEXT formatting tags: \A1; \H0.7x; etc.
    t = re.sub(r"\\[A-Za-z0-9]+;?", "", t)
    # AutoCAD stacking: \S+0.05^-0.02;
    t = re.sub(r"\\S([^^;#]+)\^([^^;#]+);?", r" +\1/-\2", t)
    t = re.sub(r"[{}\\]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_dimension(text: str, bbox: Optional[BBox] = None, page: int = 0,
                    conf: float = 1.0) -> Optional[DimensionCallout]:
    """Parse a single text string into a DimensionCallout if it represents a dimension."""
    clean = normalize_dim_symbols(text.strip())
    if not clean or len(clean) > 50:
        return None

    # Check chamfer
    m_ch = _CHAMFER_RX.search(clean)
    if m_ch:
        nom = None
        if m_ch.group("c1"):
            nom_str = re.sub(r"[^\d.]", "", m_ch.group("c1"))
            nom = float(nom_str) if nom_str else None
        elif m_ch.group("c2"):
            nom_str = m_ch.group("c2").split("x")[0].split("X")[0].strip()
            nom = float(nom_str) if nom_str else None
        return DimensionCallout(text=clean, nominal=nom, prefix="C", dim_type="chamfer",
                                raw=text, bbox=bbox, page=page, confidence=conf)

    # Check thread
    m_th = _THREAD_RX.search(clean)
    if m_th:
        th_val = m_th.group("thread")
        num_m = re.search(r"\d+(?:\.\d+)?", th_val)
        nom = float(num_m.group(0)) if num_m else None
        pfx = "M" if th_val.upper().startswith("M") else "G" if th_val.upper().startswith("G") else "THREAD"
        return DimensionCallout(text=clean, nominal=nom, prefix=pfx, dim_type="thread",
                                raw=text, bbox=bbox, page=page, confidence=conf)

    # Check angle
    m_ang = _ANGLE_RX.search(clean)
    if m_ang and not any(p in clean.upper() for p in ("ISO", "DIN", "ANSI", "SCALE", "REV")):
        nom = float(m_ang.group("ang"))
        if m_ang.group("min"):
            nom += float(m_ang.group("min")) / 60.0
        return DimensionCallout(text=clean, nominal=nom, suffix="°", dim_type="angle",
                                raw=text, bbox=bbox, page=page, confidence=conf)

    # Full standard dimension
    m = _FULL_DIM_RX.match(clean)
    if not m:
        # Try matching substring if surrounded by standard delimiters
        if any(c in clean for c in ("Ø", "±", "H7", "g6", "h6", "js6")):
            for token in clean.split(";"):
                token = token.strip()
                m = _FULL_DIM_RX.match(token)
                if m:
                    clean = token
                    break
    if not m:
        return None

    nom_val = float(m.group("nom"))
    pfx = (m.group("pfx") or "").upper()
    qty = m.group("qty")
    if qty:
        pfx = f"{qty}x {pfx}".strip()

    tol = None
    if m.group("tol_pm"):
        tol = f"±{m.group('tol_pm')}"
    elif m.group("tol_plus") and m.group("tol_minus"):
        tol = f"{m.group('tol_plus')}/{m.group('tol_minus')}"
    elif m.group("fit"):
        tol = m.group("fit").upper()

    sfx = m.group("sfx")
    if sfx:
        sfx = sfx.upper()

    dim_type = "linear"
    if "Ø" in pfx or "DIA" in pfx:
        dim_type = "diameter"
    elif "R" in pfx or "SR" in pfx:
        dim_type = "radius"
    elif pfx.startswith("M") or pfx.startswith("G"):
        dim_type = "thread"

    return DimensionCallout(
        text=clean,
        nominal=nom_val,
        tolerance=tol,
        prefix=pfx or None,
        suffix=sfx,
        dim_type=dim_type,
        raw=text,
        bbox=bbox,
        page=page,
        confidence=conf
    )


def extract_dimensions_from_words(words: list[Word], page: int = 0) -> list[DimensionCallout]:
    """Find dimension callouts among words on a page."""
    dims: list[DimensionCallout] = []
    from .textutil import group_lines, split_segments
    for line in group_lines(words):
        for seg in split_segments(line, gap_factor=2.0):
            dim = parse_dimension(seg.text, bbox=seg.bbox, page=page, conf=seg.conf)
            if dim is not None:
                dims.append(dim)
    return dims


def dedupe_dimensions(dims: list[DimensionCallout]) -> list[DimensionCallout]:
    """Remove duplicate dimensions on the same page with identical values."""
    seen = set()
    out = []
    for d in dims:
        k = (d.page, d.dim_type, d.nominal, d.tolerance, d.prefix, d.text)
        if k in seen:
            continue
        seen.add(k)
        out.append(d)
    return out
