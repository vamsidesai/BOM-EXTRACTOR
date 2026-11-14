import React from 'react';
import { LayoutDashboard, UploadCloud, Layers, ShieldCheck, Compass } from 'lucide-react';

interface NavbarProps {
  activeView: 'dashboard' | 'upload' | 'workspace';
  onNavigate: (view: 'dashboard' | 'upload' | 'workspace') => void;
  activeDrawingName?: string | null;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeView,
  onNavigate,
  activeDrawingName,
}) => {
  return (
    <header className="bg-white border-b border-[#E4EAF2] sticky top-0 z-40 select-none shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          {/* Logo & Product Name */}
          <div className="flex items-center gap-8">
            <div
              className="flex items-center gap-2.5 cursor-pointer"
              onClick={() => onNavigate('dashboard')}
            >
              <div className="w-8 h-8 rounded-lg bg-[#2563EB] text-white flex items-center justify-center font-bold shadow-sm">
                <Compass className="w-5 h-5 text-white" />
              </div>
              <div className="flex flex-col">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-lg text-[#172B4D] tracking-tight">BOMX</span>
                  <span className="text-[10px] px-1.5 py-0.2 bg-blue-50 text-blue-700 font-semibold rounded border border-blue-200">
                    ENGINEERING
                  </span>
                </div>
                <span className="text-[11px] text-[#64748B] -mt-1">Drawing BOM & Material Extractor</span>
              </div>
            </div>

            {/* Main Navigation Links */}
            <nav className="flex items-center space-x-1">
              <button
                onClick={() => onNavigate('dashboard')}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  activeView === 'dashboard'
                    ? 'bg-blue-50 text-[#2563EB]'
                    : 'text-[#64748B] hover:text-[#172B4D] hover:bg-slate-50'
                }`}
              >
                <LayoutDashboard className="w-4 h-4" />
                Dashboard
              </button>

              <button
                onClick={() => onNavigate('upload')}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  activeView === 'upload'
                    ? 'bg-blue-50 text-[#2563EB]'
                    : 'text-[#64748B] hover:text-[#172B4D] hover:bg-slate-50'
                }`}
              >
                <UploadCloud className="w-4 h-4" />
                Upload Drawings
              </button>

              <button
                onClick={() => onNavigate('workspace')}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  activeView === 'workspace'
                    ? 'bg-blue-50 text-[#2563EB]'
                    : 'text-[#64748B] hover:text-[#172B4D] hover:bg-slate-50'
                }`}
              >
                <Layers className="w-4 h-4" />
                Review Workspace
                {activeDrawingName && (
                  <span className="text-xs bg-slate-200/80 text-slate-700 px-1.5 py-0.5 rounded max-w-[130px] truncate">
                    {activeDrawingName}
                  </span>
                )}
              </button>
            </nav>
          </div>

          {/* Engine Status Indicator */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 text-xs text-[#64748B] bg-slate-50 px-2.5 py-1 rounded-full border border-slate-200">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="font-medium text-slate-700">OCR & CAD Engine Ready</span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};

