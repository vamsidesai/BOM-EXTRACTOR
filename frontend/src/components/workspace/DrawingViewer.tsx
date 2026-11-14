import React, { useState, useRef, useEffect, useCallback } from 'react';
import type { OverlayBox } from '../../types/api';
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  Layers,
  Crosshair,
} from 'lucide-react';

interface DrawingViewerProps {
  imageUrl: string;
  pageCount: number;
  currentPage: number;
  onPageChange: (page: number) => void;
  overlays: OverlayBox[];
  highlightedOverlayId?: string | null;
  onSelectOverlay: (overlay: OverlayBox) => void;
}

export const DrawingViewer: React.FC<DrawingViewerProps> = ({
  imageUrl,
  pageCount,
  currentPage,
  onPageChange,
  overlays,
  highlightedOverlayId,
  onSelectOverlay,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);

  // Pan & Zoom state
  const [scale, setScale] = useState<number>(1);
  const [position, setPosition] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // Overlays control
  const [showOverlays, setShowOverlays] = useState<boolean>(true);
  const [overlayFilter, setOverlayFilter] = useState<'all' | 'title_block' | 'bom' | 'revision' | 'notes'>('all');
  const [hoveredOverlay, setHoveredOverlay] = useState<OverlayBox | null>(null);

  // Image natural dimensions
  const [imgNaturalSize, setImgNaturalSize] = useState<{ width: number; height: number }>({ width: 0, height: 0 });

  const handleImageLoad = () => {
    if (imageRef.current) {
      setImgNaturalSize({
        width: imageRef.current.naturalWidth,
        height: imageRef.current.naturalHeight,
      });
      fitToScreen();
    }
  };

  const fitToScreen = useCallback(() => {
    if (!containerRef.current || !imageRef.current) return;
    const container = containerRef.current;
    const img = imageRef.current;
    if (!img.naturalWidth || !img.naturalHeight) return;

    const padding = 32;
    const scaleX = (container.clientWidth - padding) / img.naturalWidth;
    const scaleY = (container.clientHeight - padding) / img.naturalHeight;
    const initialScale = Math.min(scaleX, scaleY, 1.2);

    setScale(initialScale);
    setPosition({
      x: (container.clientWidth - img.naturalWidth * initialScale) / 2,
      y: (container.clientHeight - img.naturalHeight * initialScale) / 2,
    });
  }, []);

  useEffect(() => {
    fitToScreen();
  }, [imageUrl, fitToScreen]);

  // Center on highlighted overlay if requested
  useEffect(() => {
    if (!highlightedOverlayId || !containerRef.current || !imageRef.current) return;
    const target = overlays.find((o) => o.id === highlightedOverlayId);
    if (!target) return;

    const [nx, ny, nw, nh] = target.norm;
    const imgW = imgNaturalSize.width || imageRef.current.naturalWidth;
    const imgH = imgNaturalSize.height || imageRef.current.naturalHeight;

    const boxCenterX = (nx + nw / 2) * imgW;
    const boxCenterY = (ny + nh / 2) * imgH;

    const containerW = containerRef.current.clientWidth;
    const containerH = containerRef.current.clientHeight;

    const targetScale = Math.max(scale, 1.2);
    setScale(targetScale);
    setPosition({
      x: containerW / 2 - boxCenterX * targetScale,
      y: containerH / 2 - boxCenterY * targetScale,
    });
  }, [highlightedOverlayId, overlays, imgNaturalSize]);

  // Zoom handlers
  const handleZoom = (factor: number) => {
    setScale((prev) => Math.min(Math.max(prev * factor, 0.2), 5));
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 0.85;
    handleZoom(factor);
  };

  // Drag pan handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return; // Only left mouse button
    setIsDragging(true);
    setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setPosition({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Filter overlays
  const visibleOverlays = overlays.filter((o) => {
    if (!showOverlays) return false;
    if (overlayFilter === 'all') return true;
    if (overlayFilter === 'title_block') return o.type === 'title_field' || o.category === 'title_block';
    if (overlayFilter === 'bom') return o.type === 'bom_row' || o.category === 'bom';
    if (overlayFilter === 'revision') return o.type === 'region' && o.category === 'revision';
    if (overlayFilter === 'notes') return o.category === 'notes' || o.type === 'spec';
    return true;
  });

  return (
    <div className="flex flex-col h-full bg-[#1E293B] relative select-none overflow-hidden">
      {/* Top Toolbar */}
      <div className="bg-[#0F172A] border-b border-slate-700/80 px-4 py-2 flex items-center justify-between text-xs text-slate-300 z-20 shrink-0">
        {/* Page Navigation */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => onPageChange(Math.max(1, currentPage - 1))}
            disabled={currentPage <= 1}
            className="p-1 rounded hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed text-slate-300"
            title="Previous Page"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="font-mono text-slate-200 px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
            Sheet {currentPage} of {pageCount}
          </span>
          <button
            onClick={() => onPageChange(Math.min(pageCount, currentPage + 1))}
            disabled={currentPage >= pageCount}
            className="p-1 rounded hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed text-slate-300"
            title="Next Page"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        {/* Overlay Filters & Toggles */}
        <div className="hidden sm:flex items-center gap-1 bg-slate-800/80 p-0.5 rounded border border-slate-700">
          <button
            onClick={() => setShowOverlays(!showOverlays)}
            className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-colors ${
              showOverlays ? 'bg-[#2563EB] text-white' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {showOverlays ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
            <span>Overlays</span>
          </button>

          {showOverlays && (
            <div className="flex items-center space-x-0.5 border-l border-slate-700 pl-1">
              {(['all', 'title_block', 'bom', 'notes'] as const).map((filter) => (
                <button
                  key={filter}
                  onClick={() => setOverlayFilter(filter)}
                  className={`px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider transition-colors ${
                    overlayFilter === filter
                      ? 'bg-slate-700 text-slate-100 font-bold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {filter.replace('_', ' ')}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Zoom Controls */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => handleZoom(0.85)}
            className="p-1.5 rounded hover:bg-slate-800 text-slate-300"
            title="Zoom Out"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <span className="font-mono text-[11px] w-12 text-center text-slate-300">
            {Math.round(scale * 100)}%
          </span>
          <button
            onClick={() => handleZoom(1.15)}
            className="p-1.5 rounded hover:bg-slate-800 text-slate-300"
            title="Zoom In"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <div className="w-[1px] h-4 bg-slate-700 mx-1" />
          <button
            onClick={fitToScreen}
            className="p-1.5 rounded hover:bg-slate-800 text-slate-300"
            title="Fit to Screen"
          >
            <Maximize2 className="w-4 h-4" />
          </button>
          <button
            onClick={() => {
              setScale(1);
              setPosition({ x: 20, y: 20 });
            }}
            className="p-1.5 rounded hover:bg-slate-800 text-slate-300"
            title="Reset Zoom"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main Viewport Container */}
      <div
        ref={containerRef}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        className={`flex-1 relative overflow-hidden bg-[#0F172A] ${
          isDragging ? 'cursor-grabbing' : 'cursor-grab'
        }`}
      >
        <div
          style={{
            transform: `translate(${position.x}px, ${position.y}px) scale(${scale})`,
            transformOrigin: '0 0',
            transition: isDragging ? 'none' : 'transform 0.08s ease-out',
          }}
          className="absolute left-0 top-0 inline-block shadow-2xl"
        >
          {/* Base Drawing Image */}
          <img
            ref={imageRef}
            src={imageUrl}
            alt={`Drawing Sheet ${currentPage}`}
            onLoad={handleImageLoad}
            className="pointer-events-none block max-w-none bg-white rounded-xs shadow-md"
            draggable={false}
          />

          {/* Konva / Interactive Overlay Boxes Layer */}
          {showOverlays && imgNaturalSize.width > 0 && (
            <div
              className="absolute inset-0 pointer-events-auto"
              style={{ width: imgNaturalSize.width, height: imgNaturalSize.height }}
            >
              {visibleOverlays.map((box) => {
                const [nx, ny, nw, nh] = box.norm;
                const isHighlighted = box.id === highlightedOverlayId;
                const isHovered = hoveredOverlay?.id === box.id;

                const left = nx * imgNaturalSize.width;
                const top = ny * imgNaturalSize.height;
                const width = nw * imgNaturalSize.width;
                const height = nh * imgNaturalSize.height;

                return (
                  <div
                    key={box.id}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectOverlay(box);
                    }}
                    onMouseEnter={() => setHoveredOverlay(box)}
                    onMouseLeave={() => setHoveredOverlay(null)}
                    style={{
                      left: `${left}px`,
                      top: `${top}px`,
                      width: `${width}px`,
                      height: `${height}px`,
                      borderColor: isHighlighted ? '#F59E0B' : box.color,
                      backgroundColor: isHighlighted
                        ? 'rgba(245, 158, 11, 0.25)'
                        : isHovered
                        ? 'rgba(37, 99, 235, 0.2)'
                        : 'rgba(37, 99, 235, 0.04)',
                      borderWidth: isHighlighted ? '3px' : '1.5px',
                    }}
                    className={`absolute cursor-pointer rounded-xs border transition-all duration-150 ${
                      isHighlighted
                        ? 'ring-4 ring-amber-400/50 shadow-lg z-30 animate-pulse'
                        : isHovered
                        ? 'z-20 shadow-md'
                        : 'z-10'
                    }`}
                  >
                    {/* Badge tag on box corner */}
                    {(isHovered || isHighlighted) && (
                      <div
                        style={{ backgroundColor: box.color }}
                        className="absolute -top-6 left-0 px-1.5 py-0.5 rounded text-[10px] font-semibold text-white whitespace-nowrap shadow-md pointer-events-none flex items-center gap-1 z-40"
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

        {/* Floating Tooltip info on hover */}
        {hoveredOverlay && (
          <div className="absolute bottom-4 left-4 z-40 bg-slate-900/90 backdrop-blur-xs text-white border border-slate-700 px-3 py-2 rounded-md shadow-xl text-xs max-w-sm pointer-events-none animate-in fade-in">
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
            <p className="text-[10px] text-slate-400 mt-0.5">Click to focus in extraction panel</p>
          </div>
        )}
      </div>
    </div>
  );
};

