import React, { useState, useEffect } from 'react';
import type { DashboardStats } from '../types/api';
import { api } from '../services/api';
import { MetricCard } from '../components/dashboard/MetricCard';
import { ChartsSection } from '../components/dashboard/ChartsSection';
import { RecentDrawingsTable } from '../components/dashboard/RecentDrawingsTable';
import { Button } from '../components/ui/Button';
import {
  FileText,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Table as TableIcon,
  UploadCloud,
  RefreshCw,
} from 'lucide-react';

interface DashboardViewProps {
  onSelectDrawing: (id: string) => void;
  onNavigateUpload: () => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  onSelectDrawing,
  onNavigateUpload,
}) => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getDashboardStats();
      setStats(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch dashboard metrics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Top Banner / Welcome Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-[#E4EAF2]">
        <div>
          <h1 className="text-xl font-bold text-[#172B4D] tracking-tight">
            Engineering Document Extraction Dashboard
          </h1>
          <p className="text-xs text-[#64748B] mt-0.5">
            Automated Title Block, Bill of Materials (BOM), and Material specification extraction
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
            onClick={fetchStats}
          >
            Refresh
          </Button>

          <Button
            variant="primary"
            size="sm"
            icon={<UploadCloud className="w-4 h-4" />}
            onClick={onNavigateUpload}
          >
            Upload Drawing
          </Button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-md text-xs text-rose-700">
          Failed to load dashboard metrics: {error}
        </div>
      )}

      {/* KPI Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <MetricCard
          title="Total Drawings"
          value={stats?.total_drawings ?? 0}
          subtitle="Processed sheets"
          icon={<FileText className="w-5 h-5" />}
          iconBg="bg-blue-50"
          iconColor="text-[#2563EB]"
        />

        <MetricCard
          title="Verified"
          value={stats?.verified_drawings ?? 0}
          subtitle="Human approved"
          icon={<CheckCircle2 className="w-5 h-5" />}
          iconBg="bg-emerald-50"
          iconColor="text-emerald-600"
        />

        <MetricCard
          title="Needs Review"
          value={stats?.review_required_drawings ?? 0}
          subtitle="Quality flag triggers"
          icon={<AlertTriangle className="w-5 h-5" />}
          iconBg="bg-amber-50"
          iconColor="text-amber-600"
        />

        <MetricCard
          title="Failed Extractions"
          value={stats?.failed_drawings ?? 0}
          subtitle="OCR / syntax errors"
          icon={<XCircle className="w-5 h-5" />}
          iconBg="bg-rose-50"
          iconColor="text-rose-600"
        />

        <MetricCard
          title="Total BOM Items"
          value={stats?.total_bom_items ?? 0}
          subtitle="Line items extracted"
          icon={<TableIcon className="w-5 h-5" />}
          iconBg="bg-indigo-50"
          iconColor="text-indigo-600"
        />
      </div>

      {/* Charts Section */}
      <ChartsSection
        confidenceDist={stats?.confidence_distribution || {}}
        fileTypeDist={stats?.file_type_distribution || {}}
      />

      {/* Recent Drawings Table */}
      <RecentDrawingsTable
        drawings={stats?.recent_drawings || []}
        onSelectDrawing={onSelectDrawing}
        onRefresh={fetchStats}
      />
    </div>
  );
};

