"""Core data structures shared across the extraction pipeline."""
from __future__ import annotations

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
    confidence: float = 1.0
    bbox: Optional[BBox] = None
    page: int = 0
    flags: list[str] = field(default_factory=list)


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
