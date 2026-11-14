import React from 'react';
import {
  LayoutDashboard,
  UploadCloud,
  History,
  Compass,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

export type NavView = 'dashboard' | 'upload' | 'history';

interface SidebarProps {
  activeView: NavView | 'workspace';
  onNavigate: (view: NavView) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  reviewCount?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeView,
  onNavigate,
  collapsed,
  onToggleCollapse,
  reviewCount = 0,
}) => {
  const navItems = [
    {
      id: 'dashboard' as NavView,
      label: 'Dashboard',
      icon: LayoutDashboard,
      description: 'Metrics & quality overview',
    },
    {
      id: 'upload' as NavView,
      label: 'Upload Drawings',
      icon: UploadCloud,
      description: 'Ingest PDF & CAD files',
    },
    {
      id: 'history' as NavView,
      label: 'Extraction History',
      icon: History,
      description: 'Drawing logs & review workspace',
      badge: reviewCount > 0 ? `${reviewCount} review` : undefined,
      badgeColor: 'bg-amber-100 text-amber-800 font-semibold',
    },
  ];

  return (
    <aside
      className={`bg-[#172B4D] text-white flex flex-col transition-all duration-200 select-none z-40 shrink-0 border-r border-[#0F1D38] ${
        collapsed ? 'w-16' : 'w-64'
      }`}
    >
      {/* Brand Header */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-slate-700/60">
        <div
          className="flex items-center gap-3 cursor-pointer overflow-hidden"
          onClick={() => onNavigate('dashboard')}
          title="BOMX - Drawing BOM & Material Extractor"
        >
          <div className="w-9 h-9 rounded-lg bg-[#2563EB] text-white flex items-center justify-center shrink-0 shadow-sm font-bold">
            <Compass className="w-5 h-5 text-white" />
          </div>
          {!collapsed && (
            <div className="flex flex-col min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-base tracking-tight text-white">BOMX</span>
                <span className="text-[9px] font-semibold px-1 py-0.2 rounded bg-blue-500/20 text-blue-300 border border-blue-400/30">
                  ENGINEERING
                </span>
              </div>
              <span className="text-[10px] text-slate-400 truncate -mt-0.5">
                BOM & Material Extractor
              </span>
            </div>
          )}
        </div>

        <button
          onClick={onToggleCollapse}
          className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-700/50 transition-colors"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-2.5 py-4 space-y-1.5 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeView === item.id || (activeView === 'workspace' && item.id === 'history');

          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-medium transition-all group relative ${
                isActive
                  ? 'bg-[#2563EB] text-white shadow-sm font-semibold'
                  : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
              }`}
              title={collapsed ? item.label : undefined}
            >
              <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-white' : 'text-slate-400 group-hover:text-white'}`} />

              {!collapsed && (
                <div className="flex-1 flex items-center justify-between min-w-0 text-left">
                  <span className="truncate">{item.label}</span>
                  {item.badge && (
                    <span
                      className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${
                        item.badgeColor || 'bg-blue-400/20 text-blue-200'
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </div>
              )}

              {/* Tooltip on collapsed */}
              {collapsed && (
                <div className="absolute left-full ml-2 px-2.5 py-1 bg-slate-900 text-white text-xs rounded shadow-lg whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50">
                  {item.label}
                </div>
              )}
            </button>
          );
        })}
      </nav>

      {/* Engine Status Footer */}
      <div className="p-3 border-t border-slate-700/60 bg-[#0F1D38]/60 text-[11px] text-slate-400 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0" />
        {!collapsed && (
          <div className="flex flex-col truncate">
            <span className="text-slate-200 font-medium">Docsumo Engine Ready</span>
            <span className="text-[10px] text-slate-400">OCR & CAD Pipeline Online</span>
          </div>
        )}
      </div>
    </aside>
  );
};
