import { useState, useEffect } from 'react';
import { fetchProviders, fetchProviderModels } from '../api';

export default function Sidebar({ settings, onUpdate, authUser, onLogout, width }) {
  const [providers, setProviders]       = useState([]);
  const [loadError, setLoadError]       = useState(null);
  const [orModels, setOrModels]           = useState([]);
  const [fetchingOrModels, setFetchingOrModels] = useState(false);
  const [ollamaModels, setOllamaModels]   = useState([]);
  const [fetchingOllama, setFetchingOllama] = useState(false);
  const [linked, setLinked]             = useState(true);
  const [applied, setApplied]           = useState(false);

  // ── all inputs are draft until Apply Settings ─────────────────────
  const [draft, setDraft] = useState({
    provider:            settings.provider            || '',
    prefix:              settings.prefix              || '',
    model:               settings.model               || '',
    apiKey:              settings.apiKey              || '',
    readerExpertise:     settings.readerExpertise     ?? 0,
    scientificKnowledge: settings.scientificKnowledge ?? 0,
    languageComplexity:  settings.languageComplexity  ?? 0,
    domain:              settings.domain              || 'auto',
  });

  const setDraftField = (key, val) => setDraft(d => ({ ...d, [key]: val }));

  // ── load providers once on mount ──────────────────────────────────
  useEffect(() => {
    fetchProviders()
      .then(data => {
        setProviders(data);
        if (!draft.provider && data.length > 0) {
          const first = data[0];
          setDraft(d => ({ ...d, provider: first.name, prefix: first.prefix, model: first.default_model }));
        }
      })
      .catch(err => setLoadError(err.message));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── reset provider-specific model lists when provider changes ────
  useEffect(() => {
    setOrModels([]);
    setOllamaModels([]);
    if (draft.prefix === 'ollama') {
      setFetchingOllama(true);
      fetchProviderModels('ollama', null)
        .then(({ models }) => {
          const list = models ?? [];
          setOllamaModels(list);
          if (list.length > 0) setDraftField('model', list[0]);
        })
        .catch(() => {})
        .finally(() => setFetchingOllama(false));
    }
  }, [draft.prefix]); // eslint-disable-line react-hooks/exhaustive-deps

  const provInfo     = providers.find(p => p.name === draft.provider) ?? null;
  const isOpenRouter = draft.prefix === 'openrouter';
  const isOllama     = draft.prefix === 'ollama';
  const fixedModels  = provInfo?.models ?? [];

  const handleProviderChange = (name) => {
    const info = providers.find(p => p.name === name);
    if (!info) return;
    setDraft(d => ({
      ...d,
      provider: info.name,
      prefix:   info.prefix,
      model:    info.models[0] ?? info.default_model,
      apiKey:   '',
    }));
    setOrModels([]);
  };

  const applyKey = async () => {
    const key = draft.apiKey.trim();
    if (!key || !isOpenRouter) return;
    setFetchingOrModels(true);
    try {
      const { models } = await fetchProviderModels(draft.prefix, key);
      const list = models ?? [];
      setOrModels(list);
      if (list.length > 0) setDraftField('model', list[0]);
    } catch (e) {
      console.error('OpenRouter model fetch failed:', e);
    } finally {
      setFetchingOrModels(false);
    }
  };

  const handleExpertise = (v) => {
    if (linked) {
      setDraft(d => ({ ...d, readerExpertise: v, scientificKnowledge: v, languageComplexity: v }));
    } else {
      setDraftField('readerExpertise', v);
    }
  };

  const handleApply = () => {
    onUpdate(s => ({ ...s, ...draft }));
    setApplied(true);
    setTimeout(() => setApplied(false), 2000);
  };

  // ── loading / error states ────────────────────────────────────────
  if (loadError) {
    return (
      <div style={width ? { ...sidebarStyle, width, minWidth: width } : sidebarStyle}>
        <div style={{ color: '#EF4444', fontSize: 12 }}>
          Failed to load settings from backend:<br />{loadError}
        </div>
      </div>
    );
  }
  if (providers.length === 0) {
    return (
      <div style={width ? { ...sidebarStyle, width, minWidth: width } : sidebarStyle}>
        <div style={{ color: '#6B7280', fontSize: 13 }}>Loading settings…</div>
      </div>
    );
  }

  return (
    <div style={sidebarStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontWeight: 700 }}>⚙️ Settings</div>
        {authUser && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, color: '#6B7280', maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {authUser.email}
            </span>
            <button
              onClick={onLogout}
              title="Sign out"
              style={{ background: 'none', border: '1px solid #374151', borderRadius: 5, color: '#6B7280', fontSize: 11, padding: '2px 8px', cursor: 'pointer' }}
              onMouseEnter={e => e.target.style.color = '#F9FAFB'}
              onMouseLeave={e => e.target.style.color = '#6B7280'}
            >
              out
            </button>
          </div>
        )}
      </div>

      {/* ── Provider ──────────────────────────────────────────────── */}
      <Section title="Provider">
        <select value={draft.provider} onChange={e => handleProviderChange(e.target.value)} style={sel}>
          {providers.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
        </select>
        {provInfo?.notes && <Note>{provInfo.notes}</Note>}
      </Section>

      {/* ── API Key (hidden for providers that need no key, e.g. Ollama) */}
      {provInfo?.env_var !== '' && (
        <Section title="API Key">
          <input
            type="password"
            value={draft.apiKey}
            onChange={e => setDraftField('apiKey', e.target.value)}
            onKeyDown={e => e.key === 'Enter' && applyKey()}
            onBlur={() => isOpenRouter && applyKey()}
            placeholder={provInfo?.key_hint ?? '...'}
            style={inp}
            autoComplete="off"
          />
        </Section>
      )}

      {/* ── Model ─────────────────────────────────────────────────── */}
      <Section title="Model">
        {isOpenRouter && !draft.apiKey ? (
          <div style={placeholder}>Enter API key then Apply Settings</div>
        ) : isOpenRouter && fetchingOrModels ? (
          <div style={placeholder}>Fetching models…</div>
        ) : isOllama && fetchingOllama ? (
          <div style={placeholder}>Scanning local Ollama…</div>
        ) : (
          <select value={draft.model} onChange={e => setDraftField('model', e.target.value)} style={sel}>
            {(isOpenRouter ? orModels : isOllama && ollamaModels.length > 0 ? ollamaModels : fixedModels).map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        )}
        {isOpenRouter && !fetchingOrModels && orModels.length > 0 && (
          <Note>{orModels.length} free models</Note>
        )}
        {isOllama && !fetchingOllama && (
          <Note>{ollamaModels.length > 0 ? `${ollamaModels.length} installed` : 'Ollama not running — showing defaults'}</Note>
        )}
      </Section>

      {/* ── Paper Domain ─────────────────────────────────────────── */}
      <Section title="Paper Domain">
        <select value={draft.domain} onChange={e => setDraftField('domain', e.target.value)} style={sel}>
          <option value="auto">Auto-detect</option>
          <option value="math">Math-heavy</option>
          <option value="non-math">Non-math</option>
        </select>
        <Note>
          {draft.domain === 'math'     && 'Knowledge graph + equation chains (regex-based)'}
          {draft.domain === 'non-math' && 'Section synthesis with keyword extraction, 1 LLM call'}
          {(!draft.domain || draft.domain === 'auto') && 'Detected from document content'}
        </Note>
      </Section>

      {/* ── Reader Profile ────────────────────────────────────────── */}
      <div style={{ borderTop: '1px solid #374151', paddingTop: 12 }}>
        <div style={{ fontWeight: 600, marginBottom: 10 }}>Reader Profile</div>
        <label style={{
          display: 'flex', alignItems: 'center', gap: 8,
          fontSize: 12, color: '#9CA3AF', marginBottom: 12,
          cursor: 'pointer', userSelect: 'none',
        }}>
          <input type="checkbox" checked={linked} onChange={e => setLinked(e.target.checked)} />
          Link all parameters
        </label>
        <Slider label="Expertise"   value={draft.readerExpertise}     onChange={handleExpertise} />
        <Slider label="Scientific"  value={draft.scientificKnowledge} onChange={v => !linked && setDraftField('scientificKnowledge', v)} disabled={linked} />
        <Slider label="Language"    value={draft.languageComplexity}  onChange={v => !linked && setDraftField('languageComplexity', v)}  disabled={linked} />
      </div>

      {/* ── Apply Settings ───────────────────────────────────────── */}
      <div style={{ marginTop: 'auto', paddingTop: 12, borderTop: '1px solid #374151' }}>
        <button onClick={handleApply} style={{
          width: '100%', padding: '9px 0',
          background: applied ? '#065F46' : '#2563EB',
          border: 'none', borderRadius: 6,
          color: '#fff', fontWeight: 700, fontSize: 14,
          cursor: 'pointer', transition: 'background 0.2s',
        }}>
          {applied ? '✓ Settings Applied' : 'Apply Settings'}
        </button>
      </div>
    </div>
  );
}

// ── sub-components ────────────────────────────────────────────────────

function Section({ title, children }) {
  return (
    <div>
      <label style={{
        display: 'block', fontSize: 11, color: '#9CA3AF',
        marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.05em',
      }}>
        {title}
      </label>
      {children}
    </div>
  );
}

function Note({ children }) {
  return <div style={{ color: '#6B7280', fontSize: 11, marginTop: 4 }}>{children}</div>;
}

function Slider({ label, value, onChange, disabled }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        fontSize: 12, color: disabled ? '#4B5563' : '#9CA3AF', marginBottom: 4,
      }}>
        <span>{label}</span><span>{value.toFixed(2)}</span>
      </div>
      <input
        type="range" min={0} max={1} step={0.05}
        value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        disabled={disabled}
        style={{ width: '100%', accentColor: '#3B82F6', opacity: disabled ? 0.4 : 1 }}
      />
    </div>
  );
}

// ── styles ────────────────────────────────────────────────────────────

const sidebarStyle = {
  width: 284, minWidth: 284,
  background: '#1F2937', borderRight: '1px solid #374151',
  overflowY: 'auto', padding: '16px 14px',
  display: 'flex', flexDirection: 'column', gap: 16,
};

const sel = {
  width: '100%', background: '#374151', border: '1px solid #4B5563',
  borderRadius: 4, color: '#F9FAFB', padding: '6px 28px 6px 8px',
  outline: 'none', cursor: 'pointer',
  appearance: 'none', WebkitAppearance: 'none',
  backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%239CA3AF'/%3E%3C/svg%3E\")",
  backgroundRepeat: 'no-repeat', backgroundPosition: 'right 9px center',
};

const inp = {
  width: '100%', background: '#374151', border: '1px solid #4B5563',
  borderRadius: 4, color: '#F9FAFB', padding: '6px 8px',
  outline: 'none', boxSizing: 'border-box',
};

const placeholder = {
  padding: '6px 8px', background: '#374151', border: '1px solid #4B5563',
  borderRadius: 4, color: '#6B7280', fontSize: 13,
};
