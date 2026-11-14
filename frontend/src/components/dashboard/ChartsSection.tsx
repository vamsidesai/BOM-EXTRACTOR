import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';

interface ChartsSectionProps {
  confidenceDist: Record<string, number>;
  fileTypeDist: Record<string, number>;
}

const COLORS = ['#2563EB', '#16A34A', '#8B5CF6', '#D97706', '#64748B'];

export const ChartsSection: React.FC<ChartsSectionProps> = ({
  confidenceDist,
  fileTypeDist,
}) => {
  const confData = [
    { name: 'High (≥85%)', count: confidenceDist['high (>85%)'] || 0, fill: '#16A34A' },
    { name: 'Medium (65-84%)', count: confidenceDist['medium (65-85%)'] || 0, fill: '#D97706' },
    { name: 'Low (<65%)', count: confidenceDist['low (<65%)'] || 0, fill: '#DC2626' },
  ];

  const fileData = Object.entries(fileTypeDist).map(([fmt, count]) => ({
    name: fmt,
    value: count,
  }));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 my-6">
      {/* Confidence Distribution */}
      <Card>
        <CardHeader>
          <CardTitle>Extraction OCR & Layout Confidence</CardTitle>
          <span className="text-xs text-[#64748B]">Quality assurance breakdown</span>
        </CardHeader>
        <CardContent>
          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={confData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E4EAF2" />
                <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#64748B' }} stroke="#E4EAF2" />
                <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: '#64748B' }} stroke="#E4EAF2" />
                <Tooltip
                  cursor={{ fill: 'rgba(241, 245, 249, 0.6)' }}
                  contentStyle={{
                    backgroundColor: '#FFFFFF',
                    borderColor: '#E4EAF2',
                    borderRadius: '6px',
                    fontSize: '12px',
                    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)',
                  }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {confData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* File Type Distribution */}
      <Card>
        <CardHeader>
          <CardTitle>Supported Engineering Formats</CardTitle>
          <span className="text-xs text-[#64748B]">CAD vs Vector/Raster documents</span>
        </CardHeader>
        <CardContent>
          <div className="h-56 w-full flex items-center justify-center">
            {fileData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={fileData}
                    cx="50%"
                    cy="50%"
                    innerRadius={45}
                    outerRadius={75}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {fileData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#FFFFFF',
                      borderColor: '#E4EAF2',
                      borderRadius: '6px',
                      fontSize: '12px',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-xs text-slate-400">No documents processed yet</p>
            )}
          </div>
          <div className="flex flex-wrap items-center justify-center gap-4 mt-2">
            {fileData.map((item, idx) => (
              <div key={item.name} className="flex items-center gap-1.5 text-xs text-[#64748B]">
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: COLORS[idx % COLORS.length] }}
                />
                <span className="font-medium text-[#172B4D]">{item.name}</span>
                <span>({item.value})</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

