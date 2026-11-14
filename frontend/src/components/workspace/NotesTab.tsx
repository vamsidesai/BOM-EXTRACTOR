import React from 'react';
import { ConfidenceBadge } from '../common/ConfidenceBadge';
import { FileText, Plus, Trash2 } from 'lucide-react';
import { Button } from '../ui/Button';

interface NoteItem {
  id?: number;
  number?: string;
  text: string;
  confidence: number;
  bbox?: number[] | null;
  page: number;
}

interface NotesTabProps {
  notes: NoteItem[];
  onChangeNotes: (notes: NoteItem[]) => void;
}

export const NotesTab: React.FC<NotesTabProps> = ({ notes, onChangeNotes }) => {
  const updateNote = (idx: number, text: string) => {
    const updated = [...notes];
    updated[idx] = { ...updated[idx], text };
    onChangeNotes(updated);
  };

  const handleAdd = () => {
    onChangeNotes([
      ...notes,
      {
        number: String(notes.length + 1),
        text: '',
        confidence: 1.0,
        page: 1,
      },
    ]);
  };

  const handleDelete = (idx: number) => {
    onChangeNotes(notes.filter((_, i) => i !== idx));
  };

  return (
    <div className="p-4 space-y-3.5 text-xs">
      <div className="flex items-center justify-between pb-2 border-b border-[#E4EAF2]">
        <div>
          <h4 className="font-semibold text-sm text-[#172B4D]">Technical Drawing Notes</h4>
          <p className="text-[#64748B] text-[11px]">Numbered general and manufacturing notes</p>
        </div>
        <Button variant="secondary" size="xs" icon={<Plus className="w-3 h-3 text-blue-600" />} onClick={handleAdd}>
          Add Note
        </Button>
      </div>

      {notes.length === 0 ? (
        <div className="text-center py-8 text-slate-400">
          No notes detected on this drawing.
        </div>
      ) : (
        <div className="space-y-2.5">
          {notes.map((note, idx) => (
            <div
              key={idx}
              className="p-3 bg-white border border-[#E4EAF2] rounded-md space-y-1.5 hover:border-slate-300 transition-colors"
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-xs bg-amber-50 text-amber-700 px-2 py-0.5 rounded border border-amber-200">
                  NOTE {note.number || idx + 1}
                </span>
                <div className="flex items-center gap-2">
                  <ConfidenceBadge confidence={note.confidence} size="sm" />
                  <button
                    onClick={() => handleDelete(idx)}
                    className="p-1 text-slate-400 hover:text-rose-600 rounded"
                    title="Delete note"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              <textarea
                value={note.text}
                onChange={(e) => updateNote(idx, e.target.value)}
                placeholder="Enter note text..."
                rows={2}
                className="w-full px-2.5 py-1.5 text-xs text-[#172B4D] border border-[#E4EAF2] rounded focus:outline-none focus:ring-1 focus:ring-blue-500 font-sans"
              />

              <div className="text-[10px] text-slate-400">
                Sheet {note.page}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

