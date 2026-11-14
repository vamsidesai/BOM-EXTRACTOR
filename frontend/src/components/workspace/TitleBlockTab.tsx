import React from 'react';
import type { FieldValue } from '../../types/api';
import { ConfidenceBadge } from '../common/ConfidenceBadge';
import { Crosshair, Edit3 } from 'lucide-react';

interface TitleBlockTabProps {
  titleBlock: Record<string, FieldValue>;
  onChangeField: (key: string, value: string) => void;
  onLocateField: (key: string) => void;
  focusedFieldKey?: string | null;
}

const PRIMARY_TITLE_FIELDS = [
  { key: 'drawing_number', label: 'Drawing Number' },
  { key: 'drawing_title', label: 'Drawing Title / Description' },
  { key: 'revision', label: 'Revision Level' },
  { key: 'drawn_by', label: 'Drawn By (Author)' },
  { key: 'date', label: 'Drawn Date' },
  { key: 'scale', label: 'Scale' },
  { key: 'projection', label: 'Projection Method' },
  { key: 'sheet', label: 'Sheet Number' },
  { key: 'checked_by', label: 'Checked By' },
  { key: 'approved_by', label: 'Approved By' },
  { key: 'material', label: 'Title Block Material' },
  { key: 'weight', label: 'Declared Mass / Weight' },
];

export const TitleBlockTab: React.FC<TitleBlockTabProps> = ({
  titleBlock,
  onChangeField,
  onLocateField,
  focusedFieldKey,
}) => {
  // Merge primary fields with any extra fields detected
  const existingKeys = new Set(Object.keys(titleBlock));
  const extraKeys = Array.from(existingKeys).filter(
    (k) => !PRIMARY_TITLE_FIELDS.some((pf) => pf.key === k)
  );

  const allFields = [
    ...PRIMARY_TITLE_FIELDS,
    ...extraKeys.map((k) => ({
      key: k,
      label: k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
    })),
  ];

  return (
    <div className="p-4 space-y-3.5 text-xs">
      <div className="flex items-center justify-between pb-2 border-b border-[#E4EAF2]">
        <div>
          <h4 className="font-semibold text-sm text-[#172B4D]">Title Block Metadata</h4>
          <p className="text-[#64748B] text-[11px]">
            Extracted drawing header attributes with confidence scores
          </p>
        </div>
        <span className="text-[11px] text-[#64748B] font-mono">
          {Object.keys(titleBlock).length} fields detected
        </span>
      </div>

      <div className="space-y-3">
        {allFields.map(({ key, label }) => {
          const fieldObj = titleBlock[key] || { value: '', confidence: 1.0, raw: '' };
          const val = fieldObj.value ?? '';
          const hasBbox = fieldObj.bbox && fieldObj.bbox.length === 4;
          const isFocused = focusedFieldKey === key;

          return (
            <div
              key={key}
              id={`tb-field-${key}`}
              className={`p-3 rounded-md border transition-all duration-150 ${
                isFocused
                  ? 'bg-blue-50/60 border-[#2563EB] shadow-xs'
                  : 'bg-white border-[#E4EAF2] hover:border-slate-300'
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <label className="font-semibold text-[#172B4D] flex items-center gap-1.5">
                  <span>{label}</span>
                </label>
                <div className="flex items-center gap-2">
                  <ConfidenceBadge confidence={fieldObj.confidence} size="sm" />
                  {hasBbox && (
                    <button
                      type="button"
                      onClick={() => onLocateField(key)}
                      title="Locate on drawing"
                      className="p-1 text-slate-400 hover:text-[#2563EB] hover:bg-blue-50 rounded transition-colors"
                    >
                      <Crosshair className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>

              <div className="relative">
                <input
                  type="text"
                  value={val}
                  onChange={(e) => onChangeField(key, e.target.value)}
                  placeholder={`Enter ${label.toLowerCase()}...`}
                  className="w-full px-2.5 py-1.5 text-xs text-[#172B4D] font-mono bg-slate-50/50 border border-[#E4EAF2] rounded focus:bg-white focus:outline-none focus:ring-1 focus:ring-[#2563EB]"
                />
              </div>

              {fieldObj.raw && fieldObj.raw !== val && (
                <div className="mt-1 text-[10px] text-[#64748B] font-mono">
                  <span className="text-slate-400">OCR Raw:</span> {fieldObj.raw}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

