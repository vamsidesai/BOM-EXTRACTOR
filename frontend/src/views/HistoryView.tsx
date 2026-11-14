import React, { useState, useEffect } from 'react';
import type { DrawingSummaryItem } from '../types/api';
import { api } from '../services/api';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { ConfidenceBadge } from '../components/common/ConfidenceBadge';
import { StatusPill } from '../components/common/StatusPill';
import {
  History,
  Search,
  ExternalLink,
  FileSpreadsheet,
  FileText,
  FileCode,
  Trash2,
  RefreshCw,
  Filter,
  CheckSquare,
  Square,
  AlertTriangle,
} from 'lucide-react';

interface HistoryViewProps {
  onSelectDrawing: (id: string) => void;
  onRefreshStats?: () => void;
}

export const HistoryView: React.FC<HistoryViewProps> = ({
  onSelectDrawing,
  onRefreshStats,
}) => {
  const [drawings, setDrawings] = useState<DrawingSummaryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'verified' | 'needs_review' | 'failed'>('all');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const loadDrawings = async () => {
    try {
      setLoading(true);
      const items = await api.listDrawings();
      setDrawings(items);
      if (onRefreshStats) onRefreshStats();
    } catch (e) {
      // Ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDrawings();
  }, []);

  const filtered = drawings.filter((d) => {
    const term = searchTerm.toLowerCase();
    const matchesSearch =
      d.filename.toLowerCase().includes(term) ||
      (d.drawing_number && d.drawing_number.toLowerCase().includes(term)) ||
      (d.drawing_title && d.drawing_title.toLowerCase().includes(term));

    if (!matchesSearch) return false;

    if (statusFilter === 'verified') return d.verified;
    if (statusFilter === 'needs_review') return !d.verified && (d.review_required || (d.mean_confidence && d.mean_confidence < 0.85));
    if (statusFilter === 'failed') return d.status === 'failed';
    return true;
  });

  const toggleSelectAll = () => {
    if (selectedIds.size === filtered.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filtered.map((d) => d.id)));
    }
  };

  const toggleSelectOne = (id: string) => {
    const updated = new Set(selectedIds);
    if (updated.has(id)) updated.delete(id);
    else updated.add(id);
    setSelectedIds(updated);
  };

  const handleDeleteSingle = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!window.confirm('Delete this drawing record?')) return;
    try {
      await api.deleteDrawing(id);
      loadDrawings();
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-[#E4EAF2]">
        <div>
          <h1 className="text-xl font-bold text-[#172B4D] tracking-tight flex items-center gap-2">
            <History className="w-5 h-5 text-[#2563EB]" />
            <span>Extraction History & Archive</span>
          </h1>
          <p className="text-xs text-[#64748B] mt-0.5">
            Audit trail of all processed engineering drawings, verification logs, and exported packages
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
            onClick={loadDrawings}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <Card>
        <div className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[#64748B] font-semibold flex items-center gap-1">
              <Filter className="w-3.5 h-3.5" />
              <span>Status:</span>
            </span>

            {(['all', 'verified', 'needs_review', 'failed'] as const).map((filter) => (
              <button
                key={filter}
                onClick={() => setStatusFilter(filter)}
                className={`px-3 py-1 rounded-full font-medium transition-colors ${
                  statusFilter === filter
                    ? 'bg-[#2563EB] text-white'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}
              >
                {filter === 'all'
                  ? `All (${drawings.length})`
                  : filter === 'verified'
                  ? `Verified (${drawings.filter((d) => d.verified).length})`
                  : filter === 'needs_review'
                  ? `Needs Review (${drawings.filter((d) => !d.verified && d.review_required).length})`
                  : `Failed (${drawings.filter((d) => d.status === 'failed').length})`}
              </button>
            ))}
          </div>

          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search drawings or files..."
              className="pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-[#E4EAF2] rounded-md focus:outline-none focus:ring-1 focus:ring-[#2563EB] w-64 text-[#172B4D]"
            />
          </div>
        </div>
      </Card>

      {/* Data Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-[#F8FAFC] border-b border-[#E4EAF2] text-[#64748B] font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4 w-10">
                    <button
                      onClick={toggleSelectAll}
                      className="text-slate-500 hover:text-slate-700"
                    >
                      {selectedIds.size > 0 && selectedIds.size === filtered.length ? (
                        <CheckSquare className="w-4 h-4 text-[#2563EB]" />
                      ) : (
                        <Square className="w-4 h-4" />
                      )}
                    </button>
                  </th>
                  <th className="py-3 px-4">Drawing Information</th>
                  <th className="py-3 px-4">Format</th>
                  <th className="py-3 px-4">Uploaded At</th>
                  <th className="py-3 px-4">BOM Items</th>
                  <th className="py-3 px-4">OCR Conf</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E4EAF2]">
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-12 text-center text-slate-400">
                      No matching drawing records found in history.
                    </td>
                  </tr>
                ) : (
                  filtered.map((d) => {
                    const isSelected = selectedIds.has(d.id);
                    return (
                      <tr
                        key={d.id}
                        onClick={() => onSelectDrawing(d.id)}
                        className={`cursor-pointer transition-colors ${
                          isSelected ? 'bg-blue-50/60' : 'hover:bg-slate-50'
                        }`}
                      >
                        <td className="py-3.5 px-4" onClick={(e) => e.stopPropagation()}>
                          <button
                            onClick={() => toggleSelectOne(d.id)}
                            className="text-slate-400 hover:text-slate-700"
                          >
                            {isSelected ? (
                              <CheckSquare className="w-4 h-4 text-[#2563EB]" />
                            ) : (
                              <Square className="w-4 h-4" />
                            )}
                          </button>
                        </td>

                        <td className="py-3.5 px-4">
                          <div className="font-semibold text-sm text-[#172B4D] hover:text-[#2563EB]">
                            {d.drawing_number || d.filename}
                          </div>
                          <div className="text-[11px] text-[#64748B]">
                            {d.drawing_title ? `${d.drawing_title} · ` : ''}
                            {d.filename}
                            {d.revision ? ` · Rev ${d.revision}` : ''}
                          </div>
                        </td>

                        <td className="py-3.5 px-4">
                          <span className="px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-slate-100 text-slate-700 border border-slate-200">
                            {d.file_format}
                          </span>
                        </td>

                        <td className="py-3.5 px-4 font-mono text-[11px] text-slate-600">
                          {new Date(d.uploaded_at).toLocaleDateString()}{' '}
                          <span className="text-slate-400">
                            {new Date(d.uploaded_at).toLocaleTimeString([], {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </span>
                        </td>

                        <td className="py-3.5 px-4 font-medium text-[#172B4D]">
                          {d.bom_items_count} items
                        </td>

                        <td className="py-3.5 px-4">
                          <ConfidenceBadge confidence={d.mean_confidence} />
                        </td>

                        <td className="py-3.5 px-4">
                          <StatusPill
                            status={d.status}
                            verified={d.verified}
                            reviewRequired={d.review_required}
                          />
                        </td>

                        <td className="py-3.5 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center justify-end gap-1.5">
                            <Button
                              variant="secondary"
                              size="xs"
                              icon={<ExternalLink className="w-3 h-3 text-[#2563EB]" />}
                              onClick={() => onSelectDrawing(d.id)}
                            >
                              Review
                            </Button>

                            <button
                              onClick={() => window.open(api.getExcelExportUrl(d.id), '_blank')}
                              title="Export Excel"
                              className="p-1.5 rounded hover:bg-emerald-50 text-slate-400 hover:text-emerald-700"
                            >
                              <FileSpreadsheet className="w-3.5 h-3.5" />
                            </button>

                            <button
                              onClick={(e) => handleDeleteSingle(e, d.id)}
                              title="Delete"
                              className="p-1.5 rounded hover:bg-rose-50 text-slate-400 hover:text-rose-600"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
