import React from 'react';
import type { SpecCallout } from '../../types/api';
import { ConfidenceBadge } from '../common/ConfidenceBadge';
import { Layers, ShieldCheck, Tag } from 'lucide-react';

interface SpecsTabProps {
  specs: SpecCallout[];
}

export const SpecsTab: React.FC<SpecsTabProps> = ({ specs }) => {
  // Group by category
  const categories: Record<string, SpecCallout[]> = {};
  specs.forEach((s) => {
    const cat = s.category || 'general';
    if (!categories[cat]) categories[cat] = [];
    categories[cat].push(s);
  });

  return (
    <div className="p-4 space-y-4 text-xs">
      <div className="flex items-center justify-between pb-2 border-b border-[#E4EAF2]">
        <div>
          <h4 className="font-semibold text-sm text-[#172B4D]">Materials & Specifications</h4>
          <p className="text-[#64748B] text-[11px]">
            Callouts detected from drawing notes, title block, and annotations
          </p>
        </div>
        <span className="text-[11px] text-[#64748B] font-mono">{specs.length} specs</span>
      </div>

      {specs.length === 0 ? (
        <div className="text-center py-8 text-slate-400">
          No explicit material or surface finish callouts detected.
        </div>
      ) : (
        Object.entries(categories).map(([cat, items]) => (
          <div key={cat} className="space-y-2">
            <h5 className="font-semibold text-xs text-[#2563EB] uppercase tracking-wider flex items-center gap-1.5">
              <Tag className="w-3.5 h-3.5" />
              <span>{cat.replace(/_/g, ' ')}</span>
            </h5>

            <div className="space-y-2">
              {items.map((item, idx) => (
                <div
                  key={idx}
                  className="p-3 bg-white border border-[#E4EAF2] rounded-md hover:border-slate-300 transition-colors"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-[#172B4D] font-mono text-sm">
                      {item.value}
                    </span>
                    <ConfidenceBadge confidence={item.confidence} size="sm" />
                  </div>

                  <p className="text-[11px] text-slate-600 bg-slate-50 p-2 rounded border border-slate-100 font-mono">
                    "{item.context}"
                  </p>

                  <div className="flex items-center gap-3 text-[10px] text-slate-400 mt-2">
                    <span>Source: {item.source}</span>
                    <span>·</span>
                    <span>Sheet {item.page}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
};

