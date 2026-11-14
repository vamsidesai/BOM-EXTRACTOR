import React, { useState } from 'react';
import type { DrawingSummaryItem } from '../../types/api';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Button } from '../ui/Button';
import { ConfidenceBadge } from '../common/ConfidenceBadge';
import { StatusPill } from '../common/StatusPill';
import {
  FileText,
  Search,
  ExternalLink,
  Download,
  Trash2,
  FileSpreadsheet,
  AlertTriangle,
} from 'lucide-react';
import { api } from '../../services/api';

interface RecentDrawingsTableProps {
  drawings: DrawingSummaryItem[];
  onSelectDrawing: (id: string) => void;
  onRefresh: () => void;
}

export const RecentDrawingsTable: React.FC<RecentDrawingsTableProps> = ({
  drawings,
  onSelectDrawing,
  onRefresh,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const filtered = drawings.filter((d) => {
    const term = searchTerm.toLowerCase();
    return (
      d.filename.toLowerCase().includes(term) ||
      (d.drawing_number && d.drawing_number.toLowerCase().includes(term)) ||
      (d.drawing_title && d.drawing_title.toLowerCase().includes(term))
    );
  });

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!window.confirm('Are you sure you want to delete this drawing?')) return;
    try {
      setDeletingId(id);
      await api.deleteDrawing(id);
      onRefresh();
    } catch (err) {
      alert(`Delete failed: ${err}`);
    } finally {
      setDeletingId(null);
    }
  };

  const handleDownloadExcel = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    window.open(api.getExcelExportUrl(id), '_blank');
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 w-full">
          <div>
            <CardTitle>Recent Engineering Drawings</CardTitle>
            <p className="text-xs text-[#64748B] mt-0.5">
              Select any drawing to open the interactive Docsumo-style review workspace
            </p>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search drawings or parts..."
                className="pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-[#E4EAF2] rounded-md focus:outline-none focus:ring-1 focus:ring-[#2563EB] w-56 text-[#172B4D]"
              />
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#F8FAFC] border-b border-[#E4EAF2] text-[#64748B] font-semibold uppercase tracking-wider">
                <th className="py-3 px-4">Drawing Info</th>
                <th className="py-3 px-4">Format</th>
                <th className="py-3 px-4">BOM Items</th>
                <th className="py-3 px-4">Confidence</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E4EAF2]">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-400 text-xs">
                    {drawings.length === 0
                      ? 'No drawings uploaded yet. Upload a drawing or sample to begin.'
                      : 'No matching drawings found.'}
                  </td>
                </tr>
              ) : (
                filtered.map((d) => (
                  <tr
                    key={d.id}
                    onClick={() => onSelectDrawing(d.id)}
                    className="hover:bg-blue-50/40 cursor-pointer transition-colors group"
                  >
                    <td className="py-3.5 px-4">
                      <div className="flex items-start gap-2.5">
                        <div className="w-8 h-8 rounded bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-600 shrink-0 mt-0.5 group-hover:border-blue-300 group-hover:text-blue-600 transition-colors">
                          <FileText className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="font-semibold text-sm text-[#172B4D] group-hover:text-[#2563EB] transition-colors">
                            {d.drawing_number || d.filename}
                          </div>
                          <div className="text-[11px] text-[#64748B] line-clamp-1">
                            {d.drawing_title ? `${d.drawing_title} · ` : ''}
                            {d.filename}
                            {d.revision ? ` · Rev ${d.revision}` : ''}
                          </div>
                          {d.review_required && d.review_reasons && (
                            <div className="flex items-center gap-1 mt-1 text-[11px] text-amber-600">
                              <AlertTriangle className="w-3 h-3 shrink-0" />
                              <span className="line-clamp-1">{d.review_reasons}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </td>

                    <td className="py-3.5 px-4">
                      <span className="px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-slate-100 text-slate-700 border border-slate-200">
                        {d.file_format}
                      </span>
                    </td>

                    <td className="py-3.5 px-4">
                      <div className="font-medium text-[#172B4D]">{d.bom_items_count} rows</div>
                      <div className="text-[11px] text-[#64748B]">
                        {d.page_count} {d.page_count === 1 ? 'page' : 'pages'}
                      </div>
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

                    <td className="py-3.5 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                        <Button
                          variant="secondary"
                          size="xs"
                          icon={<ExternalLink className="w-3 h-3 text-[#2563EB]" />}
                          onClick={() => onSelectDrawing(d.id)}
                          title="Open Drawing Review Workspace"
                        >
                          Review
                        </Button>

                        <button
                          onClick={(e) => handleDownloadExcel(e, d.id)}
                          title="Download Excel Report"
                          className="p-1.5 rounded text-slate-500 hover:text-emerald-700 hover:bg-emerald-50 border border-transparent hover:border-emerald-200 transition-colors"
                        >
                          <FileSpreadsheet className="w-3.5 h-3.5" />
                        </button>

                        <button
                          onClick={(e) => handleDelete(e, d.id)}
                          disabled={deletingId === d.id}
                          title="Delete Drawing"
                          className="p-1.5 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-50 border border-transparent hover:border-rose-200 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
};

