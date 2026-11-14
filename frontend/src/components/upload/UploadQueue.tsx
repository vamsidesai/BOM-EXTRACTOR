import React from 'react';
import type { DrawingSummaryItem } from '../../types/api';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Button } from '../ui/Button';
import { StatusPill } from '../common/StatusPill';
import { ConfidenceBadge } from '../common/ConfidenceBadge';
import { FileText, ArrowRight, CheckCircle2, AlertCircle, RefreshCw } from 'lucide-react';

interface UploadQueueProps {
  queue: DrawingSummaryItem[];
  onOpenWorkspace: (id: string) => void;
  onRefresh: () => void;
}

export const UploadQueue: React.FC<UploadQueueProps> = ({
  queue,
  onOpenWorkspace,
  onRefresh,
}) => {
  if (queue.length === 0) return null;

  return (
    <Card className="mt-6">
      <CardHeader>
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-2">
            <CardTitle>Batch Upload & Extraction Progress</CardTitle>
            <span className="text-xs bg-blue-50 text-blue-700 font-semibold px-2 py-0.5 rounded-full border border-blue-200">
              {queue.length} {queue.length === 1 ? 'file' : 'files'}
            </span>
          </div>
          <Button variant="ghost" size="xs" icon={<RefreshCw className="w-3 h-3" />} onClick={onRefresh}>
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="divide-y divide-[#E4EAF2]">
          {queue.map((item) => {
            const isProcessing = item.status === 'processing';
            const isCompleted = item.status === 'completed';
            const isFailed = item.status === 'failed';

            return (
              <div
                key={item.id}
                className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <div className="w-9 h-9 rounded bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-600 shrink-0">
                    <FileText className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-[#172B4D]">{item.filename}</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-100 border text-slate-600">
                        {item.file_format}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-3 text-xs text-[#64748B] mt-1">
                      <span>{(item.file_size_bytes / (1024 * 1024)).toFixed(2)} MB</span>
                      {item.bom_items_count > 0 && (
                        <span>· {item.bom_items_count} BOM items detected</span>
                      )}
                      {item.processing_seconds && (
                        <span>· Processed in {item.processing_seconds}s</span>
                      )}
                    </div>

                    {isProcessing && (
                      <div className="w-64 mt-2">
                        <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
                          <div className="bg-[#2563EB] h-1.5 rounded-full animate-pulse w-3/4" />
                        </div>
                        <span className="text-[10px] text-blue-600 font-medium mt-0.5 inline-block">
                          Running layout detection & OCR pipeline...
                        </span>
                      </div>
                    )}

                    {isFailed && item.error_message && (
                      <p className="text-xs text-rose-600 mt-1 flex items-center gap-1">
                        <AlertCircle className="w-3 h-3 shrink-0" />
                        {item.error_message}
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0 self-end sm:self-center">
                  {isCompleted && (
                    <ConfidenceBadge confidence={item.mean_confidence} />
                  )}

                  <StatusPill
                    status={item.status}
                    verified={item.verified}
                    reviewRequired={item.review_required}
                  />

                  {isCompleted && (
                    <Button
                      variant="primary"
                      size="sm"
                      icon={<ArrowRight className="w-3.5 h-3.5" />}
                      onClick={() => onOpenWorkspace(item.id)}
                    >
                      Open Review
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
};

