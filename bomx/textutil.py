"""Text helpers: line grouping, normalisation and fuzzy label matching."""
from __future__ import annotations

import re
import statistics
from difflib import SequenceMatcher
from typing import Iterable, Optional

from .models import TextLine, Word

_PUNCT = re.compile(r"[^A-Z0-9#/&% ]+")
_SPACES = re.compile(r"\s+")


def norm_label(text: str) -> str:
    """Normalise a header/label for matching: upper-case, punctuation removed,
    parenthesised units dropped, common OCR digit/letter confusions fixed."""
    t = text.upper()
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)
    t = t.replace("'", "").replace("’", "").replace(".", " ").replace(":", " ")
    t = _PUNCT.sub(" ", t)
    t = _SPACES.sub(" ", t).strip()
    # OCR confusions inside label words (never applied to values)
    t = re.sub(r"\bN0\b", "NO", t)
    t = re.sub(r"\b0TY\b|\bOTY\b|\bQTV\b|\bQ TY\b", "QTY", t)
    return t


def clean_value(text: str) -> str:
    t = text.strip().strip(":;|").strip()
    t = _SPACES.sub(" ", t)
    return t


def similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def best_match(text: str, synonyms: dict[str, list[str]], threshold: float = 0.84,
               allow_prefix: bool = True) -> tuple[Optional[str], float, str]:
    """Match *text* against a {field: [synonym, ...]} table.

    Returns (field, score, matched_synonym). Prefix matches ("MASS KG" ->
    "MASS") are accepted with a small penalty so that units/extra words in a
    header still resolve.
    """
    n = norm_label(text)
    if not n:
        return None, 0.0, ""
    best = (None, 0.0, "")
    for fld, syns in synonyms.items():
        for s in syns:
            sn = norm_label(s)
            if not sn:
                continue
            if len(sn) > 3:
                score = similarity(n, sn)
                if score < threshold and len(n) == len(sn) and \
                        sum(a != b for a, b in zip(n, sn)) == 1 and n.replace(" ", "").isalpha():
                    score = threshold  # one OCR-substituted letter: WASS -> MASS
            else:
                score = 1.0 if n == sn else 0.0
            if allow_prefix and score < threshold and n.startswith(sn + " ") and len(sn) >= 2:
                score = 0.9 + 0.05 * min(len(sn) / max(len(n), 1), 1)
            # prefer longer synonyms on ties ("DRAWN BY" over "DRAWN")
            if score > best[1] or (score == best[1] and len(sn) > len(best[2])):
                best = (fld, score, sn)
    if best[1] >= threshold:
        return best
    return None, best[1], ""


def match_label_prefix(text: str, synonyms: dict[str, list[str]]) -> tuple[Optional[str], str, str]:
    """Find a label at the *start* of a text ("DWG NO: 1234").

    Returns (field, matched_label_text, remainder). Longest label wins.
    """
    upper = text.upper()
    best: tuple[Optional[str], str, str] = (None, "", text)
    best_len = 0
    for fld, syns in synonyms.items():
        for s in syns:
            pat = _label_regex(s)
            m = pat.match(upper)
            if m and len(m.group(0)) > best_len:
                best_len = len(m.group(0))
                best = (fld, text[: m.end()], text[m.end():])
    return best


_label_cache: dict[str, re.Pattern] = {}


def _label_regex(label: str) -> re.Pattern:
    if label not in _label_cache:
        toks = [re.escape(t) for t in re.split(r"[\s.]+", label.upper()) if t]
        body = r"[\s.]*".join(toks)
        # label must end at a word boundary, optionally followed by . : # -
        _label_cache[label] = re.compile(r"\s*" + body + r"(?![A-Z0-9])[\s.:#\-]*")
    return _label_cache[label]


