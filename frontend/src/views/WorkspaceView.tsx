import React, { useState, useEffect, useCallback } from 'react';
import type {
  DrawingDetailResponse,
  DrawingOverlaysResponse,
  OverlayBox,
  BomRow,
  RevisionRow,
  DrawingResult,
} from '../types/api';
import { api } from '../services/api';
import { WorkspaceHeader } from '../components/workspace/WorkspaceHeader';
import { DrawingViewer } from '../components/workspace/DrawingViewer';
import { ExtractionPanel, type WorkspaceTabType } from '../components/workspace/ExtractionPanel';
import { ExtractionConfigModal } from '../components/upload/ExtractionConfigModal';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface WorkspaceViewProps {
  drawingId: string;
  onBack: () => void;
}

export const WorkspaceView: React.FC<WorkspaceViewProps> = ({ drawingId, onBack }) => {
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [drawing, setDrawing] = useState<DrawingDetailResponse | null>(null);
  const [overlaysData, setOverlaysData] = useState<DrawingOverlaysResponse | null>(null);

  // Active state
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [activeTab, setActiveTab] = useState<WorkspaceTabType>('bom');
  const [focusedFieldKey, setFocusedFieldKey] = useState<string | null>(null);
  const [selectedRowIndex, setSelectedRowIndex] = useState<number | null>(null);
  const [highlightedOverlayId, setHighlightedOverlayId] = useState<string | null>(null);

  // Edit & Save state
  const [editableResult, setEditableResult] = useState<DrawingResult | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isRerunModalOpen, setIsRerunModalOpen] = useState<boolean>(false);

  const fetchDrawingData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [detail, overlays] = await Promise.all([
        api.getDrawingDetail(drawingId),
        api.getDrawingOverlays(drawingId).catch(() => null),
      ]);
      setDrawing(detail);
      setOverlaysData(overlays);
      if (detail.result) {
        setEditableResult(JSON.parse(JSON.stringify(detail.result)));
      }
      setHasUnsavedChanges(false);
    } catch (err: any) {
      setError(err.message || 'Failed to load drawing');
    } finally {
      setLoading(false);
    }
  }, [drawingId]);

  useEffect(() => {
    fetchDrawingData();
  }, [fetchDrawingData]);

  // Handle bidirectional interaction from left drawing overlay click
  const handleSelectOverlay = (box: OverlayBox) => {
    setHighlightedOverlayId(box.id);

    if (box.type === 'title_field' && box.field) {
      setActiveTab('title_block');
      setFocusedFieldKey(box.field);
      const el = document.getElementById(`tb-field-${box.field}`);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else if (box.type === 'bom_row' && box.rowIndex !== undefined) {
      setActiveTab('bom');
      setSelectedRowIndex(box.rowIndex);
    } else if (box.category === 'revision') {
      setActiveTab('revisions');
    } else if (box.category === 'notes' || box.type === 'spec') {
      setActiveTab('specs');
    }
  };

  // Locate title field on drawing
  const handleLocateTitleField = (key: string) => {
    setFocusedFieldKey(key);
    const box = currentOverlays.find((o) => o.field === key || o.id === `tb_${key}`);
    if (box) setHighlightedOverlayId(box.id);
  };

  // Locate BOM row on drawing
  const handleLocateBomRow = (index: number) => {
    setSelectedRowIndex(index);
    const box = currentOverlays.find((o) => o.type === 'bom_row' && o.rowIndex === index);
    if (box) setHighlightedOverlayId(box.id);
  };

  // Changes in Title Block
  const handleChangeTitleField = (key: string, val: string) => {
    if (!editableResult) return;
    const updated = { ...editableResult };
    if (!updated.title_block[key]) {
      updated.title_block[key] = { value: val, confidence: 1.0, raw: val };
    } else {
      updated.title_block[key].value = val;
    }
    setEditableResult(updated);
    setHasUnsavedChanges(true);
  };

  // Changes in BOM Table
  const handleChangeBom = (updatedBom: BomRow[]) => {
    if (!editableResult) return;
    setEditableResult({ ...editableResult, bom: updatedBom });
    setHasUnsavedChanges(true);
  };

  // Changes in Revisions
  const handleChangeRevisions = (updatedRevs: RevisionRow[]) => {
    if (!editableResult) return;
    setEditableResult({ ...editableResult, revisions: updatedRevs });
    setHasUnsavedChanges(true);
  };

  // Changes in Notes
  const handleChangeNotes = (updatedNotes: any[]) => {
    if (!editableResult) return;
    setEditableResult({ ...editableResult, notes: updatedNotes });
    setHasUnsavedChanges(true);
  };

  // Save changes to backend
  const handleSave = async () => {
    if (!editableResult) return;
    try {
      setIsSaving(true);
      await api.updateDrawing(drawingId, {
        title_block: editableResult.title_block,
        bom: editableResult.bom,
        revisions: editableResult.revisions,
        notes: editableResult.notes,
      });
      setHasUnsavedChanges(false);
      // Refresh drawing metadata
      const updatedDetail = await api.getDrawingDetail(drawingId);
      setDrawing(updatedDetail);
    } catch (err: any) {
      alert(`Save failed: ${err.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  // Toggle verification status
  const handleToggleVerified = async () => {
    if (!drawing) return;
    const newStatus = !drawing.metadata.verified;
    try {
      await api.updateDrawing(drawingId, { verified: newStatus });
      setDrawing({
        ...drawing,
        metadata: { ...drawing.metadata, verified: newStatus },
      });
    } catch (err: any) {
      alert(`Failed to update verification status: ${err.message}`);
    }
  };

  // Rerun extraction with custom configuration
  const handleRerunExtraction = async (cfg: any) => {
    try {
      await api.startExtraction(drawingId, cfg);
      fetchDrawingData();
    } catch (err: any) {
      alert(`Rerun failed: ${err.message}`);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3 text-slate-500">
        <RefreshCw className="w-8 h-8 animate-spin text-[#2563EB]" />
        <p className="text-sm font-medium">Loading drawing and extraction overlays...</p>
      </div>
    );
  }

  if (error || !drawing) {
    return (
      <div className="p-8 max-w-xl mx-auto text-center space-y-4">
        <AlertCircle className="w-10 h-10 text-rose-500 mx-auto" />
        <h3 className="text-base font-semibold text-[#172B4D]">Drawing Review Workspace Error</h3>
        <p className="text-xs text-[#64748B]">{error || 'Unable to find drawing details.'}</p>
        <button
          onClick={onBack}
          className="text-xs text-[#2563EB] hover:underline font-medium"
        >
          ← Return to Dashboard
        </button>
      </div>
    );
  }

  const currentOverlays = overlaysData?.overlays?.[currentPage] || [];
  const imageUrl = api.getPageImageUrl(drawingId, currentPage);
  const pageCount = drawing.metadata.page_count || 1;

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)] overflow-hidden">
      {/* Workspace Header Toolbar */}
      <WorkspaceHeader
        drawing={drawing}
        onBack={onBack}
        onToggleVerified={handleToggleVerified}
        onSave={handleSave}
        isSaving={isSaving}
        hasUnsavedChanges={hasUnsavedChanges}
        onRerun={() => setIsRerunModalOpen(true)}
      />

      {/* Two-Panel Split Layout */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Left Panel: Drawing Viewer */}
        <div className="w-full md:w-7/12 h-1/2 md:h-full border-r border-[#E4EAF2] relative">
          <DrawingViewer
            imageUrl={imageUrl}
            pageCount={pageCount}
            currentPage={currentPage}
            onPageChange={setCurrentPage}
            overlays={currentOverlays}
            highlightedOverlayId={highlightedOverlayId}
            onSelectOverlay={handleSelectOverlay}
          />
        </div>

        {/* Right Panel: Extracted Information */}
        <div className="w-full md:w-5/12 h-1/2 md:h-full bg-white relative">
          {editableResult ? (
            <ExtractionPanel
              result={editableResult}
              activeTab={activeTab}
              onTabChange={setActiveTab}
              onChangeTitleField={handleChangeTitleField}
              onLocateTitleField={handleLocateTitleField}
              focusedFieldKey={focusedFieldKey}
              onChangeBom={handleChangeBom}
              onLocateBomRow={handleLocateBomRow}
              selectedRowIndex={selectedRowIndex}
              onChangeRevisions={handleChangeRevisions}
              onChangeNotes={handleChangeNotes}
            />
          ) : (
            <div className="p-8 text-center text-slate-400 text-xs">
              No extraction results available yet.
            </div>
          )}
        </div>
      </div>

      <ExtractionConfigModal
        isOpen={isRerunModalOpen}
        onClose={() => setIsRerunModalOpen(false)}
        config={{
          dpi: 300,
          ocr_lang: 'eng',
          force_ocr: true,
          cell_ocr: true,
          deskew: true,
          auto_rotate: true,
          low_conf_threshold: 0.65,
        }}
        onSave={handleRerunExtraction}
      />
    </div>
  );
};
