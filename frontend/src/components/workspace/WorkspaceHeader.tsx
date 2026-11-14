import React, { useState } from 'react';
import type { DrawingDetailResponse } from '../../types/api';
import { Button } from '../ui/Button';
import { StatusPill } from '../common/StatusPill';
import { ConfidenceBadge } from '../common/ConfidenceBadge';
import {
  ArrowLeft,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileText,
  FileCode,
  Save,
  RotateCw,
  ChevronDown,
  AlertTriangle,
} from 'lucide-react';
import { api } from '../../services/api';

interface WorkspaceHeaderProps {
  drawing: DrawingDetailResponse;
  onBack: () => void;
  onToggleVerified: () => void;
  onSave: () => void;
  isSaving: boolean;
  hasUnsavedChanges: boolean;
  onRerun: () => void;
}

export const WorkspaceHeader: React.FC<WorkspaceHeaderProps> = ({
  drawing,
  onBack,
  onToggleVerified,
  onSave,
  isSaving,
  hasUnsavedChanges,
  onRerun,
}) => {
  const [showExportMenu, setShowExportMenu] = useState(false);
  const meta = drawing.metadata;
  const res = drawing.result;
  const drawingNumber = res?.summary?.drawing_number || res?.title_block?.drawing_number?.value || meta.filename;
  const drawingTitle = res?.summary?.drawing_title || res?.title_block?.drawing_title?.value;
  const revision = res?.summary?.revision || res?.title_block?.revision?.value;

  const handleExport = (type: 'excel' | 'csv' | 'json') => {
    setShowExportMenu(false);
    if (type === 'excel') window.open(api.getExcelExportUrl(meta.id), '_blank');
    if (type === 'csv') window.open(api.getCsvExportUrl(meta.id), '_blank');
    if (type === 'json') window.open(api.getJsonExportUrl(meta.id), '_blank');
  };

  return (
    <div className="bg-white border-b border-[#E4EAF2] px-4 py-2.5 flex flex-col md:flex-row md:items-center justify-between gap-3 sticky top-14 z-30 shadow-xs">
      {/* Left: Back button + Drawing Identification */}
      <div className="flex items-center gap-3">
        <button
          onClick={onBack}
          className="p-1.5 rounded-md text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors shrink-0"
          title="Back to Dashboard"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded bg-blue-50 border border-blue-200 flex items-center justify-center text-[#2563EB] font-bold text-xs shrink-0">
            DRG
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm text-[#172B4D] tracking-tight">
                {drawingNumber}
              </span>
              {revision && (
                <span className="text-[11px] font-mono px-1.5 py-0.2 bg-slate-100 text-slate-700 font-semibold rounded border border-slate-200">
                  REV {revision}
                </span>
              )}
              <span className="text-[10px] font-mono px-1.5 py-0.2 bg-slate-100 text-slate-600 rounded">
                {meta.file_format}
              </span>
            </div>
            {drawingTitle && (
              <p className="text-xs text-[#64748B] line-clamp-1">{drawingTitle}</p>
            )}
          </div>
        </div>

        {/* Verification Status & Confidence Badges */}
        <div className="hidden lg:flex items-center gap-2 ml-4 pl-4 border-l border-[#E4EAF2]">
          <StatusPill
            status={meta.status}
            verified={meta.verified}
            reviewRequired={meta.review_required}
          />
          <ConfidenceBadge confidence={meta.mean_confidence} />
        </div>
      </div>

      {/* Right: Actions (Verified, Save, Export, Rerun) */}
      <div className="flex items-center gap-2 shrink-0">
        <Button
          variant={meta.verified ? 'success' : 'secondary'}
          size="sm"
          icon={<CheckCircle2 className="w-4 h-4" />}
          onClick={onToggleVerified}
          title={meta.verified ? 'Drawing verified. Click to unverify.' : 'Mark all fields as verified.'}
        >
          {meta.verified ? 'Verified' : 'Mark as Verified'}
        </Button>

        <Button
          variant={hasUnsavedChanges ? 'primary' : 'secondary'}
          size="sm"
          icon={<Save className="w-4 h-4" />}
          onClick={onSave}
          loading={isSaving}
          disabled={!hasUnsavedChanges}
        >
          {hasUnsavedChanges ? 'Save Changes' : 'Saved'}
        </Button>

        {/* Export Dropdown */}
        <div className="relative">
          <Button
            variant="secondary"
            size="sm"
            icon={<Download className="w-4 h-4" />}
            onClick={() => setShowExportMenu(!showExportMenu)}
          >
            Export
            <ChevronDown className="w-3.5 h-3.5 ml-1 text-slate-500" />
          </Button>

          {showExportMenu && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowExportMenu(false)}
              />
              <div className="absolute right-0 mt-1 w-48 bg-white rounded-md border border-[#E4EAF2] shadow-lg py-1 z-50 text-xs">
                <button
                  onClick={() => handleExport('excel')}
                  className="w-full px-3 py-2 text-left flex items-center gap-2 hover:bg-slate-50 text-[#172B4D]"
                >
                  <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
                  <span>Excel Workbook (.xlsx)</span>
                </button>
                <button
                  onClick={() => handleExport('csv')}
                  className="w-full px-3 py-2 text-left flex items-center gap-2 hover:bg-slate-50 text-[#172B4D]"
                >
                  <FileText className="w-4 h-4 text-blue-600" />
                  <span>CSV Tables (.zip)</span>
                </button>
                <button
                  onClick={() => handleExport('json')}
                  className="w-full px-3 py-2 text-left flex items-center gap-2 hover:bg-slate-50 text-[#172B4D]"
                >
                  <FileCode className="w-4 h-4 text-purple-600" />
                  <span>Structured JSON (.json)</span>
                </button>
              </div>
            </>
          )}
        </div>

        <button
          onClick={onRerun}
          title="Rerun Extraction Pipeline"
          className="p-2 text-slate-500 hover:text-blue-600 hover:bg-blue-50 rounded-md border border-[#E4EAF2] transition-colors"
        >
          <RotateCw className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};

