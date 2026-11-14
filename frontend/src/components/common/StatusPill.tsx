import React from 'react';
import { clsx } from 'clsx';
import { CheckCircle2, AlertTriangle, XCircle, Clock, FileCheck } from 'lucide-react';

interface StatusPillProps {
  status: string;
  verified?: boolean;
  reviewRequired?: boolean;
}

export const StatusPill: React.FC<StatusPillProps> = ({
  status,
  verified = false,
  reviewRequired = false,
}) => {
  if (verified) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
        <CheckCircle2 className="w-3.5 h-3.5" />
        Verified
      </span>
    );
  }

  if (status === 'processing') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
        <span className="w-2 h-2 rounded-full bg-blue-600 animate-ping" />
        Processing
      </span>
    );
  }

  if (status === 'failed') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200">
        <XCircle className="w-3.5 h-3.5" />
        Failed
      </span>
    );
  }

  if (reviewRequired) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
        <AlertTriangle className="w-3.5 h-3.5" />
        Needs Review
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
      <FileCheck className="w-3.5 h-3.5" />
      Extracted
    </span>
  );
};

