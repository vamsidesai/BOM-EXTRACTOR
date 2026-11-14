import React, { useState, useRef } from 'react';
import { UploadCloud, FileType, Settings, CheckCircle2, AlertCircle } from 'lucide-react';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { ExtractionConfigModal } from './ExtractionConfigModal';
import type { ExtractionConfig } from '../../types/api';

interface UploadZoneProps {
  onFilesSelected: (files: File[], config: ExtractionConfig, autoExtract: boolean) => void;
  isUploading: boolean;
}

const SUPPORTED_FORMATS = ['PDF', 'PNG', 'JPG / JPEG', 'TIFF', 'DWG', 'DXF'];

export const UploadZone: React.FC<UploadZoneProps> = ({ onFilesSelected, isUploading }) => {
  const [isDragOver, setIsDragOver] = useState(false);
  const [autoExtract, setAutoExtract] = useState(true);
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [config, setConfig] = useState<ExtractionConfig>({
    dpi: 300,
    ocr_lang: 'eng',
    force_ocr: false,
    cell_ocr: true,
    deskew: true,
    auto_rotate: true,
    low_conf_threshold: 0.65,
  });

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const files = Array.from(e.dataTransfer.files);
      onFilesSelected(files, config, autoExtract);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const files = Array.from(e.target.files);
      onFilesSelected(files, config, autoExtract);
    }
  };

  return (
    <div className="space-y-4">
      <Card
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`border-2 border-dashed transition-all duration-200 cursor-pointer ${
          isDragOver
            ? 'border-[#2563EB] bg-blue-50/50 shadow-md'
            : 'border-[#CBD5E1] hover:border-slate-400 bg-white'
        }`}
        onClick={() => fileInputRef.current?.click()}
      >
        <div className="p-10 flex flex-col items-center justify-center text-center">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileInput}
            multiple
            accept=".pdf,.png,.jpg,.jpeg,.tiff,.tif,.dwg,.dxf"
            className="hidden"
          />

          <div className="w-14 h-14 rounded-full bg-blue-50 text-[#2563EB] flex items-center justify-center mb-4">
            <UploadCloud className="w-7 h-7" />
          </div>

          <h3 className="text-base font-semibold text-[#172B4D]">
            Upload Engineering Drawings & CAD Files
          </h3>
          <p className="text-xs text-[#64748B] max-w-md mt-1 mb-4">
            Drag and drop 2D PDF drawing sheets, high-resolution scans, DWG, or DXF files to automatically extract Title Blocks, BOM tables, and Material specifications.
          </p>

          <Button
            variant="primary"
            size="md"
            loading={isUploading}
            onClick={(e) => {
              e.stopPropagation();
              fileInputRef.current?.click();
            }}
          >
            Browse Files from Computer
          </Button>

          {/* Supported Format Pills */}
          <div className="mt-6 pt-5 border-t border-[#E4EAF2] w-full flex flex-wrap items-center justify-center gap-2">
            <span className="text-xs text-[#64748B] font-medium mr-1">Supported Formats:</span>
            {SUPPORTED_FORMATS.map((fmt) => (
              <span
                key={fmt}
                className="text-[11px] font-mono font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200"
              >
                {fmt}
              </span>
            ))}
          </div>
        </div>
      </Card>

      {/* Upload Settings Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-1 text-xs text-[#64748B]">
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={autoExtract}
            onChange={(e) => setAutoExtract(e.target.checked)}
            className="rounded border-[#E4EAF2] text-[#2563EB] focus:ring-[#2563EB]"
          />
          <span className="text-[#172B4D] font-medium">
            Automatically trigger OCR & BOM table extraction upon upload
          </span>
        </label>

        <button
          type="button"
          onClick={() => setIsConfigOpen(true)}
          className="flex items-center gap-1.5 text-[#2563EB] hover:text-[#1D4ED8] font-medium transition-colors"
        >
          <Settings className="w-3.5 h-3.5" />
          <span>Extraction Parameters ({config.dpi} DPI, {config.ocr_lang.toUpperCase()})</span>
        </button>
      </div>

      <ExtractionConfigModal
        isOpen={isConfigOpen}
        onClose={() => setIsConfigOpen(false)}
        config={config}
        onSave={setConfig}
      />
    </div>
  );
};

