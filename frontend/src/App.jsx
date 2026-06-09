import { useState, useCallback, useRef, useEffect } from 'react';

// ── localStorage cache helpers ─────────────────────────────────────────
const CACHE_PREFIX = 'rpa:';
function cacheSet(paperId, graphData, summaryData) {
  try { localStorage.setItem(CACHE_PREFIX + paperId, JSON.stringify({ graphData, summaryData })); } catch (_) {}
}
function cacheDel(paperId) { localStorage.removeItem(CACHE_PREFIX + paperId); }
function cacheLoadAll() {
  const out = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key?.startsWith(CACHE_PREFIX)) continue;
    try {
      const { graphData, summaryData } = JSON.parse(localStorage.getItem(key));
      if (graphData && summaryData)
        out.push({ paper_id: key.slice(CACHE_PREFIX.length), status: 'done', fromCache: true, graphData, summaryData });
    } catch (_) {}
  }
  return out;
}
import Sidebar from './components/Sidebar';
import TabBar from './components/TabBar';
import PdfViewer from './components/PdfViewer';
import KnowledgeGraph from './components/KnowledgeGraph';
import Summary from './components/Summary';
import Chat from './components/Chat';
import { uploadPaper, getStatus, getGraph, getSummary, cancelPaper } from './api';

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
  const [tabs, setTabs] = useState([]);
  const [activeIdx, setActiveIdx] = useState(0);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);

  const pollTimers = useRef({});

  // Restore any previously cached papers on first mount
  useEffect(() => {
    const cached = cacheLoadAll();
    if (cached.length > 0) setTabs(cached);
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
          const [graphData, summaryData] = await Promise.all([
            getGraph(paperId), getSummary(paperId),
          ]);
          cacheSet(paperId, graphData, summaryData);
          setTabs(prev => prev.map(t =>
            t.paper_id !== paperId ? t : { ...t, graphData, summaryData, fromCache: false }
          ));
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
      { paper_id: paperId, status: 'processing', progress: 0, progressText: 'Uploading…' },
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
      startPolling(paperId);
    } catch (err) {
      setTabs(prev => prev.map(t =>
        t.paper_id === paperId ? { ...t, status: 'error', error: err.message } : t
      ));
    }
  }, [tabs, settings, resolvedModel, startPolling]);

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

  // section_id → page map built from summaryData when a paper is ready
  const [targetPage, setTargetPage] = useState(null);

  const sectionPageMap = (() => {
    const sections = activePaper?.summaryData?.section_qa;
    if (!sections) return {};
    return Object.fromEntries(
      sections.filter(s => s.page != null).map(s => [s.section_id, s.page])
    );
  })();

  const handleNodeClick = (sectionId) => {
    const page = sectionPageMap[sectionId];
    if (page) setTargetPage(page);
  };

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* Sidebar — always visible, even on homepage */}
      <Sidebar settings={settings} onUpdate={setSettings} />

      {tabs.length === 0 ? (
        /* ── Homepage ─────────────────────────────────────────────────── */
        <HomePage onUpload={handleUpload} />
      ) : (
        /* ── Main workspace ───────────────────────────────────────────── */
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
          {/* Top bar */}
          <div style={{ display: 'flex', alignItems: 'stretch', background: '#1F2937', borderBottom: '1px solid #374151', flexShrink: 0 }}>
            <TabBar
              tabs={tabs}
              activeIdx={activeIdx}
              onSelect={setActiveIdx}
              onClose={closeTab}
              onUpload={handleUpload}
            />
          </div>

          {activePaper && (
            <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
              <div style={{ flex: 1, overflow: 'hidden', borderRight: '1px solid #374151' }}>
                <PdfViewer paperId={activePaper.paper_id} targetPage={targetPage} />
              </div>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'auto', minWidth: 0 }}>
                {activePaper.status !== 'done' ? (
                  <PipelineProgress
                    status={activePaper.status}
                    progress={activePaper.progress || 0}
                    text={activePaper.progressText || 'Starting…'}
                    error={activePaper.error}
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
                    <KnowledgeGraph
                      graphData={activePaper.graphData}
                      sectionPageMap={sectionPageMap}
                      onNodeClick={handleNodeClick}
                    />
                    <Summary summaryData={activePaper.summaryData} />
                    <Chat
                      paperId={activePaper.paper_id}
                      model={resolvedModel}
                      apiKey={settings.apiKey}
                      readerParams={readerParams}
                    />
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PipelineProgress({ status, progress, text, error }) {
  if (status === 'error') {
    return (
      <div style={{ padding: 24 }}>
        <div style={{ color: '#EF4444', fontWeight: 600, marginBottom: 8 }}>Pipeline failed</div>
        <div style={{ color: '#9CA3AF', fontSize: 13 }}>{error}</div>
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
      {isMath ? '∑ Math' : '✦ English'} graph
    </div>
  );
}

function HomePage({ onUpload }) {
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
