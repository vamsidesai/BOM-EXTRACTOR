/**
 * TypeScript API interfaces for BOMX.
 */

export interface BBox {
  0: number; // x0
  1: number; // y0
  2: number; // x1
  3: number; // y1
}

export interface Measurement {
  raw: string;
  nominal?: number | null;
  unit?: string | null;
  canonical_value?: number | null;
  canonical_unit?: string | null;
  measurement_type?: string;
  tolerance?: string | null;
  confidence: number;
}

export interface FieldValue {
  value?: string | null;
  confidence: number;
  bbox?: number[] | null;
  raw?: string | null;
  normalized?: any;
}

export interface BomRow {
  item?: string | null;
  part_number?: string | null;
  description?: string | null;
  quantity?: string | null;
  material?: string | null;
  mass?: string | null;
  remarks?: string | null;
  extra?: Record<string, string>;
  quantity_value?: number | null;
  mass_kg?: number | null;
  confidence: number;
  structural_confidence: number;
  bbox?: number[] | null;
  page: number;
  flags: string[];
  quantity_measurement?: Measurement | null;
  mass_measurement?: Measurement | null;
  mass_verified?: boolean;
  mass_candidate?: number | null;
}

export interface RevisionRow {
  rev?: string | null;
  description?: string | null;
  date?: string | null;
  approved?: string | null;
  extra?: Record<string, string>;
  confidence: number;
  bbox?: number[] | null;
  page: number;
}

export interface SpecCallout {
  category: string;
  value: string;
  context: string;
  source: string;
  subtype?: string | null;
  confidence: number;
  bbox?: number[] | null;
  page: number;
}

export interface Dimension {
  text: string;
  nominal?: number | null;
  tolerance?: string | null;
  prefix?: string | null;
  suffix?: string | null;
  dim_type: string;
  raw?: string | null;
  bbox?: number[] | null;
  page: number;
  confidence: number;
  measurement?: Measurement | null;
}

export interface Region {
  kind: 'title_block' | 'bom' | 'revision' | 'notes' | 'other';
  bbox?: number[] | null;
  page: number;
  confidence: number;
}

export interface PageResult {
  index: number;
  source: string;
  width: number;
  height: number;
  dpi: number;
  skew_deg: number;
  rotation_deg: number;
  regions: Region[];
  overlay_path?: string | null;
  kind?: string;
  layout?: string;
  image_url?: string;
  overlay_url?: string;
}

export interface DrawingResult {
  source_file: string;
  summary: {
    drawing_number?: string | null;
    drawing_title?: string | null;
    revision?: string | null;
    drawn_by?: string | null;
    date?: string | null;
    scale?: string | null;
    projection?: string | null;
    sheet?: string | null;
    mean_confidence?: number | null;
    text_confidence?: number | null;
    structural_confidence?: number | null;
    review_required?: boolean;
    review_reasons?: string | null;
    bom_items?: number;
    pages?: number;
    file_format?: string;
    status?: string;
  };
  title_block: Record<string, FieldValue>;
  bom_columns: string[];
  bom: BomRow[];
  revisions: RevisionRow[];
  notes: Array<{
    id?: number;
    number?: string;
    text: string;
    confidence: number;
    bbox?: number[] | null;
    page: number;
  }>;
  specs: SpecCallout[];
  dimensions: Dimension[];
  pages: PageResult[];
  warnings: string[];
  processing_seconds: number;
}

export interface DrawingSummaryItem {
  id: string;
  filename: string;
  file_format: string;
  file_size_bytes: number;
  uploaded_at: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  verified: boolean;
  review_required: boolean;
  review_reasons?: string | null;
  mean_confidence?: number | null;
  text_confidence?: number | null;
  structural_confidence?: number | null;
  drawing_number?: string | null;
  drawing_title?: string | null;
  revision?: string | null;
  bom_items_count: number;
  page_count: number;
  processing_seconds?: number | null;
  error_message?: string | null;
}

export interface DrawingDetailResponse {
  metadata: DrawingSummaryItem;
  result?: DrawingResult | null;
  preview_url?: string | null;
}

export interface OverlayBox {
  id: string;
  type: 'region' | 'title_field' | 'bom_row' | 'spec' | 'note';
  category?: string;
  field?: string;
  rowIndex?: number;
  label: string;
  value?: string | null;
  confidence: number;
  bbox: number[]; // [x0, y0, x1, y1]
  norm: number[]; // [x, y, w, h] normalized 0..1
  color: string;
}

export interface DrawingOverlaysResponse {
  drawing_id: string;
  page_count: number;
  overlays: Record<number, OverlayBox[]>;
}

export interface DashboardStats {
  total_drawings: number;
  verified_drawings: number;
  review_required_drawings: number;
  failed_drawings: number;
  total_bom_items: number;
  recent_drawings: DrawingSummaryItem[];
  confidence_distribution: Record<string, number>;
  file_type_distribution: Record<string, number>;
}

export interface ExtractionConfig {
  dpi: number;
  ocr_lang: string;
  force_ocr: boolean;
  cell_ocr: boolean;
  deskew: boolean;
  auto_rotate: boolean;
  low_conf_threshold: number;
}

