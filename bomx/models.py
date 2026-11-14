"""Core data structures shared across the extraction pipeline."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

BBox = tuple[float, float, float, float]  # x0, y0, x1, y1 in page-image pixels


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 1.0  # 0..1

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def bbox(self) -> BBox:
        return (self.x0, self.y0, self.x1, self.y1)


@dataclass
class TextLine:
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def bbox(self) -> BBox:
        return union_bbox([w.bbox for w in self.words])

    @property
    def conf(self) -> float:
        return mean_conf(self.words)


@dataclass
class Cell:
    x0: float
    y0: float
    x1: float
    y1: float
    words: list[Word] = field(default_factory=list)
    id: int = -1
    parent: int = -1  # for virtual cells split out of a merged/broken cell

    @property
    def bbox(self) -> BBox:
        return (self.x0, self.y0, self.x1, self.y1)

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def lines(self) -> list[TextLine]:
        from .textutil import group_lines
        return group_lines(self.words)

    @property
    def text(self) -> str:
        return " ".join(l.text for l in self.lines).strip()

    @property
    def conf(self) -> float:
        return mean_conf(self.words)


@dataclass
class Region:
    kind: str  # title_block | bom | revision | notes | other
    bbox: BBox
    page: int
    confidence: float = 1.0
    cells: list[Cell] = field(default_factory=list)


@dataclass
class FieldValue:
    value: Optional[str]
    confidence: float = 0.0
    bbox: Optional[BBox] = None
    raw: Optional[str] = None
    normalized: Any = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items()}


@dataclass
class Measurement:
    """Canonical model for engineering measurements (mass, quantity, dimensions)."""
    raw: str
    nominal: Optional[float] = None
    unit: Optional[str] = None
    canonical_value: Optional[float] = None  # in base unit (kg, mm, count, deg)
    canonical_unit: Optional[str] = None
    measurement_type: str = "generic"  # quantity | mass | linear | diameter | radius | thread | chamfer | angle | roughness
    tolerance: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items()}


@dataclass
class BomRow:
    item: Optional[str] = None
    part_number: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[str] = None
    material: Optional[str] = None
    mass: Optional[str] = None
    remarks: Optional[str] = None
    extra: dict[str, str] = field(default_factory=dict)
    quantity_value: Optional[float] = None
    mass_kg: Optional[float] = None
    confidence: float = 1.0  # OCR / character recognition confidence
    structural_confidence: float = 1.0  # layout / column assignment confidence
    bbox: Optional[BBox] = None
    page: int = 0
    flags: list[str] = field(default_factory=list)
    quantity_measurement: Optional[Measurement] = None
    mass_measurement: Optional[Measurement] = None
    mass_verified: bool = False
    mass_candidate: Optional[float] = None

    def __post_init__(self):
        if "mass_decimal_ambiguous" in self.flags:
            if self.mass_kg is not None and self.mass_candidate is None:
                self.mass_candidate = self.mass_kg
            self.mass_kg = None
            self.mass_measurement = None
            self.mass_verified = False
        elif self.mass_kg is not None:
            self.mass_verified = True

        if self.quantity_measurement is None and (self.quantity_value is not None or self.quantity):
            raw = self.quantity or (str(self.quantity_value) if self.quantity_value is not None else "")
            nom = float(self.quantity_value) if self.quantity_value is not None else None
            unit = None
            if self.quantity:
                num_m = re.search(r"[-+]?(?:\d+(?:[.,]\d+)?|\.\d+)", self.quantity)
                if num_m and nom is None:
                    try:
                        nom = float(num_m.group(0).replace(",", "."))
                    except ValueError:
                        pass
                m = re.search(r"([A-Za-z]+)", self.quantity)
                if m:
                    unit = m.group(1)

            canon_val = float(self.quantity_value) if self.quantity_value is not None else (nom if nom is not None else None)
            canon_unit = "count"
            if unit:
                u_upper = unit.upper()
                if u_upper in ("M", "MTR"):
                    canon_unit = "m"
                elif u_upper == "MM":
                    canon_unit = "m"
                    if canon_val is not None:
                        canon_val = canon_val / 1000.0
                elif u_upper.startswith("KG"):
                    canon_unit = "kg"
                elif u_upper in ("L", "LTR"):
                    canon_unit = "l"

            self.quantity_measurement = Measurement(
                raw=raw,
                nominal=nom,
                unit=unit,
                canonical_value=canon_val,
                canonical_unit=canon_unit,
                measurement_type="quantity",
                confidence=self.confidence
            )

        if self.mass_measurement is None and (self.mass_kg is not None or self.mass) and "mass_decimal_ambiguous" not in self.flags:
            raw = self.mass or (f"{self.mass_kg} kg" if self.mass_kg is not None else "")
            nom = None
            unit = None
            if self.mass:
                num_m = re.search(r"[-+]?(?:\d+(?:[.,]\d+)?|\.\d+)", self.mass)
                if num_m:
                    try:
                        nom = float(num_m.group(0).replace(",", "."))
                    except ValueError:
                        pass
                m = re.search(r"([A-Za-z]+)", self.mass)
                if m:
                    unit = m.group(1)

            if unit is None and self.mass_kg is not None:
                unit = "kg"
            if nom is None and self.mass_kg is not None:
                nom = self.mass_kg

            canon_val = self.mass_kg
            canon_unit = "kg"
            if canon_val is None and nom is not None:
                u_upper = (unit or "KG").upper()
                if u_upper.startswith("KG"):
                    canon_val = nom
                elif u_upper in ("G", "GM", "GMS", "GRAM", "GRAMS"):
                    canon_val = nom / 1000.0
                elif u_upper.startswith("LB") or u_upper.startswith("POUND"):
                    canon_val = nom * 0.45359237
                elif u_upper.startswith("OZ") or u_upper.startswith("OUNCE"):
                    canon_val = nom * 0.0283495
                elif u_upper == "MG":
                    canon_val = nom / 1_000_000.0
                elif u_upper.startswith("T"):
                    canon_val = nom * 1000.0
                else:
                    canon_val = nom

            if self.mass_kg is None and canon_val is not None:
                self.mass_kg = canon_val

            self.mass_measurement = Measurement(
                raw=raw,
                nominal=nom,
                unit=unit,
                canonical_value=canon_val,
                canonical_unit=canon_unit,
                measurement_type="mass",
                confidence=self.confidence
            )


@dataclass
class RevisionRow:
    rev: Optional[str] = None
    description: Optional[str] = None
    date: Optional[str] = None
    approved: Optional[str] = None
    extra: dict[str, str] = field(default_factory=dict)
    confidence: float = 1.0
    bbox: Optional[BBox] = None
    page: int = 0


@dataclass
class SpecCallout:
    category: str  # material | surface_finish | heat_treatment | standard
    value: str  # normalised matched value, e.g. "SS 304"
    context: str  # the full sentence / note it came from
    source: str  # notes | title_block | bom | page_text
    subtype: Optional[str] = None
    confidence: float = 1.0
    bbox: Optional[BBox] = None
    page: int = 0


@dataclass
class Dimension:
    text: str
    nominal: Optional[float] = None
    tolerance: Optional[str] = None
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    dim_type: str = "linear"  # linear | diameter | radius | thread | chamfer | angle
    raw: Optional[str] = None
    bbox: Optional[BBox] = None
    page: int = 0
    confidence: float = 1.0
    measurement: Optional[Measurement] = None

    def __post_init__(self):
        if self.measurement is None:
            raw = self.raw or self.text
            unit = "°" if self.dim_type == "angle" else ("mm" if self.dim_type in ("linear", "diameter", "radius", "chamfer") else None)
            canonical_unit = "deg" if self.dim_type == "angle" else ("mm" if self.dim_type in ("linear", "diameter", "radius", "chamfer") else None)
            self.measurement = Measurement(
                raw=raw,
                nominal=self.nominal,
                unit=unit,
                canonical_value=self.nominal,
                canonical_unit=canonical_unit,
                measurement_type=self.dim_type,
                tolerance=self.tolerance,
                confidence=self.confidence
            )

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items()}

    @property
    def as_measurement(self) -> Measurement:
        return self.measurement


@dataclass
class PageResult:
    index: int
    source: str  # native | ocr
    width: int
    height: int
    dpi: float
    skew_deg: float = 0.0
    rotation_deg: int = 0
    regions: list[Region] = field(default_factory=list)
    overlay_path: Optional[str] = None
    kind: str = ""  # pdf-vector | pdf-scan | pdf-outlined-text | image | dxf | dwg | dxf-traced ...
    layout: str = ""  # CAD layout (model / paper-space sheet) the page was rendered from


@dataclass
class DrawingResult:
    source_file: str
    title_block: dict[str, FieldValue] = field(default_factory=dict)
    bom: list[BomRow] = field(default_factory=list)
    bom_columns: list[str] = field(default_factory=list)
    revisions: list[RevisionRow] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)
    specs: list[SpecCallout] = field(default_factory=list)
    dimensions: list[Dimension] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    pages: list[PageResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    processing_seconds: float = 0.0

    def to_dict(self) -> dict:
        def region_dict(r: Region) -> dict:
            return {"kind": r.kind, "bbox": _rb(r.bbox), "page": r.page,
                    "confidence": round(r.confidence, 3)}

        pages = []
        for p in self.pages:
            d = {k: v for k, v in asdict(p).items() if k != "regions"}
            d["regions"] = [region_dict(r) for r in p.regions]
            pages.append(d)
        return {
            "source_file": self.source_file,
            "summary": self.summary,
            "title_block": {k: _clean(v.to_dict()) for k, v in self.title_block.items()},
            "bom_columns": self.bom_columns,
            "bom": [_clean(asdict(r)) for r in self.bom],
            "revisions": [_clean(asdict(r)) for r in self.revisions],
            "notes": self.notes,
            "specs": [_clean(asdict(s)) for s in self.specs],
            "dimensions": [_clean(asdict(d)) for d in self.dimensions],
            "pages": pages,
            "warnings": self.warnings,
            "processing_seconds": round(self.processing_seconds, 2),
        }


# ---------------------------------------------------------------- helpers

def _rb(b):
    return None if b is None else [round(float(v), 1) for v in b]


def _clean(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if k == "bbox":
            v = _rb(v)
        elif isinstance(v, float):
            v = round(v, 4)
        elif isinstance(v, dict):
            v = _clean(v)
        out[k] = v
    return out


def union_bbox(boxes) -> BBox:
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return (0, 0, 0, 0)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def mean_conf(words) -> float:
    if not words:
        return 0.0
    tot = sum(max(len(w.text), 1) for w in words)
    return sum(w.conf * max(len(w.text), 1) for w in words) / tot