def group_lines(words: Iterable[Word]) -> list[TextLine]:
    """Group words into reading-order lines by vertical overlap."""
    ws = sorted(words, key=lambda w: (w.cy, w.x0))
    if not ws:
        return []
    med_h = statistics.median([w.h for w in ws]) or 1
    lines: list[list[Word]] = []
    for w in ws:
        placed = False
        for line in reversed(lines[-4:]):
            ref = statistics.median([x.cy for x in line])
            min_h = min(min(x.h for x in line), w.h)
            line_y0 = min(x.y0 for x in line)
            line_y1 = max(x.y1 for x in line)
            v_overlap = min(w.y1, line_y1) - max(w.y0, line_y0)
            # two words of one line never sit on top of each other (a small
            # label directly above its value is a separate line)
            if any(min(w.x1, x.x1) - max(w.x0, x.x0) > 0.3 * min(w.x1 - w.x0, x.x1 - x.x0)
                   and abs(w.cy - x.cy) > 0.35 * min(w.h, x.h) for x in line):
                continue
            if abs(w.cy - ref) <= 0.5 * med_h or abs(w.cy - ref) <= 0.6 * min_h or v_overlap >= 0.4 * min_h:
                line.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])
    out = [TextLine(sorted(l, key=lambda w: w.x0)) for l in lines]
    out.sort(key=lambda l: (l.bbox[1], l.bbox[0]))
    return out


def split_segments(line: TextLine, gap_factor: float = 2.5) -> list[TextLine]:
    """Split a line wherever the horizontal gap is large (separate columns)."""
    if not line.words:
        return []
    h = statistics.median([w.h for w in line.words]) or 1
    segs = [[line.words[0]]]
    for prev, w in zip(line.words, line.words[1:]):
        if w.x0 - prev.x1 > gap_factor * h:
            segs.append([w])
        else:
            segs[-1].append(w)
    return [TextLine(s) for s in segs]


def text_lines_to_str(lines: list[TextLine]) -> str:
    return "\n".join(l.text for l in lines)


# ---------------------------------------------------------------- OCR clean-up
_CONF2DIGIT = str.maketrans({"O": "0", "o": "0", "S": "5", "s": "5", "I": "1", "l": "1", "|": "1",
                             "B": "8", "Z": "2", "z": "2", "G": "6"})
_UNITS = r"(?:kW|kg|kgs|g|mm|cm|m|A|V|W|Nm|N|bar|kN|Hz|rpm|MPa|°C|L|l|t)"
_THREAD = re.compile(r"\b([MG])(\d{1,3}(?:[.,]\d+)?)([xX×])([0-9OSIlBZ]{1,4})\b")
_DEC_UNIT = re.compile(rf"(?<![A-Za-z0-9])([0-9OSIlBZ]{{1,4}})([.,])([0-9OSIlBZ]{{1,3}})(?=\s*{_UNITS}\b|\b)")
_KQ = re.compile(r"(\d)\s*(kq|Kq|kG)\b")
_ISO = re.compile(r"(?<![A-Za-z0-9])[1lIT|]SO(?=[-\s]\d)")
_RAL = re.compile(r"\b(RAL\s*)([0-9OSIlBZ]{4})\b")


def fix_ocr_confusions(text: str) -> str:
    """Repair letter/digit confusions that only make sense one way in an
    engineering context. Conservative by design: it touches characters only
    inside thread sizes (M10x4S -> M10x45), decimal numbers (7.SkW -> 7.5kW,
    B.8 -> 8.8), units right after a number (4.2 kq -> 4.2 kg) and ISO
    prefixes (1SO-4014 -> ISO-4014). Part numbers and words are left alone."""
    if not text:
        return text
    s = _THREAD.sub(lambda m: m.group(1) + m.group(2) + m.group(3) + m.group(4).translate(_CONF2DIGIT), text)

    def dec(m):
        a, sep, b = m.group(1), m.group(2), m.group(3)
        if not any(c.isdigit() for c in a + b):
            return m.group(0)  # needs at least one real digit
        return a.translate(_CONF2DIGIT) + sep + b.translate(_CONF2DIGIT)

    s = _DEC_UNIT.sub(dec, s)
    s = _KQ.sub(lambda m: m.group(1) + " kg" if " " in m.group(0) else m.group(1) + "kg", s)
    s = _ISO.sub("ISO", s)
    s = _RAL.sub(lambda m: m.group(1) + m.group(2).translate(_CONF2DIGIT), s)  # RAL colours: 4 digits
    return s
