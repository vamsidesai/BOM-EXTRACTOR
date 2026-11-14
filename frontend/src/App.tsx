import React, { useState, useEffect } from 'react';
import { Navbar } from './components/common/Navbar';
import { DashboardView } from './views/DashboardView';
import { UploadView } from './views/UploadView';
import { WorkspaceView } from './views/WorkspaceView';
import { api } from './services/api';

export function App() {
  const [activeView, setActiveView] = useState<'dashboard' | 'upload' | 'workspace'>('dashboard');
  const [activeDrawingId, setActiveDrawingId] = useState<string | null>(null);
  const [activeDrawingName, setActiveDrawingName] = useState<string | null>(null);

  // If no drawing is selected when switching to workspace, pick the first drawing
  const handleNavigate = async (view: 'dashboard' | 'upload' | 'workspace') => {
    if (view === 'workspace' && !activeDrawingId) {
      try {
        const drawings = await api.listDrawings();
        if (drawings.length > 0) {
          setActiveDrawingId(drawings[0].id);
          setActiveDrawingName(drawings[0].drawing_number || drawings[0].filename);
        } else {
          alert('No drawings available to review. Please upload a drawing first.');
          setActiveView('upload');
          return;
        }
      } catch (e) {
        // Fall back
      }
    }
    setActiveView(view);
  };

  const handleSelectDrawing = (id: string) => {
    setActiveDrawingId(id);
    setActiveView('workspace');
  };

  // Sync active drawing name when activeDrawingId changes
  useEffect(() => {
    if (activeDrawingId) {
      api.getDrawingDetail(activeDrawingId).then((res) => {
        if (res?.metadata) {
          setActiveDrawingName(res.metadata.drawing_number || res.metadata.filename);
        }
      }).catch(() => {});
    }
  }, [activeDrawingId]);

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col text-[#172B4D]">
      <Navbar
        activeView={activeView}
        onNavigate={handleNavigate}
        activeDrawingName={activeDrawingName}
      />

      <main className="flex-1">
        {activeView === 'dashboard' && (
          <DashboardView
            onSelectDrawing={handleSelectDrawing}
            onNavigateUpload={() => setActiveView('upload')}
          />
        )}

        {activeView === 'upload' && (
          <UploadView
            onOpenWorkspace={(id) => {
              setActiveDrawingId(id);
              setActiveView('workspace');
            }}
          />
        )}

        {activeView === 'workspace' && activeDrawingId && (
          <WorkspaceView
            drawingId={activeDrawingId}
            onBack={() => setActiveView('dashboard')}
          />
        )}
      </main>
    </div>
  );
}

export default App;
