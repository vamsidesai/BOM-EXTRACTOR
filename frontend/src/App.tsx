import React, { useState, useEffect } from 'react';
import { Sidebar, type NavView } from './components/common/Sidebar';
import { DashboardView } from './views/DashboardView';
import { UploadView } from './views/UploadView';
import { WorkspaceView } from './views/WorkspaceView';
import { HistoryView } from './views/HistoryView';
import { api } from './services/api';

export function App() {
  const [activeNav, setActiveNav] = useState<NavView | 'workspace'>('dashboard');
  const [activeDrawingId, setActiveDrawingId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(false);
  const [reviewCount, setReviewCount] = useState<number>(0);

  const fetchStats = async () => {
    try {
      const stats = await api.getDashboardStats();
      setReviewCount(stats.review_required_drawings || 0);
    } catch (e) {
      // Ignore
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  // When user clicks on a drawing in Dashboard or History logs
  const handleOpenReview = (id: string) => {
    setActiveDrawingId(id);
    setActiveNav('workspace');
  };

  const handleSidebarNavigate = (view: NavView) => {
    setActiveNav(view);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#F8FAFC] text-[#172B4D]">
      {/* Persistent Left Sidebar: Dashboard, Upload, History */}
      <Sidebar
        activeView={activeNav}
        onNavigate={handleSidebarNavigate}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
        reviewCount={reviewCount}
      />

      {/* Main Screen Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {activeNav === 'dashboard' && (
          <div className="flex-1 overflow-y-auto">
            <DashboardView
              onSelectDrawing={handleOpenReview}
              onNavigateUpload={() => setActiveNav('upload')}
            />
          </div>
        )}

        {activeNav === 'upload' && (
          <div className="flex-1 overflow-y-auto">
            <UploadView
              onOpenWorkspace={handleOpenReview}
              onNavigateHistory={() => setActiveNav('history')}
            />
          </div>
        )}

        {activeNav === 'history' && (
          <div className="flex-1 overflow-y-auto">
            <HistoryView
              onSelectDrawing={handleOpenReview}
              onRefreshStats={fetchStats}
            />
          </div>
        )}

        {activeNav === 'workspace' && activeDrawingId && (
          <div className="flex-1 h-full overflow-hidden">
            <WorkspaceView
              drawingId={activeDrawingId}
              onBack={() => setActiveNav('history')}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
