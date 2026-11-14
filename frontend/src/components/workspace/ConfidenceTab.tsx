import React from 'react';
import type { DrawingResult } from '../../types/api';
import { AlertTriangle, CheckCircle2, ShieldCheck, Activity } from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';

interface ConfidenceTabProps {
  result: DrawingResult;
}

export const ConfidenceTab: React.FC<ConfidenceTabProps> = ({ result }) => {
  const summary = result.summary || {};
  const meanConf = summary.mean_confidence ?? 0;
  const textConf = summary.text_confidence ?? 0;
  const structConf = summary.structural_confidence ?? 0;
  const reviewRequired = summary.review_required ?? false;
  const reviewReasons = summary.review_reasons;

  const chartData = [
    { name: 'Overall Confidence', score: Math.round(meanConf * 100), fill: '#2563EB' },
    { name: 'Text OCR Quality', score: Math.round(textConf * 100), fill: '#16A34A' },
    { name: 'Table Structure', score: Math.round(structConf * 100), fill: '#8B5CF6' },
  ];

  return (
    <div className="p-4 space-y-4 text-xs">
      <div className="pb-2 border-b border-[#E4EAF2]">
        <h4 className="font-semibold text-sm text-[#172B4D]">Quality & Verification Metrics</h4>
        <p className="text-[#64748B] text-[11px]">
          Confidence score analysis across OCR character recognition and table structural layout
        </p>
      </div>

      {/* Review Alert Banner */}
      {reviewRequired ? (
        <div className="p-3 bg-amber-50 border border-amber-200 rounded-md flex items-start gap-2.5 text-amber-800">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" />
          <div>
            <span className="font-semibold text-xs">Human Review Recommended</span>
            <p className="text-[11px] mt-0.5">{reviewReasons || 'One or more fields or rows fall below quality threshold.'}</p>
          </div>
        </div>
      ) : (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-md flex items-start gap-2.5 text-emerald-800">
          <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-emerald-600" />
          <div>
            <span className="font-semibold text-xs">High Extraction Confidence</span>
            <p className="text-[11px] mt-0.5">All structural tables and title block attributes pass quality thresholds.</p>
          </div>
        </div>
      )}

      {/* Metric Cards Grid */}
      <div className="grid grid-cols-3 gap-2.5">
        <div className="p-3 bg-white border border-[#E4EAF2] rounded-md text-center">
          <span className="text-[10px] text-slate-500 font-medium uppercase">Overall</span>
          <p className="text-xl font-bold font-mono text-[#2563EB] mt-0.5">
            {Math.round(meanConf * 100)}%
          </p>
        </div>
        <div className="p-3 bg-white border border-[#E4EAF2] rounded-md text-center">
          <span className="text-[10px] text-slate-500 font-medium uppercase">Text OCR</span>
          <p className="text-xl font-bold font-mono text-emerald-600 mt-0.5">
            {Math.round(textConf * 100)}%
          </p>
        </div>
        <div className="p-3 bg-white border border-[#E4EAF2] rounded-md text-center">
          <span className="text-[10px] text-slate-500 font-medium uppercase">Table Grid</span>
          <p className="text-xl font-bold font-mono text-purple-600 mt-0.5">
            {Math.round(structConf * 100)}%
          </p>
        </div>
      </div>

      {/* Visual Chart */}
      <div className="p-3 bg-white border border-[#E4EAF2] rounded-md">
        <h5 className="font-semibold text-xs text-[#172B4D] mb-3">Confidence Breakdown</h5>
        <div className="h-44 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 30, left: 40, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#E4EAF2" />
              <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} />
              <YAxis dataKey="name" type="category" tick={{ fontSize: 11, fill: '#172B4D' }} width={110} />
              <Tooltip
                formatter={(val) => [`${val}%`, 'Confidence Score']}
                contentStyle={{ backgroundColor: '#FFF', borderColor: '#E4EAF2', borderRadius: '4px', fontSize: '11px' }}
              />
              <Bar dataKey="score" radius={[0, 4, 4, 0]}>
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Processing Metadata */}
      <div className="p-3 bg-slate-50 border border-slate-200 rounded-md space-y-1.5 text-[11px] text-[#64748B]">
        <div className="flex justify-between">
          <span>Processing duration:</span>
          <span className="font-mono text-[#172B4D]">{result.processing_seconds}s</span>
        </div>
        <div className="flex justify-between">
          <span>Detected drawing pages:</span>
          <span className="font-mono text-[#172B4D]">{result.pages.length}</span>
        </div>
        <div className="flex justify-between">
          <span>Total BOM line items:</span>
          <span className="font-mono text-[#172B4D]">{result.bom.length}</span>
        </div>
      </div>
    </div>
  );
};

