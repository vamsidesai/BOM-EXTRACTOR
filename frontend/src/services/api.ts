/**
 * REST API client for BOMX backend services.
 */

import type {
  DashboardStats,
  DrawingDetailResponse,
  DrawingOverlaysResponse,
  DrawingSummaryItem,
  ExtractionConfig,
} from '../types/api';

const API_BASE = '/api';

export const api = {
  // Dashboard
  async getDashboardStats(): Promise<DashboardStats> {
    const res = await fetch(`${API_BASE}/dashboard/stats`);
    if (!res.ok) throw new Error(`Failed to load dashboard stats: ${res.statusText}`);
    return res.json();
  },

  // Drawings
  async listDrawings(): Promise<DrawingSummaryItem[]> {
    const res = await fetch(`${API_BASE}/drawings`);
    if (!res.ok) throw new Error(`Failed to list drawings: ${res.statusText}`);
    return res.json();
  },

  async getDrawingDetail(id: string): Promise<DrawingDetailResponse> {
    const res = await fetch(`${API_BASE}/drawings/${id}`);
    if (!res.ok) throw new Error(`Failed to get drawing ${id}: ${res.statusText}`);
    return res.json();
  },

  async updateDrawing(id: string, payload: {
    verified?: boolean;
    title_block?: Record<string, any>;
    bom?: any[];
    revisions?: any[];
    notes?: any[];
  }): Promise<any> {
    const res = await fetch(`${API_BASE}/drawings/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`Failed to update drawing: ${res.statusText}`);
    return res.json();
  },

  async deleteDrawing(id: string): Promise<void> {
    const res = await fetch(`${API_BASE}/drawings/${id}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(`Failed to delete drawing: ${res.statusText}`);
  },

  // Upload
  async uploadDrawings(files: File[], autoExtract: boolean = true, forceOcr: boolean = false): Promise<any> {
    const formData = new FormData();
    files.forEach((f) => formData.append('files', f));
    formData.append('auto_extract', String(autoExtract));
    formData.append('force_ocr', String(forceOcr));

    const res = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Upload failed');
    }
    return res.json();
  },

  // Extraction
  async startExtraction(drawingId: string, config?: Partial<ExtractionConfig>): Promise<any> {
    const res = await fetch(`${API_BASE}/extract/${drawingId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: config ? JSON.stringify(config) : undefined,
    });
    if (!res.ok) throw new Error(`Failed to start extraction: ${res.statusText}`);
    return res.json();
  },

  async getExtractionStatus(drawingId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/extract/${drawingId}/status`);
    if (!res.ok) throw new Error(`Failed to fetch status: ${res.statusText}`);
    return res.json();
  },

  // Viewer & Overlays
  async getDrawingOverlays(drawingId: string): Promise<DrawingOverlaysResponse> {
    const res = await fetch(`${API_BASE}/drawings/${drawingId}/overlays`);
    if (!res.ok) throw new Error(`Failed to fetch overlays: ${res.statusText}`);
    return res.json();
  },

  getPageImageUrl(drawingId: string, pageNum: number = 1): string {
    return `${API_BASE}/drawings/${drawingId}/pages/${pageNum}/image`;
  },

  getPageOverlayUrl(drawingId: string, pageNum: number = 1): string {
    return `${API_BASE}/drawings/${drawingId}/pages/${pageNum}/overlay`;
  },

  getOriginalFileUrl(drawingId: string): string {
    return `${API_BASE}/drawings/${drawingId}/file`;
  },

  // Export URLs
  getExcelExportUrl(drawingId: string): string {
    return `${API_BASE}/drawings/${drawingId}/export/excel`;
  },

  getCsvExportUrl(drawingId: string): string {
    return `${API_BASE}/drawings/${drawingId}/export/csv`;
  },

  getJsonExportUrl(drawingId: string): string {
    return `${API_BASE}/drawings/${drawingId}/export/json`;
  },
};

