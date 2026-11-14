import React, { useState, useRef, useEffect } from 'react';
import type { OverlayBox } from '../../types/api';
import {
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  Crosshair,
  Loader2,
  FileText,
  Table as TableIcon,
  StickyNote,
  GitCommit,
  Tag,
  CheckCircle2,
} from 'lucide-react';

interface DrawingViewerProps {
  imageUrl: string;
  pageCount: number;
  currentPage: number;
  onPageChange: (page: number) => void;
  overlays: OverlayBox[];
  highlightedOverlayId?: string | null;
  onSelectOverlay: (overlay: OverlayBox) => void;
  onSelectSection: (section: 'title_block' | 'bom' | 'notes' | 'revisions' | 'specs') => void;
  activeSection?: string;
}

export const DrawingViewer: React.FC<DrawingViewerProps> = ({
  imageUrl,
  pageCount,
  currentPage,
  onPageChange,
  overlays,
  highlightedOverlayId,
  onSelectOverlay,
  onSelectSection,
  activeSection = 'bom',
}) => {
  const [isImageLoading, setIsImageLoading] = useState<boolean>(true);
  const [showOverlays, setShowOverlays] = useState<boolean>(true);
  const [hoveredOverlay, setHoveredOverlay] = useState<OverlayBox | null>(null);
  const [activeRegionFilter, setActiveRegionFilter] = useState<string>('all');
  const imageRef = useRef<HTMLImageElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setIsImageLoading(true);
  }, [imageUrl]);

  const handleImageLoad = () => {
    setIsImageLoading(false);
  };

  // When clicking a region pill at the top
  const handlePillClick = (section: 'title_block' | 'bom' | 'notes' | 'revisions' | 'specs' | 'all') => {
    setActiveRegionFilter(section);
    if (section !== 'all') {
      onSelectSection(section);
    }
  };

  // Handle clicking directly on an overlay on the map
  const handleOverlayClick = (box: OverlayBox) => {
    onSelectOverlay(box);

    if (box.category === 'title_block' || box.type === 'title_field' || box.id.includes('tb_') || box.field === 'revision') {
      onSelectSection('title_block');
      setActiveRegionFilter('title_block');
    } else if (box.category === 'bom' || box.type === 'bom_row' || box.id.includes('bom')) {
      onSelectSection('bom');
      setActiveRegionFilter('bom');
    } else if (box.category === 'notes' || box.id.includes('note')) {
      onSelectSection('notes');
      setActiveRegionFilter('notes');
    } else if (box.category === 'revision' || box.type === 'region' && box.category === 'revision') {
      onSelectSection('revisions');
      setActiveRegionFilter('revisions');
    } else if (box.type === 'spec' || box.category === 'spec') {
      onSelectSection('specs');
      setActiveRegionFilter('specs');
    }
  };

  // Filter overlays based on activeRegionFilter
  const visibleOverlays = overlays.filter((o) => {
    if (!showOverlays) return false;
    if (activeRegionFilter === 'all') return true;
    if (activeRegionFilter === 'title_block') {
      return o.category === 'title_block' || o.type === 'title_field' || o.id.includes('tb_');
    }
    if (activeRegionFilter === 'bom') {
      return o.category === 'bom' || o.type === 'bom_row' || o.id.includes('bom');
    }
    if (activeRegionFilter === 'notes') {
      return o.category === 'notes' || o.id.includes('note');
    }
    if (activeRegionFilter === 'revisions') {
      return o.category === 'revision';
    }
    if (activeRegionFilter === 'specs') {
      return o.type === 'spec' || o.category === 'spec';
    }
    return true;
  });

  return (
    <div className="flex flex-col h-full bg-[#F1F5F9] relative select-none overflow-hidden border-r border-[#CBD5E1]">
      {/* Top Interactive Section Selector Bar */}
      <div className="bg-white border-b border-[#CBD5E1] px-4 py-2 flex flex-wrap items-center justify-between gap-3 text-xs z-30 shadow-xs shrink-0">
        {/* Sheet / Page Navigation */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => onPageChange(Math.max(1, currentPage - 1))}
            disabled={currentPage <= 1}
            className="p-1 rounded hover:bg-slate-100 disabled:opacity-40 text-slate-700"
            title="Previous Sheet"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>

          <span className="font-mono text-slate-800 font-semibold px-2.5 py-0.5 rounded bg-slate-100 border border-slate-200">
            Sheet {currentPage} / {pageCount}
          </span>

          <button
            onClick={() => onPageChange(Math.min(pageCount, currentPage + 1))}
            disabled={currentPage >= pageCount}
            className="p-1 rounded hover:bg-slate-100 disabled:opacity-40 text-slate-700"
            title="Next Sheet"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        {/* Region Map Selector Pills (Directly switches right panel & highlights map) */}
        <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg border border-slate-200 flex-wrap">
          <button
            onClick={() => handlePillClick('all')}
            className={`px-2.5 py-1 rounded text-xs font-semibold transition-all ${
              activeRegionFilter === 'all'
                ? 'bg-white text-slate-900 shadow-xs font-bold'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            All Regions
          </button>

          <button
            onClick={() => handlePillClick('title_block')}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-all ${
              activeRegionFilter === 'title_block' || activeSection === 'title_block'
                ? 'bg-[#2563EB] text-white shadow-xs font-bold'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Title Block & Rev</span>
          </button>

          <button
            onClick={() => handlePillClick('bom')}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-all ${
              activeRegionFilter === 'bom' || activeSection === 'bom'
                ? 'bg-[#16A34A] text-white shadow-xs font-bold'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <TableIcon className="w-3.5 h-3.5" />
            <span>BOM Table & Parts</span>
          </button>

          <button
            onClick={() => handlePillClick('notes')}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-all ${
              activeRegionFilter === 'notes' || activeSection === 'notes'
                ? 'bg-[#D97706] text-white shadow-xs font-bold'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <StickyNote className="w-3.5 h-3.5" />
            <span>Notes</span>
          </button>

          <button
            onClick={() => handlePillClick('specs')}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-all ${
              activeRegionFilter === 'specs' || activeSection === 'specs'
                ? 'bg-[#0284C7] text-white shadow-xs font-bold'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Tag className="w-3.5 h-3.5" />
            <span>Specs</span>
          </button>
        </div>

        {/* Toggle Overlays visibility */}
        <button
          onClick={() => setShowOverlays(!showOverlays)}
          className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium border transition-colors ${
            showOverlays
              ? 'bg-blue-50 text-[#2563EB] border-blue-200'
              : 'bg-white text-slate-600 border-slate-200'
          }`}
          title="Toggle region highlights on drawing"
        >
          {showOverlays ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
          <span>{showOverlays ? 'Highlights On' : 'Highlights Off'}</span>
        </button>
      </div>

      {/* Main Static Drawing Map Viewport */}
      <div className="flex-1 relative overflow-auto p-4 flex items-center justify-center">
        {isImageLoading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-slate-100/90 z-20">
            <Loader2 className="w-8 h-8 text-[#2563EB] animate-spin" />
            <span className="text-xs font-medium text-slate-600">Loading drawing sheet map...</span>
          </div>
        )}

        {/* Static Document Sheet Canvas */}
        <div
          ref={wrapperRef}
          className="relative inline-block max-w-full max-h-full bg-white shadow-[0_4px_30px_rgba(0,0,0,0.14)] rounded-xs border border-slate-300"
        >
          {/* Base Drawing Image (statically fitted, crisp, non-draggable) */}
          <img
            ref={imageRef}
            src={imageUrl}
            alt={`Drawing Sheet ${currentPage}`}
            onLoad={handleImageLoad}
            className="block max-w-full max-h-[calc(100vh-10rem)] object-contain bg-white select-none pointer-events-none"
            draggable={false}
          />

          {/* Percentage-locked Interactive Bounding Boxes Layer */}
          {showOverlays && (
            <div className="absolute inset-0 pointer-events-auto">
              {visibleOverlays.map((box) => {
                const [nx, ny, nw, nh] = box.norm;
                const isHighlighted = box.id === highlightedOverlayId;
                const isHovered = hoveredOverlay?.id === box.id;

                const isTitleSection =
                  box.category === 'title_block' || box.type === 'title_field' || box.id.includes('tb_');
                const isBomSection =
                  box.category === 'bom' || box.type === 'bom_row' || box.id.includes('bom');
                const isNotesSection =
                  box.category === 'notes' || box.id.includes('note');

                // Determine border color
                const color = isTitleSection
                  ? '#2563EB'
                  : isBomSection
                  ? '#16A34A'
                  : isNotesSection
                  ? '#D97706'
                  : box.color || '#2563EB';

                return (
                  <div
                    key={box.id}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleOverlayClick(box);
                    }}
                    onMouseEnter={() => setHoveredOverlay(box)}
                    onMouseLeave={() => setHoveredOverlay(null)}
                    style={{
                      left: `${nx * 100}%`,
                      top: `${ny * 100}%`,
                      width: `${nw * 100}%`,
                      height: `${nh * 100}%`,
                      borderColor: isHighlighted ? '#F59E0B' : color,
                      backgroundColor: isHighlighted
                        ? 'rgba(245, 158, 11, 0.28)'
                        : isHovered
                        ? 'rgba(37, 99, 235, 0.16)'
                        : 'rgba(37, 99, 235, 0.04)',
                      borderWidth: isHighlighted ? '3px' : '2px',
                    }}
                    className={`absolute cursor-pointer rounded-xs border transition-all duration-150 ${
                      isHighlighted
                        ? 'ring-4 ring-amber-400/60 shadow-lg z-30 animate-pulse'
                        : isHovered
                        ? 'z-20 shadow-md ring-2 ring-blue-300'
                        : 'z-10 hover:border-blue-600'
                    }`}
                  >
                    {/* Badge Pill pinned on region */}
                    {(isHovered || isHighlighted || box.type === 'region') && (
                      <div
                        style={{ backgroundColor: color }}
                        className="absolute -top-6 left-0 px-2 py-0.5 rounded text-[10px] font-bold text-white whitespace-nowrap shadow-md pointer-events-none flex items-center gap-1 z-40"
                      >
                        <Crosshair className="w-2.5 h-2.5" />
                        <span>{box.label}</span>
                        <span className="font-mono text-[9px] opacity-90">
                          ({Math.round(box.confidence * 100)}%)
                        </span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Floating Tooltip hint on hover */}
        {hoveredOverlay && (
          <div className="absolute bottom-4 left-4 z-40 bg-slate-900/90 backdrop-blur-xs text-white border border-slate-700 px-3.5 py-2 rounded-lg shadow-xl text-xs max-w-sm pointer-events-none animate-in fade-in">
            <div className="flex items-center justify-between gap-3">
              <span className="font-semibold text-blue-400">{hoveredOverlay.label}</span>
              <span className="font-mono text-[11px] text-emerald-400 font-medium">
                {Math.round(hoveredOverlay.confidence * 100)}% Conf
              </span>
            </div>
            {hoveredOverlay.value && (
              <p className="mt-1 text-slate-200 font-mono text-[11px] line-clamp-2">
                {hoveredOverlay.value}
              </p>
            )}
            <p className="text-[10px] text-blue-300 mt-1 font-medium">
              Click to list {hoveredOverlay.label} contents on the right →
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
