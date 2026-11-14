"""Recognise material grades, surface finishes, heat treatments and
standards in free text (notes, title block fields, BOM material column)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from .models import SpecCallout


@dataclass
class Pattern:
    category: str
    subtype: str
    regex: re.Pattern
    normalize: Callable[[re.Match], str]


def _p(category, subtype, rx, norm=None):
    return Pattern(category, subtype, re.compile(rx, re.I),
                   norm or (lambda m: _tidy(m.group(0))))


def _tidy(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip(" .,;:")).upper()


# --------------------------------------------------------------- materials
_SS_GRADES = r"(?:20[1-2]|30[1-9]L?|31[0-9]L?|32[01]|347|409|410|416|420|430|431|440[ABC]?|17[\s-]?4\s?PH|15[\s-]?5\s?PH|2205|2507|904L)"

MATERIALS = [
    _p("material", "stainless_steel",
       rf"\b(?:STAINLESS\s+STEEL|STAINLESS|S\.?S\.?|AISI|SUS|UNS\s*S)\s*(?:GRADE|GR\.?|TYPE)?\s*-?\s*{_SS_GRADES}\b",
       lambda m: "STAINLESS STEEL " + re.sub(r"\s+", "", re.search(_SS_GRADES, m.group(0), re.I).group(0)).upper()),
    _p("material", "stainless_steel", rf"\bSS\s?{_SS_GRADES}\b",
       lambda m: "STAINLESS STEEL " + re.sub(r"^SS\s?", "", m.group(0).upper())),
    _p("material", "stainless_steel", r"\bSTAINLESS\s+STEEL\b(?!\s*(?:GRADE|GR|TYPE)?\s*-?\s*\d)"),
    _p("material", "aluminium",
       r"\b(?:ALUMINI?UM(?:\s+ALLOY)?|AL(?:UM)?\.?|AA|ALLOY)\s*-?\s*([1-8]\d{3})(?:\s*[-/ ]\s*(T\d{1,4}|O|H\d{2,3}|F))?\b",
       lambda m: "ALUMINIUM " + m.group(1) + (f"-{m.group(2).upper()}" if m.group(2) else "")),
    _p("material", "aluminium", r"\b([1-8]\d{3})\s*-\s*(T\d{1,4})\b(?:\s+ALUMINI?UM)?",
       lambda m: f"ALUMINIUM {m.group(1)}-{m.group(2).upper()}"),
    _p("material", "carbon_steel",
       r"\b(?:ASTM\s*)?A\s?(36|283|285|516|572|500|106|53|105|350)\b(?:\s*(?:GR\.?|GRADE)\s*[A-Z0-9]+)?(?:\s+(?:STRUCTURAL\s+)?STEEL)?",
       lambda m: _tidy("ASTM " + m.group(0).upper().replace("ASTM", "").strip())),
    _p("material", "carbon_steel", r"\bSTRUCTURAL\s+STEEL(?:\s+(?:ASTM\s*)?A\s?\d{2,3})?\b"),
    _p("material", "carbon_steel", r"\bIS\s?2062\s*(?:GR\.?|GRADE)?\s*(?:E\s?\d{3}\s*[A-D]?[RO]?)?\b"),
    _p("material", "carbon_steel", r"\bE\s?(250|275|300|350|410|450)\s*(?:BR|BO|C|A)?\b(?=.*\b(?:IS|STEEL)\b)?"),
    _p("material", "carbon_steel", r"\bEN\s?(1A|3B?|8[DM]?|9|19|24|31|32|36|41B?|42|45|47|353|354)\b(?!\s*ISO)",
       lambda m: "EN" + m.group(1).upper()),
    _p("material", "carbon_steel", r"\b(?:AISI|SAE)\s*(10[1-9]\d|11\d{2}|12L14|41[34]0|43[34]0|8620|52100)\b"),
    _p("material", "carbon_steel", r"\b(?:C|CK)\s?(15|20|22|35|40|45|55|60)(?:E)?\b(?=\s*(?:STEEL|$|[,;/]))"),
    _p("material", "alloy_steel", r"\b(42CrMo4|34CrNiMo6|16MnCr5|20MnCr5|18CrNiMo7-6|41Cr4|100Cr6|S690QL?)\b"),
    _p("material", "structural_steel",
       r"\bS\s?(?:185|235|275|355|420|450|460|500|550|620|690)\s?(?:J[R0-2]|K2|N|NL|M|ML|JUR|JUO|JUZ)?(?:\+[A-Z]{1,2})?(?![A-Z0-9])",
       # EN 10025 suffixes: a 'U' inside J?R is an OCR insertion (S355JUR -> S355JR)
       lambda m: re.sub(r"JU([R0-2Z])", lambda x: "J" + x.group(1).replace("Z", "2"), _tidy(m.group(0))).replace(" ", "")),
    _p("material", "carbon_steel", r"\b(?:MILD\s+STEEL|M\.S\.|CRCA|HRPO|HRCA|C\.R\.C\.A\.)\b"),
    _p("material", "tool_steel", r"\b(?:TOOL\s+STEEL\s+)?(?:AISI\s*)?(D2|D3|H13|O1|A2|M2|S7|P20|OHNS|HCHCR)\b(?=\s*(?:TOOL|STEEL|$|[,;/]|HRC|HARDEN))"),
    _p("material", "cast_iron", r"\b(?:GREY\s+|GRAY\s+|SG\s+|DUCTILE\s+)?CAST\s+IRON\b|\bFG\s?\d{3}\b|\bSG\s?\d{3}(?:/\d+)?\b|\bGG\s?-?\d{2}\b|\bGGG\s?-?\d{2}\b|\bEN-GJ[LS]-\d{3}\b"),
    _p("material", "copper_alloy", r"\b(?:BRASS|BRONZE|PHOSPHOR\s+BRONZE|GUNMETAL|COPPER|BERYLLIUM\s+COPPER)\b(?:\s+(?:C\d{5}|CZ\d{3}|CuZn\d+\w*))?|\bC(?:1[01]|2[2-8]|36|51|54|63|93)\d{3}\b|\bCuZn\d+(?:Pb\d)?\b"),
    _p("material", "titanium", r"\bTi-?6Al-?4V\b|\bTITANIUM(?:\s+(?:GR\.?|GRADE)\s*\d{1,2})?\b"),
    _p("material", "polymer", r"\b(?:NYLON\s*(?:6/6|66|6)?|PA\s?6{1,2}(?:\s?GF\d{2})?|POM|DELRIN|ACETAL|PTFE|TEFLON|UHMW-?PE|PEEK|ABS|POLYCARBONATE|HDPE|LDPE|POLYPROPYLENE|PVC|PET|ACRYLIC|PMMA)\b"),
    _p("material", "elastomer", r"\b(?:EPDM|NBR|NITRILE|NEOPRENE|VITON|FKM|SILICONE\s+RUBBER|NATURAL\s+RUBBER|POLYURETHANE)\b(?:\s+\d{2}\s*SHORE\s*A)?"),
]

# --------------------------------------------------------------- finishes
FINISHES = [
    _p("surface_finish", "roughness",
       r"\b(R[az])\s*[=:]?\s*(\d+(?:[.,]\d+)?)\s*(µm|μm|um|micron|microns|µin|uin|micro\s?inch)?",
       lambda m: f"{m.group(1)[0].upper()}{m.group(1)[1].lower()} {m.group(2).replace(',', '.')} "
                 f"{_unit(m.group(3))}".strip()),
    _p("surface_finish", "roughness", r"\b(?:SURFACE\s+)?(?:FINISH|ROUGHNESS)\s*[:=]?\s*(N(?:[1-9]|1[0-2]))\b",
       lambda m: m.group(1).upper()),
    _p("surface_finish", "anodize",
       r"\b(?:HARD\s+|CLEAR\s+|BLACK\s+|NATURAL\s+|COLOU?RLESS\s+)?ANODI[SZ](?:E|ED|ING)\b"
       r"(?:[\s,]+(?:TYPE\s+(?:I{1,3}|[123])|CLASS\s+[12]|CLEAR|BLACK|NATURAL|HARD|SULPHURIC|SULFURIC|"
       r"\d{1,3}\s*(?:µm|μm|um|MICRON)S?(?:\s+THK)?|PER|MIL-A-8625[A-Z]?|TO))*"),
    _p("surface_finish", "plating",
       r"\b(?:BRIGHT\s+|YELLOW\s+|BLUE\s+|CLEAR\s+|BLACK\s+)?(?:ZINC(?:[\s-]NICKEL)?|NICKEL|CHROME|HARD\s+CHROME|CHROMIUM|"
       r"ELECTROLESS\s+NICKEL|CADMIUM|TIN|SILVER|GOLD|COPPER)\s+PLAT(?:E|ED|ING)\b"
       r"(?:[\s,]+(?:\d{1,3}\s*(?:-\s*\d{1,3}\s*)?(?:µm|μm|um|MICRONS?)|THK|MIN|YELLOW|BLUE|CLEAR|BLACK|"
       r"PASSIVATED|TRIVALENT|CHROMATE|FE/ZN\s?\d+\w*))*"),
    _p("surface_finish", "plating", r"\bFE/ZN\s?\d+\w*\b|\bEN\s?ISO\s?2081\b|\bASTM\s?B\s?633\b"),
    _p("surface_finish", "coating",
       r"\b(?:POWDER\s+COAT(?:ED|ING)?|PAINT(?:ED)?|PRIMER|PRIMED|E-?COAT(?:ED|ING)?|CED\s+COAT(?:ED|ING)?|"
       r"ZINC\s+FLAKE|GEOMET|DACROMET|HOT[\s-]DIP(?:PED)?\s+GALVANI[SZ](?:E|ED|ING)|GALVANI[SZ](?:E|ED|ING)|"
       r"BLACK\s+OXIDE|BLACKODI[SZ](?:E|ED|ING)|PHOSPHAT(?:E|ED|ING)|ZINC\s+PHOSPHATE|MANGANESE\s+PHOSPHATE|"
       r"PASSIVAT(?:E|ED|ION)|CHEM(?:ICAL)?\s+FILM|ALODINE|IRIDITE|CHROMATE\s+CONVERSION(?:\s+COAT(?:ING)?)?|"
       r"PTFE\s+COAT(?:ED|ING)|DLC\s+COAT(?:ED|ING)?|TIN\s+COAT(?:ED|ING)|NITRIDE\s+COAT(?:ED|ING))\b"
       r"(?:[\s,]+(?:RAL\s?\d{4}|\d{2,3}\s*(?:-\s*\d{2,3}\s*)?(?:µm|μm|um|MICRONS?)(?:\s+(?:DFT|THK|MIN))?|"
       r"MATT|GLOSS|SEMI[\s-]GLOSS|BLACK|GREY|GRAY|WHITE|RED|BLUE|TEXTURED|EPOXY|POLYESTER|PER\s+\S+))*"),
    _p("surface_finish", "mechanical",
       r"\b(?:SHOT|SAND|BEAD|GRIT)\s+BLAST(?:ED|ING)?(?:\s+(?:TO\s+)?SA\s?\d(?:\.\d)?)?|\b(?:MIRROR\s+|ELECTRO[\s-]?)?POLISH(?:ED|ING)\b|"
       r"\bBRUSHED\b|\bLAPPED\b|\bHONED\b|\bGROUND\b(?=\s+(?:FINISH|SURFACE))"),
]

# --------------------------------------------------------------- heat treatment
_HARD = r"(\d{2,3}(?:\.\d)?)\s*(?:(?:-|TO|~|–)\s*(\d{2,3}(?:\.\d)?))?\s*(HRC|HRB|HRA|HB|HBW|BHN|HV\d*)"
_HARD_PRE = r"(HRC|HRB|HB|HBW|BHN|HV\d*)\s*(\d{2,3})(?:\s*(?:-|TO|~|–)\s*(\d{2,3}))?"

HEAT = [
    _p("heat_treatment", "quench_temper",
       r"\b(?:QUENCH(?:ED)?|HARDEN(?:ED)?)\s*(?:&|AND|\+)\s*TEMPER(?:ED)?\b|\bQ\s?&\s?T\b|\bQT\b(?=.*\b(?:HRC|HB|TEMPER))",
       lambda m: "QUENCHED & TEMPERED" if m.group(0).upper().startswith("Q") else "HARDENED & TEMPERED"),
    _p("heat_treatment", "case_hardening",
       r"\b(?:CASE[\s-]HARDEN(?:ED|ING)?|CARBURI[SZ](?:E|ED|ING)|CARBONITRID(?:E|ED|ING)|CASE\s+CARBURI[SZ]ED)\b"
       r"(?:[\s,]+(?:(?:EFFECTIVE\s+)?CASE\s+DEPTH|ECD|TO)?\s*[:=]?\s*\d+(?:\.\d+)?\s*(?:-\s*\d+(?:\.\d+)?)?\s*MM)?"),
    _p("heat_treatment", "surface_hardening",
       r"\b(?:INDUCTION|FLAME|LASER)\s+HARDEN(?:ED|ING)?\b|\b(?:GAS\s+|PLASMA\s+|SALT\s+BATH\s+)?NITRID(?:E|ED|ING)\b(?!\s+COAT)|\bNITROCARBURI[SZ](?:E|ED|ING)\b|\bTUFFTRID(?:E|ED|ING)\b"),
    _p("heat_treatment", "through_hardening", r"\bTHROUGH[\s-]HARDEN(?:ED|ING)?\b|\bHARDEN(?:ED|ING)?\b(?!\s*(?:&|AND|\+)\s*TEMPER)(?=\s+(?:TO|AND)\s)"),
    _p("heat_treatment", "softening",
       r"\b(?:FULL\s+|SOLUTION\s+)?ANNEAL(?:ED|ING)?\b|\bNORMALI[SZ](?:E|ED|ING)\b|\bSTRESS[\s-]RELIEV(?:E|ED|ING)\b|\bSPHEROIDI[SZ](?:E|ED|ING)\b"),
    _p("heat_treatment", "precipitation",
       r"\b(?:AGE[\s-]HARDEN(?:ED|ING)?|PRECIPITATION\s+HARDEN(?:ED|ING)?|SOLUTION\s+TREAT(?:ED|MENT)(?:\s+(?:AND|&)\s+AGED)?|ARTIFICIALLY\s+AGED|H\s?1025|H\s?900|H\s?1150)\b"),
    _p("heat_treatment", "hardness", rf"\b{_HARD}\b",
       lambda m: f"{m.group(1)}{'-' + m.group(2) if m.group(2) else ''} {m.group(3).upper()}"),
    _p("heat_treatment", "hardness", rf"\b{_HARD_PRE}\b",
       lambda m: f"{m.group(2)}{'-' + m.group(3) if m.group(3) else ''} {m.group(1).upper()}"),
]

# --------------------------------------------------------------- standards
STANDARDS = [
    _p("standard", "standard",
       r"\b(ASTM|ISO|DIN(?:\s+EN)?|EN(?:\s+ISO)?|SAE|ANSI|ASME|JIS|BS(?:\s+EN)?|IS|AMS|NAS|GB/?T?|MIL-[A-Z]{1,4}|AWS|API|AS)\s?[- ]?"
       r"([A-Z]{0,2}\s?\d[\dA-Z]*(?:[.\-:/]\d[\dA-Z]*)*(?:\s?-\s?[a-zA-Z]{1,3}\b)?)",
       lambda m: _std_norm(m)),
]


def _std_norm(m: re.Match) -> str:
    body = re.sub(r"\s+", " ", m.group(2)).strip()
    org = m.group(1).upper()
    if org.startswith("MIL-"):
        return f"{org}-{body}"
    return f"{org} {body}"


def _unit(u: Optional[str]) -> str:
    if not u:
        return "µm"
    u = u.lower()
    if "in" in u:
        return "µin"
    return "µm"


ALL_PATTERNS = MATERIALS + FINISHES + HEAT + STANDARDS

# standards that are clearly not engineering standards / are materials
_STD_EXCLUDE = re.compile(r"^(?:EN\s?(?:1A|3B?|8[DM]?|9|19|24|31|32|36|41B?|42|45|47|353|354)|IS\s?\d{1,2}|AS\s?\d{1,2})$", re.I)


def find_specs(text: str, source: str, page: int = 0, bbox=None, conf: float = 1.0,
               categories: Optional[set[str]] = None) -> list[SpecCallout]:
    """Return every spec callout found in *text*, longest match first,
    non-overlapping within a category."""
    if not text:
        return []
    found: list[SpecCallout] = []
    spans: dict[str, list[tuple[int, int]]] = {}
    hits = []
    for p in ALL_PATTERNS:
        if categories and p.category not in categories:
            continue
        for m in p.regex.finditer(text):
            if not m.group(0).strip():
                continue
            hits.append((p, m))
    hits.sort(key=lambda pm: -(pm[1].end() - pm[1].start()))
    for p, m in hits:
        s, e = m.span()
        taken = spans.setdefault(p.category, [])
        if any(s < te and e > ts for ts, te in taken):
            continue
        try:
            val = p.normalize(m)
        except Exception:
            val = _tidy(m.group(0))
        if p.category == "standard":
            if _STD_EXCLUDE.match(val):
                continue
            # don't double report an ASTM material grade as a bare standard? keep it - useful.
        taken.append((s, e))
        found.append(SpecCallout(category=p.category, subtype=p.subtype, value=val,
                                 context=_context(text, s, e), source=source,
                                 confidence=conf, bbox=bbox, page=page))
    found.sort(key=lambda c: text.upper().find(c.context.upper()[:10]))
    return found


def _context(text: str, s: int, e: int) -> str:
    """The sentence/clause around the match."""
    left = max(text.rfind(".", 0, s - 1) if s > 1 else -1, text.rfind(";", 0, s), text.rfind("\n", 0, s))
    # don't split decimals like 1.6 or 6061-T6. inside sentence boundaries
    while left > 0 and left + 1 < len(text) and text[left - 1].isdigit() and text[left + 1].isdigit():
        left = max(text.rfind(".", 0, left), text.rfind(";", 0, left), text.rfind("\n", 0, left))
    right_c = [i for i in (text.find(". ", e), text.find(";", e), text.find("\n", e)) if i != -1]
    right = min(right_c) if right_c else len(text)
    ctx = text[left + 1:right].strip(" .;\n")
    return re.sub(r"\s+", " ", ctx)[:300]


def summarise(specs: list[SpecCallout]) -> dict[str, Optional[str]]:
    """Pick the headline material / surface finish / heat treatment for the
    drawing, preferring explicit notes and title-block fields over BOM lines."""
    pri = {"title_block": 0, "notes": 1, "page_text": 2, "bom": 3}

    def pick(cat, sub_order=None):
        cands = [s for s in specs if s.category == cat]
        if not cands:
            return None
        cands.sort(key=lambda s: (pri.get(s.source, 9), -len(s.value)))
        return cands

    out: dict[str, Optional[str]] = {}
    mats = pick("material")
    if mats:
        top_src = mats[0].source
        same = [m.value for m in mats if m.source == top_src]
        if top_src == "bom":  # fall back to the dominant BOM material
            freq = {v.upper(): same.count(v) for v in same}
            same = sorted(same, key=lambda v: -freq[v.upper()])
        vals = _uniq(same)
        out["material_callout"] = " / ".join(vals[:2])
    else:
        out["material_callout"] = None
    fin = pick("surface_finish")
    if fin:
        coat = _uniq([f.value for f in fin if f.subtype != "roughness" and f.source != "bom"])
        rough = _uniq([f.value for f in fin if f.subtype == "roughness" and f.source != "bom"])
        out["surface_finish"] = " / ".join(coat[:2] + rough[:1]) or fin[0].value
    else:
        out["surface_finish"] = None
    ht = pick("heat_treatment")
    if ht:
        procs = _uniq([h.value for h in ht if h.subtype != "hardness" and h.source != "bom"])
        hard = _uniq([h.value for h in ht if h.subtype == "hardness" and h.source != "bom"])
        out["heat_treatment"] = " ".join(procs[:2] + hard[:1]) or ht[0].value
    else:
        out["heat_treatment"] = None
    stds = _uniq([s.value for s in specs if s.category == "standard"])
    out["standards"] = ", ".join(stds) if stds else None
    return out


def _uniq(xs):
    seen, out = set(), []
    for x in xs:
        k = x.upper()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out
