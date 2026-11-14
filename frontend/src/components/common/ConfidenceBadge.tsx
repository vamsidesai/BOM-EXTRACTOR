import React from 'react';
import { clsx } from 'clsx';
import { ShieldCheck, AlertCircle, AlertTriangle } from 'lucide-react';

interface ConfidenceBadgeProps {
  confidence: number | null | undefined;
  size?: 'sm' | 'md';
  showIcon?: boolean;
}

export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({
  confidence,
  size = 'md',
  showIcon = true,
}) => {
  if (confidence === null || confidence === undefined) {
    return <span className="text-xs text-slate-400 font-mono">-</span>;
  }

  const val = Math.round(confidence * 100);

  let variantStyles = 'bg-emerald-50 text-emerald-700 border-emerald-200';
  let IconComponent = ShieldCheck;
  let title = `High confidence (${val}%)`;

  if (val < 65) {
    variantStyles = 'bg-rose-50 text-rose-700 border-rose-200';
    IconComponent = AlertCircle;
    title = `Low confidence (${val}%) - manual verification recommended`;
  } else if (val < 85) {
    variantStyles = 'bg-amber-50 text-amber-700 border-amber-200';
    IconComponent = AlertTriangle;
    title = `Moderate confidence (${val}%)`;
  }

  const sizeStyles = size === 'sm' ? 'text-[11px] px-1.5 py-0.5' : 'text-xs px-2 py-0.5';

  return (
    <span
      title={title}
      className={clsx(
        'inline-flex items-center gap-1 font-mono font-medium rounded border cursor-help select-none',
        variantStyles,
        sizeStyles
      )}
    >
      {showIcon && <IconComponent className={size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5'} />}
      <span>{val}%</span>
    </span>
  );
};

