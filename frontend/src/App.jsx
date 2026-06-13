import { useState, useCallback, useRef, useEffect, useMemo } from 'react';

// ── localStorage cache helpers ─────────────────────────────────────────
const CACHE_PREFIX = 'rpa:';
const CHAT_PREFIX  = 'rpa:chat:';
function cacheSet(paperId, graphData, summaryData) {
  try { localStorage.setItem(CACHE_PREFIX + paperId, JSON.stringify({ graphData, summaryData })); } catch (_) {}
}
function cacheDel(paperId) {
  localStorage.removeItem(CACHE_PREFIX + paperId);
  localStorage.removeItem(CHAT_PREFIX  + paperId);
}
function chatSave(paperId, messages) {
  try { localStorage.setItem(CHAT_PREFIX + paperId, JSON.stringify(messages)); } catch (_) {}
}
function chatLoad(paperId) {
  try { return JSON.parse(localStorage.getItem(CHAT_PREFIX + paperId)) ?? []; } catch { return []; }
}
function cacheLoadAll() {
  const out = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key?.startsWith(CACHE_PREFIX) || key.startsWith(CHAT_PREFIX)) continue;
    try {
      const { graphData, summaryData } = JSON.parse(localStorage.getItem(key));
      if (graphData && summaryData)
        out.push({ paper_id: key.slice(CACHE_PREFIX.length), status: 'done', fromCache: true, graphData, summaryData });
    } catch (_) {}
  }
  return out;
}
function cacheLoadOne(paperId) {
  try {
    const d = localStorage.getItem(CACHE_PREFIX + paperId);
    if (!d) return null;
    const { graphData, summaryData } = JSON.parse(d);
    return (graphData && summaryData) ? { graphData, summaryData } : null;
  } catch { return null; }
}
import Sidebar from './components/Sidebar';
import TabBar from './components/TabBar';
import PdfViewer from './components/PdfViewer';
import KnowledgeGraph from './components/KnowledgeGraph';
import Summary from './components/Summary';
import Chat from './components/Chat';
import MarkerDecisionModal from './components/MarkerDecisionModal';
import LoginScreen from './components/LoginScreen';
import { uploadPaper, getStatus, getGraph, getSummary, cancelPaper, retryPaper, getInfo, getMyPapers, openPaper, deletePaper } from './api';

// provider/model/prefix are all empty until Sidebar's mount effect calls GET /providers
const DEFAULT_SETTINGS = {
  provider:            '',
  prefix:              '',
  model:               '',
  apiKey:              '',
  datalabKey:          '',
  readerExpertise:     0.0,
  scientificKnowledge: 0.0,
  languageComplexity:  0.0,
  domain:              'auto',
};

export default function App() {
  const [authToken, setAuthToken] = useState(() => localStorage.getItem('rpa:token'));
  const [authUser, setAuthUser]   = useState(() => {
    try { return JSON.parse(localStorage.getItem('rpa:user')); } catch { return null; }
  });

  const handleLogin = (token, user) => {
    localStorage.setItem('rpa:token', token);
    localStorage.setItem('rpa:user', JSON.stringify(user));
    setAuthToken(token);
    setAuthUser(user);
  };

  const handleLogout = () => {
    localStorage.removeItem('rpa:token');
    localStorage.removeItem('rpa:user');
    setAuthToken(null);
    setAuthUser(null);
  };

  if (!authToken || !authUser) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  return <AuthenticatedApp authUser={authUser} onLogout={handleLogout} />;
}

