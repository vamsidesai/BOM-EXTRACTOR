"""Pydantic schemas for BOMX REST API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Base Engineering Primitives
# -----------------------------------------------------------------------------

class MeasurementSchema(BaseModel):
    raw: str = ""
    nominal: Optional[float] = None
    unit: Optional[str] = None
    canonical_value: Optional[float] = None
    canonical_unit: Optional[str] = None
    measurement_type: str = "generic"
    tolerance: Optional[str] = None
    confidence: float = 1.0


class FieldValueSchema(BaseModel):
    value: Optional[str] = None
    confidence: float = 0.0
    bbox: Optional[List[float]] = None
    raw: Optional[str] = None
    normalized: Any = None


class BomRowSchema(BaseModel):
    item: Optional[str] = None
    part_number: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[str] = None
    material: Optional[str] = None
    mass: Optional[str] = None
    remarks: Optional[str] = None
    extra: Dict[str, str] = Field(default_factory=dict)
    quantity_value: Optional[float] = None
    mass_kg: Optional[float] = None
    confidence: float = 1.0
    structural_confidence: float = 1.0
    bbox: Optional[List[float]] = None
    page: int = 0
    flags: List[str] = Field(default_factory=list)
    quantity_measurement: Optional[MeasurementSchema] = None
    mass_measurement: Optional[MeasurementSchema] = None
    mass_verified: bool = False
    mass_candidate: Optional[float] = None


class RevisionRowSchema(BaseModel):
    rev: Optional[str] = None
    description: Optional[str] = None
    date: Optional[str] = None
    approved: Optional[str] = None
    extra: Dict[str, str] = Field(default_factory=dict)
    confidence: float = 1.0
    bbox: Optional[List[float]] = None
    page: int = 0


class SpecCalloutSchema(BaseModel):
    category: str
    value: str
    context: str
    source: str
    subtype: Optional[str] = None
    confidence: float = 1.0
    bbox: Optional[List[float]] = None
    page: int = 0


class DimensionSchema(BaseModel):
    text: str
    nominal: Optional[float] = None
    tolerance: Optional[str] = None
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    dim_type: str = "linear"
    raw: Optional[str] = None
    bbox: Optional[List[float]] = None
    page: int = 0
    confidence: float = 1.0
    measurement: Optional[MeasurementSchema] = None


class RegionSchema(BaseModel):
    kind: str  # title_block | bom | revision | notes | other
    bbox: Optional[List[float]] = None
    page: int
    confidence: float = 1.0


class PageResultSchema(BaseModel):
    index: int
    source: str
    width: int
    height: int
    dpi: float
    skew_deg: float = 0.0
    rotation_deg: int = 0
    regions: List[RegionSchema] = Field(default_factory=list)
    overlay_path: Optional[str] = None
    kind: str = ""
    layout: str = ""
    image_url: Optional[str] = None


class DrawingResultSchema(BaseModel):
    source_file: str
    summary: Dict[str, Any] = Field(default_factory=dict)
    title_block: Dict[str, FieldValueSchema] = Field(default_factory=dict)
    bom_columns: List[str] = Field(default_factory=list)
    bom: List[BomRowSchema] = Field(default_factory=list)
    revisions: List[RevisionRowSchema] = Field(default_factory=list)
    notes: List[Dict[str, Any]] = Field(default_factory=list)
    specs: List[SpecCalloutSchema] = Field(default_factory=list)
    dimensions: List[DimensionSchema] = Field(default_factory=list)
    pages: List[PageResultSchema] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    processing_seconds: float = 0.0


# -----------------------------------------------------------------------------
# Document & API Management Schemas
# -----------------------------------------------------------------------------

class DrawingSummaryItem(BaseModel):
    id: str
    filename: str
    file_format: str
    file_size_bytes: int
    uploaded_at: str
    status: str  # "pending" | "processing" | "completed" | "failed"
    verified: bool = False
    review_required: bool = False
    review_reasons: Optional[str] = None
    mean_confidence: Optional[float] = None
    text_confidence: Optional[float] = None
    structural_confidence: Optional[float] = None
    drawing_number: Optional[str] = None
    drawing_title: Optional[str] = None
    revision: Optional[str] = None
    bom_items_count: int = 0
    page_count: int = 1
    processing_seconds: Optional[float] = None
    error_message: Optional[str] = None


class DrawingDetailResponse(BaseModel):
    metadata: DrawingSummaryItem
    result: Optional[DrawingResultSchema] = None
    preview_url: Optional[str] = None


class ExtractionConfigRequest(BaseModel):
    dpi: int = 300
    ocr_lang: str = "eng"
    force_ocr: bool = False
    cell_ocr: bool = True
    deskew: bool = True
    auto_rotate: bool = True
    low_conf_threshold: float = 0.65


class ExtractionJobStatus(BaseModel):
    job_id: str
    drawing_id: str
    status: str  # pending | processing | completed | failed
    progress: int  # 0 to 100
    current_step: str = ""
    error_message: Optional[str] = None


class DashboardStatsResponse(BaseModel):
    total_drawings: int
    verified_drawings: int
    review_required_drawings: int
    failed_drawings: int
    total_bom_items: int
    recent_drawings: List[DrawingSummaryItem]
    confidence_distribution: Dict[str, int]
    file_type_distribution: Dict[str, int]


class UpdateDrawingPayload(BaseModel):
    verified: Optional[bool] = None
    title_block: Optional[Dict[str, Any]] = None
    bom: Optional[List[Dict[str, Any]]] = None
    revisions: Optional[List[Dict[str, Any]]] = None
    notes: Optional[List[Dict[str, Any]]] = None


class BatchDeleteRequest(BaseModel):
    ids: List[str]


class BatchExportRequest(BaseModel):
    ids: List[str]
    format: str = "excel"  # excel | csv_zip | json

