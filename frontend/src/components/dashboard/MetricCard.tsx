import React from 'react';
import { Card } from '../ui/Card';

interface MetricCardProps {
  title: string;
  value: number | string;
  subtitle?: string;
  icon: React.ReactNode;
  iconBg?: string;
  iconColor?: string;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subtitle,
  icon,
  iconBg = 'bg-blue-50',
  iconColor = 'text-[#2563EB]',
}) => {
  return (
    <Card className="hover:border-slate-300 transition-colors">
      <div className="p-5 flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold text-[#64748B] uppercase tracking-wider">{title}</p>
          <p className="mt-1.5 text-2xl font-bold text-[#172B4D] tracking-tight">{value}</p>
          {subtitle && <p className="mt-1 text-xs text-[#64748B]">{subtitle}</p>}
        </div>
        <div className={`w-11 h-11 rounded-lg ${iconBg} ${iconColor} flex items-center justify-center shrink-0`}>
          {icon}
        </div>
      </div>
    </Card>
  );
};

