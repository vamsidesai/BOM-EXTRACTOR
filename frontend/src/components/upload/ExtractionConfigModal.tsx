import React, { useState } from 'react';
import type { ExtractionConfig } from '../../types/api';
import { Button } from '../ui/Button';
import { Settings, X } from 'lucide-react';

interface ExtractionConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  config: ExtractionConfig;
  onSave: (config: ExtractionConfig) => void;
}

export const ExtractionConfigModal: React.FC<ExtractionConfigModalProps> = ({
  isOpen,
  onClose,
  config,
  onSave,
}) => {
  const [localCfg, setLocalCfg] = useState<ExtractionConfig>({ ...config });

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave(localCfg);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
      <div className="bg-white rounded-lg border border-[#E4EAF2] shadow-xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        <div className="px-5 py-4 border-b border-[#E4EAF2] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Settings className="w-4 h-4 text-[#2563EB]" />
            <h3 className="font-semibold text-sm text-[#172B4D]">Extraction Engine Parameters</h3>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-1 rounded hover:bg-slate-100"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4 text-xs">
          <div>
            <label className="block font-medium text-[#172B4D] mb-1">Rendering Resolution (DPI)</label>
            <select
              value={localCfg.dpi}
              onChange={(e) => setLocalCfg({ ...localCfg, dpi: Number(e.target.value) })}
              className="w-full px-3 py-1.5 border border-[#E4EAF2] rounded bg-white text-[#172B4D] focus:ring-1 focus:ring-[#2563EB]"
            >
              <option value={150}>150 DPI (Fastest preview)</option>
              <option value={300}>300 DPI (Standard engineering drawing)</option>
              <option value={400}>400 DPI (High-detail scanned drawing)</option>
            </select>
            <p className="text-[11px] text-[#64748B] mt-0.5">Controls rasterization clarity for OCR and CAD line trace.</p>
          </div>

          <div>
            <label className="block font-medium text-[#172B4D] mb-1">OCR Language</label>
            <select
              value={localCfg.ocr_lang}
              onChange={(e) => setLocalCfg({ ...localCfg, ocr_lang: e.target.value })}
              className="w-full px-3 py-1.5 border border-[#E4EAF2] rounded bg-white text-[#172B4D] focus:ring-1 focus:ring-[#2563EB]"
            >
              <option value="eng">English (eng)</option>
              <option value="deu">German (deu)</option>
              <option value="fra">French (fra)</option>
            </select>
          </div>

          <div>
            <label className="block font-medium text-[#172B4D] mb-1">
              Low Confidence Floor ({Math.round(localCfg.low_conf_threshold * 100)}%)
            </label>
            <input
              type="range"
              min={0.4}
              max={0.9}
              step={0.05}
              value={localCfg.low_conf_threshold}
              onChange={(e) => setLocalCfg({ ...localCfg, low_conf_threshold: parseFloat(e.target.value) })}
              className="w-full accent-[#2563EB]"
            />
            <span className="text-[11px] text-[#64748B]">Threshold below which fields are flagged for manual review.</span>
          </div>

          <div className="space-y-2 pt-2 border-t border-[#E4EAF2]">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={localCfg.cell_ocr}
                onChange={(e) => setLocalCfg({ ...localCfg, cell_ocr: e.target.checked })}
                className="rounded border-[#E4EAF2] text-[#2563EB] focus:ring-[#2563EB]"
              />
              <span className="text-[#172B4D] font-medium">Cell-by-cell OCR Re-read (higher scan precision)</span>
            </label>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={localCfg.deskew}
                onChange={(e) => setLocalCfg({ ...localCfg, deskew: e.target.checked })}
                className="rounded border-[#E4EAF2] text-[#2563EB] focus:ring-[#2563EB]"
              />
              <span className="text-[#172B4D] font-medium">Automatic Deskew (correct crooked scans)</span>
            </label>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={localCfg.auto_rotate}
                onChange={(e) => setLocalCfg({ ...localCfg, auto_rotate: e.target.checked })}
                className="rounded border-[#E4EAF2] text-[#2563EB] focus:ring-[#2563EB]"
              />
              <span className="text-[#172B4D] font-medium">Auto-detect Orientation (OSD 90°/180°/270°)</span>
            </label>
          </div>

          <div className="flex items-center justify-end gap-2 pt-4 border-t border-[#E4EAF2]">
            <Button variant="secondary" size="sm" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" type="submit">
              Apply Settings
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};

