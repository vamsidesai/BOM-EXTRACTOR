import React, { useState, useEffect } from 'react';
import type { DrawingSummaryItem, ExtractionConfig } from '../types/api';
import { api } from '../services/api';
import { UploadZone } from '../components/upload/UploadZone';
import { UploadQueue } from '../components/upload/UploadQueue';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { FileCheck, ShieldAlert, Cpu, History, ArrowRight } from 'lucide-react';

interface UploadViewProps {
  onOpenWorkspace: (id: string) => void;
  onNavigateHistory: () => void;
}

export const UploadView: React.FC<UploadViewProps> = ({
  onOpenWorkspace,
  onNavigateHistory,
}) => {
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [queue, setQueue] = useState<DrawingSummaryItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fetchRecent = async () => {
    try {
      const items = await api.listDrawings();
      setQueue(items.slice(0, 10));
    } catch (e) {
      // Ignore initial load failure
    }
  };

  useEffect(() => {
    fetchRecent();
    const interval = setInterval(async () => {
      try {
        const items = await api.listDrawings();
        setQueue(items.slice(0, 10));
      } catch (e) {}
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleFilesSelected = async (
    files: File[],
    config: ExtractionConfig,
    autoExtract: boolean
  ) => {
    try {
      setIsUploading(true);
      setError(null);
      await api.uploadDrawings(files, autoExtract, config.force_ocr);
      await fetchRecent();
    } catch (err: any) {
      setError(err.message || 'File upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-[#E4EAF2]">
        <div>
          <h1 className="text-xl font-bold text-[#172B4D] tracking-tight">
            Upload Engineering Drawings
          </h1>
          <p className="text-xs text-[#64748B] mt-0.5">
            Ingest multi-page PDF drawing sheets, raster scans (PNG, TIFF, JPG), or 2D CAD layouts (DWG, DXF)
          </p>
        </div>

        <Button
          variant="secondary"
          size="sm"
          icon={<History className="w-4 h-4 text-[#2563EB]" />}
          onClick={onNavigateHistory}
        >
          View Extraction History Logs
        </Button>
      </div>

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-md text-xs text-rose-700">
          {error}
        </div>
      )}

      {/* Upload Zone */}
      <UploadZone onFilesSelected={handleFilesSelected} isUploading={isUploading} />

      {/* Technical Feature Highlights */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
        <Card className="bg-[#F8FAFC]">
          <div className="p-4 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-[#172B4D]">
              <Cpu className="w-4 h-4 text-[#2563EB]" />
              <span>Hybrid Text & Vision</span>
            </div>
            <p className="text-[11px] text-[#64748B]">
              Extracts native vector PDF text layers or applies adaptive thresholding, deskew, and Tesseract OCR on scans.
            </p>
          </div>
        </Card>

        <Card className="bg-[#F8FAFC]">
          <div className="p-4 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-[#172B4D]">
              <FileCheck className="w-4 h-4 text-emerald-600" />
              <span>CAD Vector Tracing</span>
            </div>
            <p className="text-[11px] text-[#64748B]">
              Parses DWG and DXF layouts via LibreDWG and ezdxf, extracting MTEXT, block attributes, and geometry.
            </p>
          </div>
        </Card>

        <Card className="bg-[#F8FAFC]">
          <div className="p-4 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-[#172B4D]">
              <ShieldAlert className="w-4 h-4 text-amber-600" />
              <span>Review in History</span>
            </div>
            <p className="text-[11px] text-[#64748B]">
              Open any processed drawing from the Extraction History logs to inspect interactive overlays and verify fields.
            </p>
          </div>
        </Card>
      </div>

      {/* Recent Uploads Queue */}
      <UploadQueue
        queue={queue}
        onOpenWorkspace={onOpenWorkspace}
        onRefresh={fetchRecent}
      />
    </div>
  );
};