function AuthenticatedApp({ authUser, onLogout }) {
  // ── App state ─────────────────────────────────────────────────────────
  const [tabs, setTabs] = useState([]);
  const [activeIdx, setActiveIdx] = useState(0);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [chatMessages, setChatMessages] = useState([]);
  const [panels, setPanels] = useState({ sidebar: true, pdf: true, summary: true });
  const toggle = name => setPanels(p => ({ ...p, [name]: !p[name] }));
  const [chatOpen, setChatOpen] = useState(false);
  const [chatExpanded, setChatExpanded] = useState(false);
  const [library, setLibrary] = useState([]);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [adminMode, setAdminMode] = useState(false);

  const pollTimers  = useRef({});

  // ── Panel resize state ────────────────────────────────────────────────
  const [sidebarWidth, setSidebarWidth] = useState(284);
  const [pdfPct,       setPdfPct]       = useState(50);
  const workspaceRef = useRef(null);

  // Restore cached papers, fetch app info, and load user's paper library on mount
  useEffect(() => {
    const localCached = cacheLoadAll();
    if (localCached.length > 0) setTabs(localCached);

    // Build library from both the server manifest AND localStorage cache,
    // so papers appear even before the manifest was introduced.
    const buildLibrary = (serverEntries) => {
      const serverIds = new Set(serverEntries.map(e => e.paper_id));
      const localOnly = localCached
        .filter(t => !serverIds.has(t.paper_id))
        .map(t => ({
          paper_id: t.paper_id,
          title: t.summaryData?.title || t.paper_id,
          detected_domain: t.detectedDomain || null,
          uploaded_at: null,
        }));
      return [...serverEntries, ...localOnly];
    };

    getInfo().then(d => setAdminMode(d.admin_mode)).catch(() => {});
    getMyPapers()
      .then(data => setLibrary(buildLibrary(data)))
      .catch(() => setLibrary(buildLibrary([])));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // prefix and model are set by Sidebar once GET /providers responds.
  // Guard against double-prefix for providers (Gemini, Mistral) whose model
  // names already embed the prefix (e.g. "gemini/gemini-1.5-flash").
  const resolvedModel = (() => {
    const prefix = settings.prefix;
    const model  = (settings.model || '').trim();
    if (!prefix || !model) return '';         // not ready yet — providers still loading
    return model.startsWith(`${prefix}/`) ? model : `${prefix}/${model}`;
  })();

  const readerParams = {
    reader_expertise: settings.readerExpertise,
    scientific_knowledge: settings.scientificKnowledge,
    language_complexity: settings.languageComplexity,
  };

  const startPolling = useCallback((paperId) => {
    if (pollTimers.current[paperId]) {
      clearInterval(pollTimers.current[paperId]);
      delete pollTimers.current[paperId];
    }
    const timer = setInterval(async () => {
      try {
        const status = await getStatus(paperId);
        setTabs(prev => prev.map(t =>
          t.paper_id !== paperId ? t
            : { ...t, status: status.status, progress: status.progress_pct, progressText: status.progress_text, error: status.error, detectedDomain: status.detected_domain ?? t.detectedDomain }
        ));

        if (status.status === 'done') {
          clearInterval(pollTimers.current[paperId]);
          delete pollTimers.current[paperId];
          try {
            const [graphData, summaryData] = await Promise.all([
              getGraph(paperId), getSummary(paperId),
            ]);
            cacheSet(paperId, graphData, summaryData);
            setTabs(prev => prev.map(t =>
              t.paper_id !== paperId ? t : { ...t, graphData, summaryData, fromCache: false }
            ));
          } catch (fetchErr) {
            console.error('Failed to fetch graph/summary:', fetchErr);
            setTabs(prev => prev.map(t =>
              t.paper_id !== paperId ? t : { ...t, error: 'Failed to load results — try refreshing', status: 'error' }
            ));
          }
          getMyPapers().then(setLibrary).catch(() => {});
        } else if (status.status === 'error' || status.status === 'cancelled') {
          clearInterval(pollTimers.current[paperId]);
          delete pollTimers.current[paperId];
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 2000);
    pollTimers.current[paperId] = timer;
  }, []);

  const handleUpload = useCallback(async (file) => {
    const paperId = file.name.replace(/\.pdf$/i, '');

    const existingIdx = tabs.findIndex(t => t.paper_id === paperId);
    if (existingIdx !== -1) {
      setActiveIdx(existingIdx);
      return;
    }

    const newIdx = tabs.length;
    setTabs(prev => [
      ...prev,
      { paper_id: paperId, status: 'processing', progress: 0, progressText: 'Uploading…', pdfReady: false },
    ]);
    setActiveIdx(newIdx);

    try {
      await uploadPaper(file, {
        model: resolvedModel,
        apiKey: settings.apiKey,
        readerExpertise: settings.readerExpertise,
        scientificKnowledge: settings.scientificKnowledge,
        languageComplexity: settings.languageComplexity,
        datalabKey: settings.datalabKey,
        domain: settings.domain,
      });
      setTabs(prev => prev.map(t => t.paper_id === paperId ? { ...t, pdfReady: true } : t));
      startPolling(paperId);
    } catch (err) {
      setTabs(prev => prev.map(t =>
        t.paper_id === paperId ? { ...t, status: 'error', error: err.message } : t
      ));
    }
  }, [tabs, settings, resolvedModel, startPolling]);

  const handleRetry = useCallback(async (paperId) => {
    setTabs(prev => prev.map(t =>
      t.paper_id === paperId ? { ...t, status: 'processing', progress: 0, progressText: 'Retrying…', error: null } : t
    ));
    try {
      await retryPaper(paperId);
      startPolling(paperId);
    } catch (err) {
      setTabs(prev => prev.map(t =>
        t.paper_id === paperId ? { ...t, status: 'error', error: err.message } : t
      ));
    }
  }, [startPolling]);

  const handleOpenFromLibrary = useCallback(async (entry) => {
    const { paper_id, detected_domain } = entry;
    setLibraryOpen(false);

    // Already open — just switch to it
    const existingIdx = tabs.findIndex(t => t.paper_id === paper_id);
    if (existingIdx !== -1) { setActiveIdx(existingIdx); return; }

    // Local cache available — show instantly, then refresh graph from server
    const cached = cacheLoadOne(paper_id);
    if (cached) {
      const newIdx = tabs.length;
      setTabs(prev => [...prev, { paper_id, status: 'done', fromCache: true, pdfReady: true, detectedDomain: detected_domain, ...cached }]);
      setActiveIdx(newIdx);
      openPaper(paper_id)
        .then(() => Promise.all([getGraph(paper_id), getSummary(paper_id)]))
        .then(([graphData, summaryData]) => {
          cacheSet(paper_id, graphData, summaryData);
          setTabs(prev => prev.map(t => t.paper_id !== paper_id ? t
            : { ...t, graphData, summaryData, detectedDomain: detected_domain }));
        })
        .catch(() => {});
      return;
    }

    // No local cache — ask backend to restore from output cache
    const newIdx = tabs.length;
    setTabs(prev => [...prev, { paper_id, status: 'processing', progress: 0, progressText: 'Restoring…' }]);
    setActiveIdx(newIdx);
    try {
      const result = await openPaper(paper_id);
      if (result.restored) {
        const [graphData, summaryData] = await Promise.all([getGraph(paper_id), getSummary(paper_id)]);
        cacheSet(paper_id, graphData, summaryData);
        setTabs(prev => prev.map(t => t.paper_id !== paper_id ? t
          : { ...t, status: 'done', graphData, summaryData, fromCache: false, detectedDomain: detected_domain }));
      } else {
        // PDF-only (no analysis cache)
        setTabs(prev => prev.map(t => t.paper_id !== paper_id ? t
          : { ...t, status: 'done', graphData: { nodes: {}, edges: [] }, summaryData: null, detectedDomain: detected_domain }));
      }
    } catch (err) {
      setTabs(prev => prev.map(t => t.paper_id !== paper_id ? t
        : { ...t, status: 'error', error: err.message }));
    }
  }, [tabs]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleDeletePaper = useCallback(async (paperId) => {
    try {
      await deletePaper(paperId);
    } catch (_) {}
    // Close the tab if open
    const idx = tabs.findIndex(t => t.paper_id === paperId);
    if (idx !== -1) {
      const tab = tabs[idx];
      if (tab.status === 'processing') cancelPaper(paperId);
      if (pollTimers.current[paperId]) {
        clearInterval(pollTimers.current[paperId]);
        delete pollTimers.current[paperId];
      }
      cacheDel(paperId);
      setTabs(prev => prev.filter(t => t.paper_id !== paperId));
      setActiveIdx(prev => Math.max(0, prev > idx ? prev - 1 : prev));
    } else {
      cacheDel(paperId);
    }
    setLibrary(prev => prev.filter(e => e.paper_id !== paperId));
  }, [tabs]);

  const closeTab = useCallback((idx) => {
    const tab = tabs[idx];
    if (tab) {
      const { paper_id, status } = tab;
      if (status === 'processing') cancelPaper(paper_id);
      if (pollTimers.current[paper_id]) {
        clearInterval(pollTimers.current[paper_id]);
        delete pollTimers.current[paper_id];
      }
      cacheDel(paper_id);
    }
    setTabs(prev => prev.filter((_, i) => i !== idx));
    setActiveIdx(prev => Math.max(0, prev >= idx ? prev - 1 : prev));
  }, [tabs]);

  // Cancel all in-progress uploads when the page is reloaded or closed
  useEffect(() => {
    const handler = () => {
      tabs.forEach(tab => {
        if (tab.status === 'processing') {
          navigator.sendBeacon(`/api/paper/${encodeURIComponent(tab.paper_id)}/cancel`);
        }
      });
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [tabs]);

  const activePaper = tabs[activeIdx] || null;

  // Stable anchor for the shared chat session — always the first done paper.
  // Using the first done paper keeps backend chat_messages in one place
  // regardless of which tab is active.
  const donePaperIds = tabs.filter(t => t.status === 'done').map(t => t.paper_id);
  const chatPaperId = donePaperIds[0] ?? null;

  // Restore chat history from localStorage when the active paper changes
  useEffect(() => {
    if (!chatPaperId) { setChatMessages([]); return; }
    setChatMessages(chatLoad(chatPaperId));
  }, [chatPaperId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Persist chat history whenever messages update
  useEffect(() => {
    if (chatPaperId && chatMessages.length > 0) chatSave(chatPaperId, chatMessages);
  }, [chatPaperId, chatMessages]);

  const clearChat = () => {
    if (chatPaperId) localStorage.removeItem(CHAT_PREFIX + chatPaperId);
    setChatMessages([]);
  };

  // section_id → page map built from summaryData when a paper is ready
  const [targetPage, setTargetPage] = useState({ page: null, seq: 0 });

  const sectionPageMap = (() => {
    const sections = activePaper?.summaryData?.section_qa;
    if (!sections) return {};
    return Object.fromEntries(
      sections.filter(s => s.page != null).map(s => [s.section_id, s.page])
    );
  })();

  const handleNodeClick = (sectionId) => {
    const page = sectionPageMap[sectionId];
    if (page) setTargetPage(prev => ({ page, seq: prev.seq + 1 }));
  };

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>

      {/* ── Sidebar + resize handle + collapse toggle ───────────────── */}
      <div style={{ display: 'flex', flexShrink: 0 }}>
        {panels.sidebar && (
          <Sidebar settings={settings} onUpdate={setSettings} authUser={authUser} onLogout={onLogout} width={sidebarWidth} />
        )}
        {panels.sidebar && (
          <ResizeDivider onDelta={dx => setSidebarWidth(w => Math.max(160, Math.min(500, w + dx)))} />
        )}
        <button
          onClick={() => toggle('sidebar')}
          title={panels.sidebar ? 'Collapse settings' : 'Expand settings'}
          style={{ width: 14, flexShrink: 0, background: '#1F2937', border: 'none', borderRight: '1px solid #374151', color: '#4B5563', cursor: 'pointer', fontSize: 11, padding: 0 }}
        >
          {panels.sidebar ? '‹' : '›'}
        </button>
      </div>

      {/* ── Paper workspace ─────────────────────────────────────────── */}
      {tabs.length === 0 ? (
        <HomePage onUpload={handleUpload} library={library} onOpenPaper={handleOpenFromLibrary} onDeletePaper={handleDeletePaper} />
      ) : (
        <div ref={workspaceRef} style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'stretch', background: '#1F2937', borderBottom: '1px solid #374151', flexShrink: 0 }}>
            <TabBar
              tabs={tabs}
              activeIdx={activeIdx}
              onSelect={setActiveIdx}
              onClose={closeTab}
              onUpload={handleUpload}
              onLibrary={() => setLibraryOpen(true)}
              libraryCount={library.length}
            />
          </div>

          {activePaper && (
            <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

              {/* PDF panel */}
              {panels.pdf ? (
                <div style={{ width: panels.summary ? `${pdfPct}%` : '100%', flexShrink: 0, minWidth: 150, overflow: 'hidden', display: 'flex', flexDirection: 'column', borderRight: '1px solid #374151' }}>
                  <PanelHeader label="PDF" dir="left" onCollapse={() => toggle('pdf')} />
                  <PdfViewer paperId={activePaper.pdfReady !== false ? activePaper.paper_id : null} targetPage={targetPage} />
                </div>
              ) : (
                <CollapseStrip label="PDF" dir="right" onClick={() => toggle('pdf')} />
              )}

              {/* Resize handle between PDF and Analysis */}
              {panels.pdf && panels.summary && (
                <ResizeDivider onDelta={dx => {
                  const total = workspaceRef.current?.clientWidth ?? 800;
                  setPdfPct(p => Math.max(15, Math.min(80, p + (dx / total) * 100)));
                }} />
              )}

              {/* Summary / Graph panel */}
              {panels.summary ? (
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'auto', minWidth: 150 }}>
                  <PanelHeader label="Analysis" dir="right" onCollapse={() => toggle('summary')} />
                  {activePaper.status !== 'done' ? (
                    <PipelineProgress
                      status={activePaper.status}
                      progress={activePaper.progress || 0}
                      text={activePaper.progressText || 'Starting…'}
                      error={activePaper.error}
                      onRetry={() => handleRetry(activePaper.paper_id)}
                    />
                  ) : (
                    <>
                      <div style={{ display: 'flex', gap: 0, flexShrink: 0 }}>
                        {activePaper.fromCache && (
                          <div style={{ padding: '4px 16px', background: '#1E3A5F', color: '#93C5FD', fontSize: 11 }}>
                            ⚡ Loaded {activePaper.paper_id} from cache
                          </div>
                        )}
                        {activePaper.detectedDomain && (
                          <DomainBadge domain={activePaper.detectedDomain} />
                        )}
                      </div>
                      {Object.keys(activePaper.graphData?.nodes ?? {}).length > 0 && (
                        <KnowledgeGraph
                          graphData={activePaper.graphData}
                          sectionPageMap={sectionPageMap}
                          onNodeClick={handleNodeClick}
                        />
                      )}
                      <Summary summaryData={activePaper.summaryData} />
                    </>
                  )}
                </div>
              ) : (
                <CollapseStrip label="Analysis" dir="left" onClick={() => toggle('summary')} />
              )}

            </div>
          )}
        </div>
      )}

      {/* ── Library overlay ──────────────────────────────────────────── */}
      {libraryOpen && (
        <>
          <div onClick={() => setLibraryOpen(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1002, backdropFilter: 'blur(2px)' }} />
          <div style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', width: 'min(780px,92vw)', maxHeight: '80vh', zIndex: 1003, borderRadius: 16, overflow: 'hidden', boxShadow: '0 20px 80px rgba(0,0,0,0.7)', border: '1px solid #4B5563', display: 'flex', flexDirection: 'column', background: '#111827' }}>
            <div style={{ padding: '14px 20px', background: '#1F2937', borderBottom: '1px solid #374151', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
              <span style={{ fontWeight: 700, color: '#F9FAFB', fontSize: 15 }}>📚 My Papers</span>
              <button onClick={() => setLibraryOpen(false)} style={{ background: 'none', border: 'none', color: '#6B7280', fontSize: 20, cursor: 'pointer', lineHeight: 1 }}>×</button>
            </div>
            <div style={{ overflowY: 'auto', padding: 20 }}>
              <PaperGrid library={library} onOpen={handleOpenFromLibrary} onDelete={handleDeletePaper} />
            </div>
          </div>
        </>
      )}

      {/* ── Floating Chat (small) ─────────────────────────────────────── */}
      {chatOpen && !chatExpanded && (
        <div style={{
          position: 'fixed',
          bottom: 80,
          right: 24,
          width: 360,
          height: 360,
          zIndex: 1000,
          borderRadius: 14,
          overflow: 'hidden',
          boxShadow: '0 12px 48px rgba(0,0,0,0.6)',
          border: '1px solid #374151',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <Chat
            chatPaperId={chatPaperId}
            allPaperIds={donePaperIds}
            messages={chatMessages}
            onMessages={setChatMessages}
            model={resolvedModel}
            apiKey={settings.apiKey}
            readerParams={readerParams}
            onToggle={() => setChatOpen(false)}
            onExpand={() => setChatExpanded(true)}
            onClear={clearChat}
          />
        </div>
      )}

      {/* ── Expanded Chat modal ───────────────────────────────────────── */}
      {chatExpanded && (
        <>
          <div
            onClick={() => setChatExpanded(false)}
            style={{
              position: 'fixed', inset: 0,
              background: 'rgba(0,0,0,0.6)',
              zIndex: 1002,
              backdropFilter: 'blur(2px)',
            }}
          />
          <div style={{
            position: 'fixed',
            top: '50%', left: '50%',
            transform: 'translate(-50%, -50%)',
            width: 'min(720px, 90vw)',
            height: 'min(640px, 85vh)',
            zIndex: 1003,
            borderRadius: 16,
            overflow: 'hidden',
            boxShadow: '0 20px 80px rgba(0,0,0,0.7)',
            border: '1px solid #4B5563',
            display: 'flex',
            flexDirection: 'column',
          }}>
            <Chat
              chatPaperId={chatPaperId}
              allPaperIds={donePaperIds}
              messages={chatMessages}
              onMessages={setChatMessages}
              model={resolvedModel}
              apiKey={settings.apiKey}
              readerParams={readerParams}
              onToggle={() => { setChatExpanded(false); setChatOpen(false); }}
              onExpand={() => setChatExpanded(false)}
              onClear={clearChat}
              expanded
            />
          </div>
        </>
      )}

      {/* ── FAB toggle ───────────────────────────────────────────────── */}
      <button
        onClick={() => { setChatOpen(o => !o); setChatExpanded(false); }}
        title={chatOpen || chatExpanded ? 'Close chat' : 'Open chat'}
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          width: 52,
          height: 52,
          borderRadius: '50%',
          background: (chatOpen || chatExpanded) ? '#1D4ED8' : '#2563EB',
          border: 'none',
          color: '#fff',
          fontSize: (chatOpen || chatExpanded) ? 22 : 20,
          cursor: 'pointer',
          zIndex: 1004,
          boxShadow: '0 4px 24px rgba(37,99,235,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'background 0.15s',
        }}
      >
        {(chatOpen || chatExpanded) ? '×' : '💬'}
      </button>

      {/* Marker decision modal — shown when auto-detect finds a math-heavy paper */}
      {(() => {
        const waiting = tabs.find(t => t.status === 'awaiting_marker_decision');
        return waiting ? (
          <MarkerDecisionModal
            paperId={waiting.paper_id}
            adminMode={adminMode}
            onDone={() => {}}
          />
        ) : null;
      })()}

    </div>
  );
}

function CollapseStrip({ label, dir, onClick }) {
  return (
    <div
      onClick={onClick}
      title={`Show ${label}`}
      style={{
        width: 28, flexShrink: 0, cursor: 'pointer',
        background: '#1F2937', display: 'flex', alignItems: 'center', justifyContent: 'center',
        borderRight: dir === 'right' ? '1px solid #374151' : 'none',
        borderLeft:  dir === 'left'  ? '1px solid #374151' : 'none',
        color: '#6B7280', userSelect: 'none',
      }}
      onMouseEnter={e => e.currentTarget.style.background = '#374151'}
      onMouseLeave={e => e.currentTarget.style.background = '#1F2937'}
    >
      <span style={{ fontSize: 11, writingMode: 'vertical-rl', transform: dir === 'right' ? 'rotate(180deg)' : 'none', color: '#9CA3AF', letterSpacing: 1 }}>
        {label}
      </span>
    </div>
  );
}

function PanelHeader({ label, dir = 'left', onCollapse }) {
  return (
    <div style={{
      padding: '3px 8px 3px 14px', background: '#1F2937', borderBottom: '1px solid #374151',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0,
      fontSize: 11, color: '#6B7280',
    }}>
      <span style={{ letterSpacing: 1, textTransform: 'uppercase' }}>{label}</span>
      <button
        onClick={onCollapse}
        title={`Collapse ${label}`}
        style={{ background: 'none', border: 'none', color: '#4B5563', cursor: 'pointer', fontSize: 16, padding: '0 4px', lineHeight: 1 }}
        onMouseEnter={e => e.target.style.color = '#9CA3AF'}
        onMouseLeave={e => e.target.style.color = '#4B5563'}
      >{dir === 'left' ? '‹' : '›'}</button>
    </div>
  );
}

function PipelineProgress({ status, progress, text, error, onRetry }) {
  if (status === 'error') {
    return (
      <div style={{ padding: 24 }}>
        <div style={{ color: '#EF4444', fontWeight: 600, marginBottom: 8 }}>Pipeline failed</div>
        <div style={{ color: '#9CA3AF', fontSize: 13, marginBottom: 16 }}>{error}</div>
        {onRetry && (
          <button
            onClick={onRetry}
            style={{
              padding: '8px 20px', borderRadius: 7, border: 'none',
              background: '#2563EB', color: '#fff', fontWeight: 600,
              fontSize: 13, cursor: 'pointer',
            }}
          >
            ↺ Retry
          </button>
        )}
      </div>
    );
  }
  return (
    <div style={{ padding: 24 }}>
      <div style={{ color: '#9CA3AF', marginBottom: 10, fontSize: 13 }}>{text}</div>
      <div style={{ background: '#374151', borderRadius: 6, height: 8, overflow: 'hidden' }}>
        <div style={{
          background: '#2563EB',
          width: `${progress}%`,
          height: '100%',
          borderRadius: 6,
          transition: 'width 0.4s ease',
        }} />
      </div>
      <div style={{ color: '#6B7280', fontSize: 12, marginTop: 6 }}>{progress}%</div>
    </div>
  );
}

function ResizeDivider({ onDelta }) {
  const onDeltaRef = useRef(onDelta);
  useEffect(() => { onDeltaRef.current = onDelta; }, [onDelta]);

  const handleMouseDown = useCallback((e) => {
    let lastX = e.clientX;
    e.preventDefault();
    const onMove = (ev) => {
      const dx = ev.clientX - lastX;
      lastX = ev.clientX;
      onDeltaRef.current(dx);
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
    };
    document.body.style.cursor = 'col-resize';
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, []);

  return (
    <div
      onMouseDown={handleMouseDown}
      style={{ width: 5, flexShrink: 0, cursor: 'col-resize', background: '#1F2937', zIndex: 10 }}
      onMouseEnter={e => e.currentTarget.style.background = '#3B82F6'}
      onMouseLeave={e => e.currentTarget.style.background = '#1F2937'}
    />
  );
}

function DomainBadge({ domain }) {
  const isMath = domain === 'math';
  return (
    <div style={{
      padding: '4px 16px',
      background: isMath ? '#1A2E1A' : '#2D1B3D',
      color: isMath ? '#86EFAC' : '#C4B5FD',
      fontSize: 11,
      borderLeft: '1px solid #374151',
    }}>
      {isMath ? '∑ Math-heavy' : '✦ Non-math'}
    </div>
  );
}

function PaperGrid({ library, onOpen, onDelete }) {
  if (!library.length) {
    return <div style={{ color: '#4B5563', fontSize: 13, textAlign: 'center', padding: '24px 0' }}>No papers yet — upload your first PDF to get started.</div>;
  }
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 12 }}>
      {library.map(entry => {
        const isMath = entry.detected_domain === 'math';
        const date = entry.uploaded_at ? new Date(entry.uploaded_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '';
        return (
          <div
            key={entry.paper_id}
            style={{ position: 'relative' }}
            onMouseEnter={e => e.currentTarget.querySelector('.del-btn').style.opacity = '1'}
            onMouseLeave={e => e.currentTarget.querySelector('.del-btn').style.opacity = '0'}
          >
            <button
              onClick={() => onOpen(entry)}
              title={entry.title || entry.paper_id}
              style={{ width: '100%', background: '#1F2937', border: '1px solid #374151', borderRadius: 10, padding: '14px 12px 10px', cursor: 'pointer', textAlign: 'left', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, transition: 'border-color 0.15s' }}
              onMouseEnter={e => e.currentTarget.style.borderColor = '#3B82F6'}
              onMouseLeave={e => e.currentTarget.style.borderColor = '#374151'}
            >
              <div style={{ fontSize: 32, lineHeight: 1 }}>📄</div>
              <div style={{ fontSize: 11, color: '#F3F4F6', fontWeight: 600, textAlign: 'center', wordBreak: 'break-word', lineHeight: 1.4, maxHeight: 44, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical' }}>
                {entry.title || entry.paper_id}
              </div>
              <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
                {entry.detected_domain && (
                  <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 6, background: isMath ? '#1A2E1A' : '#2D1B3D', color: isMath ? '#86EFAC' : '#C4B5FD' }}>
                    {isMath ? '∑ Math' : '✦ Prose'}
                  </span>
                )}
                {date && <span style={{ fontSize: 9, color: '#4B5563' }}>{date}</span>}
              </div>
            </button>
            {onDelete && (
              <button
                className="del-btn"
                onClick={e => { e.stopPropagation(); onDelete(entry.paper_id); }}
                title="Delete paper"
                style={{ position: 'absolute', top: 6, right: 6, opacity: 0, transition: 'opacity 0.15s', background: '#7F1D1D', border: 'none', borderRadius: 4, color: '#FCA5A5', fontSize: 11, width: 20, height: 20, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', lineHeight: 1 }}
              >
                ×
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

function HomePage({ onUpload, library = [], onOpenPaper, onDeletePaper }) {
  const fileRef = useRef(null);

  const features = [
    { icon: '🔍', title: 'Parse', desc: 'Extracts text and structure from any research PDF using Marker or PyMuPDF.' },
    { icon: '🕸️', title: 'Knowledge Graph', desc: 'Automatically maps theorems, lemmas, proofs, and their dependencies into a visual graph.' },
    { icon: '📖', title: 'Summary', desc: 'Generates a holistic summary with narrative arcs, key questions, and equation chains.' },
    { icon: '💬', title: 'Chat', desc: 'Ask questions about the paper. A ReAct agent retrieves relevant sections before answering.' },
  ];

  const settingsGuide = [
    {
      group: 'Provider & API Key',
      desc: 'Choose which LLM provider powers the pipeline (Groq, OpenAI, Gemini, OpenRouter, etc.). Paste your API key for that provider — it is sent directly to the backend and never stored. Without a valid key the pipeline will fail at the synthesis step.',
    },
    {
      group: 'Model',
      desc: 'Select the specific model within your chosen provider. Larger models (e.g. llama-3.3-70b, gpt-4o) produce richer summaries and chains; smaller/free models are faster. The model is used for synthesis, equation chains, and chat.',
    },
    {
      group: 'Paper Domain',
      desc: '"Auto-detect" lets the pipeline decide whether the paper is math-heavy or prose-heavy and choose the graph builder accordingly. Override to "Math" or "English" if auto-detection is wrong.',
    },
    {
      group: 'Reader Profile',
      desc: 'Three sliders calibrate how the AI tailors its explanations to you. Expertise: 0 = beginner, 1 = expert. Scientific Knowledge: how much domain jargon is assumed. Language Complexity: 0 = plain language, 1 = full technical precision. These are passed to every synthesis and chat call.',
    },
  ];

  return (
    <div style={{
      flex: 1,
      background: '#111827',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      paddingTop: 56,
      paddingBottom: 56,
      paddingLeft: 32,
      paddingRight: 32,
      overflowY: 'auto',
    }}>
      <div style={{ maxWidth: 680, width: '100%', textAlign: 'center' }}>
        {/* Title */}
        <div style={{ fontSize: 12, color: '#6B7280', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 12 }}>
          Research Paper Assistant
        </div>
        <h1 style={{ fontSize: 34, fontWeight: 700, color: '#F9FAFB', margin: '0 0 16px', lineHeight: 1.2 }}>
          Understand any paper,<br />deeply and fast.
        </h1>
        <p style={{ fontSize: 14, color: '#9CA3AF', marginBottom: 36, lineHeight: 1.7 }}>
          Upload a research PDF. The app parses it, builds a knowledge graph of its structure,
          generates a layered summary, and lets you ask questions about it using an AI agent
          that retrieves the right sections before answering.
        </p>

        {/* Upload button */}
        <button
          onClick={() => fileRef.current?.click()}
          style={{
            background: '#2563EB',
            color: '#fff',
            border: 'none',
            borderRadius: 10,
            padding: '13px 32px',
            fontSize: 15,
            fontWeight: 600,
            cursor: 'pointer',
            marginBottom: 48,
            boxShadow: '0 4px 20px rgba(37,99,235,0.4)',
          }}
        >
          Upload PDF
        </button>

        {/* Your Papers library */}
        {library.length > 0 && (
          <div style={{ marginBottom: 48, textAlign: 'left' }}>
            <div style={{ fontSize: 11, color: '#6B7280', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 14 }}>
              Your Papers
            </div>
            <PaperGrid library={library} onOpen={onOpenPaper} onDelete={onDeletePaper} />
          </div>
        )}

        {/* Feature grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 14,
          textAlign: 'left',
          marginBottom: 48,
        }}>
          {features.map(({ icon, title, desc }) => (
            <div key={title} style={{
              background: '#1F2937',
              border: '1px solid #374151',
              borderRadius: 10,
              padding: '14px 16px',
            }}>
              <div style={{ fontSize: 20, marginBottom: 6 }}>{icon}</div>
              <div style={{ fontWeight: 600, color: '#F3F4F6', fontSize: 13, marginBottom: 4 }}>{title}</div>
              <div style={{ color: '#9CA3AF', fontSize: 12, lineHeight: 1.6 }}>{desc}</div>
            </div>
          ))}
        </div>

        {/* Settings guide */}
        <div style={{ textAlign: 'left' }}>
          <div style={{ fontSize: 11, color: '#6B7280', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 14 }}>
            About the settings
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {settingsGuide.map(({ group, desc }) => (
              <div key={group} style={{
                background: '#1F2937',
                border: '1px solid #374151',
                borderRadius: 8,
                padding: '12px 16px',
              }}>
                <div style={{ fontWeight: 600, color: '#93C5FD', fontSize: 12, marginBottom: 4 }}>{group}</div>
                <div style={{ color: '#9CA3AF', fontSize: 12, lineHeight: 1.65 }}>{desc}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 14, fontSize: 11, color: '#4B5563', textAlign: 'center' }}>
            Configure settings in the panel on the left before uploading.
          </div>
        </div>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept=".pdf"
        style={{ display: 'none' }}
        onChange={e => {
          const f = e.target.files?.[0];
          if (f) { onUpload(f); e.target.value = ''; }
        }}
      />
    </div>
  );
}
