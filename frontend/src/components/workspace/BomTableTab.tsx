import React, { useState, useMemo } from 'react';
import type { BomRow } from '../../types/api';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table';
import { ConfidenceBadge } from '../common/ConfidenceBadge';
import { Button } from '../ui/Button';
import {
  Plus,
  Trash2,
  Search,
  Crosshair,
  AlertTriangle,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
} from 'lucide-react';

interface BomTableTabProps {
  bom: BomRow[];
  onChangeBom: (updatedBom: BomRow[]) => void;
  onLocateRow: (rowIndex: number) => void;
  selectedRowIndex?: number | null;
}

const columnHelper = createColumnHelper<BomRow>();

export const BomTableTab: React.FC<BomTableTabProps> = ({
  bom,
  onChangeBom,
  onLocateRow,
  selectedRowIndex,
}) => {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState('');

  const updateCell = (rowIndex: number, columnId: keyof BomRow, value: any) => {
    const updated = [...bom];
    updated[rowIndex] = {
      ...updated[rowIndex],
      [columnId]: value,
    };
    onChangeBom(updated);
  };

  const handleAddRow = () => {
    const newRow: BomRow = {
      item: String(bom.length + 1),
      part_number: '',
      description: '',
      quantity: '1',
      material: '',
      mass: '',
      remarks: '',
      flags: [],
      confidence: 1.0,
      structural_confidence: 1.0,
      page: 1,
    };
    onChangeBom([...bom, newRow]);
  };

  const handleDeleteRow = (rowIndex: number) => {
    const updated = bom.filter((_, idx) => idx !== rowIndex);
    onChangeBom(updated);
  };

  const columns = useMemo(
    () => [
      columnHelper.accessor('item', {
        header: 'Item',
        cell: (info) => {
          const idx = info.row.index;
          return (
            <input
              type="text"
              value={info.getValue() || ''}
              onChange={(e) => updateCell(idx, 'item', e.target.value)}
              className="w-12 px-1 py-0.5 font-mono text-xs bg-transparent border-b border-transparent focus:border-blue-500 focus:bg-white focus:outline-none"
            />
          );
        },
      }),

      columnHelper.accessor('part_number', {
        header: 'Part Number',
        cell: (info) => {
          const idx = info.row.index;
          return (
            <input
              type="text"
              value={info.getValue() || ''}
              onChange={(e) => updateCell(idx, 'part_number', e.target.value)}
              placeholder="P/N..."
              className="w-28 px-1 py-0.5 font-mono text-xs bg-transparent border-b border-transparent focus:border-blue-500 focus:bg-white focus:outline-none font-medium text-[#172B4D]"
            />
          );
        },
      }),

      columnHelper.accessor('description', {
        header: 'Description',
        cell: (info) => {
          const idx = info.row.index;
          return (
            <input
              type="text"
              value={info.getValue() || ''}
              onChange={(e) => updateCell(idx, 'description', e.target.value)}
              placeholder="Part name..."
              className="w-full min-w-[140px] px-1 py-0.5 text-xs bg-transparent border-b border-transparent focus:border-blue-500 focus:bg-white focus:outline-none"
            />
          );
        },
      }),

      columnHelper.accessor('quantity', {
        header: 'Qty',
        cell: (info) => {
          const idx = info.row.index;
          return (
            <input
              type="text"
              value={info.getValue() || ''}
              onChange={(e) => updateCell(idx, 'quantity', e.target.value)}
              className="w-14 px-1 py-0.5 font-mono text-xs bg-transparent border-b border-transparent focus:border-blue-500 focus:bg-white focus:outline-none text-center"
            />
          );
        },
      }),

      columnHelper.accessor('material', {
        header: 'Material Grade',
        cell: (info) => {
          const idx = info.row.index;
          return (
            <input
              type="text"
              value={info.getValue() || ''}
              onChange={(e) => updateCell(idx, 'material', e.target.value)}
              placeholder="Grade..."
              className="w-28 px-1 py-0.5 text-xs bg-transparent border-b border-transparent focus:border-blue-500 focus:bg-white focus:outline-none"
            />
          );
        },
      }),

      columnHelper.accessor('mass', {
        header: 'Mass / Wt',
        cell: (info) => {
          const idx = info.row.index;
          const row = info.row.original;
          const hasAmbiguousDecimal = row.flags && row.flags.includes('mass_decimal_ambiguous');
          return (
            <div className="flex items-center gap-1">
              <input
                type="text"
                value={info.getValue() || ''}
                onChange={(e) => updateCell(idx, 'mass', e.target.value)}
                placeholder="kg..."
                className="w-20 px-1 py-0.5 font-mono text-xs bg-transparent border-b border-transparent focus:border-blue-500 focus:bg-white focus:outline-none"
              />
              {hasAmbiguousDecimal && (
                <span title="Ambiguous decimal delimiter" className="text-amber-500">
                  <AlertTriangle className="w-3.5 h-3.5" />
                </span>
              )}
            </div>
          );
        },
      }),

      columnHelper.accessor('remarks', {
        header: 'Remarks',
        cell: (info) => {
          const idx = info.row.index;
          return (
            <input
              type="text"
              value={info.getValue() || ''}
              onChange={(e) => updateCell(idx, 'remarks', e.target.value)}
              placeholder="Notes..."
              className="w-24 px-1 py-0.5 text-xs bg-transparent border-b border-transparent focus:border-blue-500 focus:bg-white focus:outline-none text-slate-500"
            />
          );
        },
      }),

      columnHelper.accessor('confidence', {
        header: 'Conf',
        cell: (info) => <ConfidenceBadge confidence={info.getValue()} size="sm" showIcon={false} />,
      }),

      columnHelper.display({
        id: 'actions',
        header: '',
        cell: (info) => {
          const idx = info.row.index;
          return (
            <div className="flex items-center gap-1 justify-end">
              <button
                type="button"
                onClick={() => onLocateRow(idx)}
                title="Locate on drawing"
                className="p-1 text-slate-400 hover:text-blue-600 rounded"
              >
                <Crosshair className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => handleDeleteRow(idx)}
                title="Delete row"
                className="p-1 text-slate-400 hover:text-rose-600 rounded"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        },
      }),
    ],
    [bom]
  );

  const table = useReactTable({
    data: bom,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  return (
    <div className="p-4 space-y-3 text-xs flex flex-col h-full">
      {/* Table Control Header */}
      <div className="flex items-center justify-between gap-3 pb-2 border-b border-[#E4EAF2] shrink-0">
        <div>
          <h4 className="font-semibold text-sm text-[#172B4D]">Bill of Materials (BOM)</h4>
          <p className="text-[#64748B] text-[11px]">{bom.length} extracted components</p>
        </div>

        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={globalFilter ?? ''}
              onChange={(e) => setGlobalFilter(e.target.value)}
              placeholder="Search BOM rows..."
              className="pl-8 pr-2.5 py-1 text-xs bg-slate-50 border border-[#E4EAF2] rounded focus:outline-none focus:ring-1 focus:ring-blue-500 w-44"
            />
          </div>

          <Button
            variant="secondary"
            size="xs"
            icon={<Plus className="w-3 h-3 text-blue-600" />}
            onClick={handleAddRow}
          >
            Add Row
          </Button>
        </div>
      </div>

      {/* TanStack Table Container */}
      <div className="flex-1 overflow-x-auto border border-[#E4EAF2] rounded-md bg-white">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="bg-[#F8FAFC] border-b border-[#E4EAF2] text-[#64748B] font-semibold">
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler()}
                    className="py-2.5 px-3 select-none cursor-pointer hover:bg-slate-100"
                  >
                    <div className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {{
                        asc: <ArrowUp className="w-3 h-3 text-blue-600" />,
                        desc: <ArrowDown className="w-3 h-3 text-blue-600" />,
                      }[header.column.getIsSorted() as string] ?? (
                        header.column.getCanSort() && header.id !== 'actions' ? (
                          <ArrowUpDown className="w-3 h-3 text-slate-300 opacity-60" />
                        ) : null
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-[#E4EAF2]">
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="text-center py-8 text-slate-400">
                  No BOM rows extracted. Click "Add Row" to create one manually.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => {
                const isSelected = row.index === selectedRowIndex;
                const flags = row.original.flags || [];
                const hasFlags = flags.length > 0;

                return (
                  <tr
                    key={row.id}
                    onClick={() => onLocateRow(row.index)}
                    className={`transition-colors cursor-pointer ${
                      isSelected
                        ? 'bg-amber-50/70 border-l-4 border-l-amber-500'
                        : hasFlags
                        ? 'bg-amber-50/20 hover:bg-slate-50'
                        : 'hover:bg-slate-50'
                    }`}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="py-2 px-3">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
