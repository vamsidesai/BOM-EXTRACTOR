import React from 'react';
import type { RevisionRow } from '../../types/api';
import { ConfidenceBadge } from '../common/ConfidenceBadge';
import { GitCommit, Plus, Trash2 } from 'lucide-react';
import { Button } from '../ui/Button';

interface RevisionsTabProps {
  revisions: RevisionRow[];
  onChangeRevisions: (revs: RevisionRow[]) => void;
}

export const RevisionsTab: React.FC<RevisionsTabProps> = ({
  revisions,
  onChangeRevisions,
}) => {
  const updateRevision = (idx: number, key: keyof RevisionRow, val: any) => {
    const updated = [...revisions];
    updated[idx] = { ...updated[idx], [key]: val };
    onChangeRevisions(updated);
  };

  const handleAdd = () => {
    onChangeRevisions([
      ...revisions,
      { rev: '', description: '', date: '', approved: '', confidence: 1.0, page: 1 },
    ]);
  };

  const handleDelete = (idx: number) => {
    onChangeRevisions(revisions.filter((_, i) => i !== idx));
  };

  return (
    <div className="p-4 space-y-3.5 text-xs">
      <div className="flex items-center justify-between pb-2 border-b border-[#E4EAF2]">
        <div>
          <h4 className="font-semibold text-sm text-[#172B4D]">Revision History</h4>
          <p className="text-[#64748B] text-[11px]">Engineering drawing change records</p>
        </div>
        <Button variant="secondary" size="xs" icon={<Plus className="w-3 h-3 text-blue-600" />} onClick={handleAdd}>
          Add Revision
        </Button>
      </div>

      {revisions.length === 0 ? (
        <div className="text-center py-8 text-slate-400">
          No revision table detected on this drawing.
        </div>
      ) : (
        <div className="space-y-2.5">
          {revisions.map((rev, idx) => (
            <div
              key={idx}
              className="p-3 bg-white border border-[#E4EAF2] rounded-md space-y-2 hover:border-slate-300 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-xs bg-purple-50 text-purple-700 px-2 py-0.5 rounded border border-purple-200">
                    REV {rev.rev || '-'}
                  </span>
                  <span className="text-slate-400 font-mono text-[11px]">{rev.date || 'No date'}</span>
                </div>
                <div className="flex items-center gap-2">
                  <ConfidenceBadge confidence={rev.confidence} size="sm" />
                  <button
                    onClick={() => handleDelete(idx)}
                    className="p-1 text-slate-400 hover:text-rose-600 rounded"
                    title="Delete revision entry"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[10px] text-slate-500 font-medium mb-0.5">Rev Code</label>
                  <input
                    type="text"
                    value={rev.rev || ''}
                    onChange={(e) => updateRevision(idx, 'rev', e.target.value)}
                    placeholder="e.g. A, 01"
                    className="w-full px-2 py-1 text-xs border border-[#E4EAF2] rounded font-mono"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-slate-500 font-medium mb-0.5">Approved By</label>
                  <input
                    type="text"
                    value={rev.approved || ''}
                    onChange={(e) => updateRevision(idx, 'approved', e.target.value)}
                    placeholder="Approver..."
                    className="w-full px-2 py-1 text-xs border border-[#E4EAF2] rounded"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] text-slate-500 font-medium mb-0.5">Change Description</label>
                <textarea
                  value={rev.description || ''}
                  onChange={(e) => updateRevision(idx, 'description', e.target.value)}
                  placeholder="Details of revision changes..."
                  rows={2}
                  className="w-full px-2 py-1 text-xs border border-[#E4EAF2] rounded"
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

