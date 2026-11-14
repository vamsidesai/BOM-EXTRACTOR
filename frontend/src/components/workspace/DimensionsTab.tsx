import React from 'react';
import type { Dimension } from '../../types/api';
import { ConfidenceBadge } from '../common/ConfidenceBadge';
import { Ruler } from 'lucide-react';

interface DimensionsTabProps {
  dimensions: Dimension[];
}

export const DimensionsTab: React.FC<DimensionsTabProps> = ({ dimensions }) => {
  return (
    <div className="p-4 space-y-3.5 text-xs">
      <div className="flex items-center justify-between pb-2 border-b border-[#E4EAF2]">
        <div>
          <h4 className="font-semibold text-sm text-[#172B4D]">Engineering Dimensions</h4>
          <p className="text-[#64748B] text-[11px]">
            Linear, diameter, radius, and angular callouts
          </p>
        </div>
        <span className="text-[11px] text-[#64748B] font-mono">{dimensions.length} dims</span>
      </div>

      {dimensions.length === 0 ? (
        <div className="text-center py-8 text-slate-400">
          No CAD dimensions extracted for this drawing.
        </div>
      ) : (
        <div className="overflow-x-auto border border-[#E4EAF2] rounded-md bg-white">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#F8FAFC] border-b border-[#E4EAF2] text-[#64748B] font-semibold">
                <th className="py-2 px-3">Callout Text</th>
                <th className="py-2 px-3">Type</th>
                <th className="py-2 px-3">Nominal</th>
                <th className="py-2 px-3">Tolerance</th>
                <th className="py-2 px-3">Confidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E4EAF2]">
              {dimensions.map((dim, idx) => (
                <tr key={idx} className="hover:bg-slate-50 font-mono">
                  <td className="py-2 px-3 font-medium text-[#172B4D]">{dim.text}</td>
                  <td className="py-2 px-3">
                    <span className="text-[10px] uppercase px-1.5 py-0.2 rounded bg-slate-100 text-slate-600">
                      {dim.dim_type}
                    </span>
                  </td>
                  <td className="py-2 px-3">{dim.nominal ?? '-'}</td>
                  <td className="py-2 px-3 text-slate-500">{dim.tolerance ?? '-'}</td>
                  <td className="py-2 px-3">
                    <ConfidenceBadge confidence={dim.confidence} size="sm" showIcon={false} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

