import { useState, useEffect } from 'react';
import { fetchProviders, fetchOpenRouterModels } from '../api';

export default function Sidebar({ settings, onUpdate }) {
  // providers: array of {name, prefix, default_model, key_hint, notes, models}
  const [providers, setProviders] = useState([]);
  const [loadError, setLoadError] = useState(null);

  // OpenRouter-specific: live free-model list + loading flag
  const [orModels, setOrModels] = useState([]);
  const [fetchingOrModels, setFetchingOrModels] = useState(false);

  const [linked, setLinked] = useState(true);

  // Draft key — only committed to parent settings when user clicks Save
  const [draftKey, setDraftKey] = useState('');
  const [keySaved, setKeySaved] = useState(false);

  // ── load providers from backend once on mount ──────────────────────
  useEffect(() => {
    fetchProviders()
      .then(data => {
        setProviders(data);
        // Initialise settings with the first provider if nothing is selected yet
        if (!settings.provider && data.length > 0) {
          const first = data[0];
          onUpdate(s => ({
            ...s,
            provider:  first.name,
            prefix:    first.prefix,
            model:     first.default_model,
          }));
        }
      })
      .catch(err => setLoadError(err.message));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── derived info for the currently selected provider ──────────────
  const provInfo    = providers.find(p => p.name === settings.provider) ?? null;
  const isOpenRouter = settings.prefix === 'openrouter';

  // ── reset draft key and OR model list when provider changes ───────
  useEffect(() => {
    setDraftKey('');
    setKeySaved(false);
    setOrModels([]);
  }, [settings.provider]);

  // ── helpers ───────────────────────────────────────────────────────
  const set = (key, val) => onUpdate(s => ({ ...s, [key]: val }));

  const handleProviderChange = (name) => {
    const info = providers.find(p => p.name === name);
    if (!info) return;
    onUpdate(s => ({
      ...s,
      provider: info.name,
      prefix:   info.prefix,
      model:    info.models[0] ?? info.default_model,
      apiKey:   '',            // clear stale key from previous provider
    }));
  };

  const applyKey = async () => {
    const key = draftKey.trim();
    if (!key) return;
    onUpdate(s => ({ ...s, apiKey: key }));
    setKeySaved(true);
    setTimeout(() => setKeySaved(false), 2000);

    if (isOpenRouter) {
      setFetchingOrModels(true);
      try {
        const { models } = await fetchOpenRouterModels(key);
        setOrModels(models ?? []);
        if (models?.length > 0) {
          onUpdate(s => ({ ...s, model: models[0] }));
        }
      } catch (e) {
        console.error('OpenRouter model fetch failed:', e);
      } finally {
        setFetchingOrModels(false);
      }
    }
  };

  const handleExpertise = (v) => {
    if (linked) {
      onUpdate(s => ({
        ...s,
        readerExpertise:     v,
        scientificKnowledge: v,
        languageComplexity:  v,
      }));
    } else {
      set('readerExpertise', v);
    }
  };

  const fixedModels = provInfo?.models ?? [];

  // ── loading / error states ────────────────────────────────────────
  if (loadError) {
    return (
      <div style={sidebarStyle}>
        <div style={{ color: '#EF4444', fontSize: 12 }}>
          Failed to load settings from backend:<br />{loadError}
        </div>
      </div>
    );
  }

  if (providers.length === 0) {
    return (
      <div style={sidebarStyle}>
        <div style={{ color: '#6B7280', fontSize: 13 }}>Loading settings…</div>
      </div>
    );
  }

  return (
    <div style={sidebarStyle}>
      <div style={{ fontWeight: 700 }}>⚙️ Settings</div>

      {/* ── Provider ──────────────────────────────────────────────── */}
      <Section title="Provider">
        <select
          value={settings.provider}
          onChange={e => handleProviderChange(e.target.value)}
          style={sel}
        >
          {providers.map(p => (
            <option key={p.name} value={p.name}>{p.name}</option>
          ))}
        </select>
        {provInfo?.notes && <Note>{provInfo.notes}</Note>}
      </Section>

      {/* ── API Key ───────────────────────────────────────────────── */}
      <Section title="API Key">
        <input
          type="password"
          value={draftKey}
          onChange={e => { setDraftKey(e.target.value); setKeySaved(false); }}
          onKeyDown={e => e.key === 'Enter' && applyKey()}
          onBlur={() => isOpenRouter && applyKey()}
          placeholder={provInfo?.key_hint ?? '...'}
          style={{ ...inp, marginBottom: 6 }}
          autoComplete="off"
        />
        <button
          onClick={applyKey}
          style={{
            width: '100%',
            padding: '6px 0',
            background: keySaved ? '#065F46' : '#1D4ED8',
            border: 'none',
            borderRadius: 4,
            color: '#fff',
            fontWeight: 600,
            fontSize: 13,
            cursor: 'pointer',
            transition: 'background 0.2s',
          }}
        >
          {keySaved ? '✓ Saved' : 'Apply Key'}
        </button>
        {settings.apiKey && !keySaved && <Note>Key applied ✓</Note>}
      </Section>

      {/* ── Model ─────────────────────────────────────────────────── */}
      <Section title="Model">
        {isOpenRouter && !settings.apiKey ? (
          <div style={{
            padding: '6px 8px',
            background: '#374151',
            border: '1px solid #4B5563',
            borderRadius: 4,
            color: '#6B7280',
            fontSize: 13,
          }}>
            Enter API key to load models
          </div>
        ) : isOpenRouter && fetchingOrModels ? (
          <div style={{
            padding: '6px 8px',
            background: '#374151',
            border: '1px solid #4B5563',
            borderRadius: 4,
            color: '#9CA3AF',
            fontSize: 13,
          }}>
            Fetching models…
          </div>
        ) : (
          <select
            value={settings.model}
            onChange={e => set('model', e.target.value)}
            style={sel}
          >
            {(isOpenRouter ? orModels : fixedModels).map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        )}
        {isOpenRouter && !fetchingOrModels && orModels.length > 0 && (
          <Note>{orModels.length} free models</Note>
        )}
      </Section>

      {/* ── Paper Domain ─────────────────────────────────────────── */}
      <Section title="Paper Domain">
        <select
          value={settings.domain ?? 'auto'}
          onChange={e => set('domain', e.target.value)}
          style={sel}
        >
          <option value="auto">Auto-detect</option>
          <option value="math">Math / STEM</option>
          <option value="english">English / Humanities</option>
        </select>
        <Note>
          {settings.domain === 'math'    && 'Regex extraction: theorems, lemmas, proofs'}
          {settings.domain === 'english' && 'LLM extraction: claims, concepts, evidence'}
          {(!settings.domain || settings.domain === 'auto') && 'Detected from document content'}
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
          <input
            type="checkbox"
            checked={linked}
            onChange={e => setLinked(e.target.checked)}
          />
          Link all parameters
        </label>
        <Slider
          label="Expertise"
          value={settings.readerExpertise}
          onChange={handleExpertise}
        />
        <Slider
          label="Scientific"
          value={settings.scientificKnowledge}
          onChange={v => !linked && set('scientificKnowledge', v)}
          disabled={linked}
        />
        <Slider
          label="Language"
          value={settings.languageComplexity}
          onChange={v => !linked && set('languageComplexity', v)}
          disabled={linked}
        />
      </div>
    </div>
  );
}

// ── sub-components ────────────────────────────────────────────────────

function Section({ title, children }) {
  return (
    <div>
      <label style={{
        display: 'block',
        fontSize: 11,
        color: '#9CA3AF',
        marginBottom: 5,
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
      }}>
        {title}
      </label>
      {children}
    </div>
  );
}

function Note({ children }) {
  return (
    <div style={{ color: '#6B7280', fontSize: 11, marginTop: 4 }}>
      {children}
    </div>
  );
}

function Slider({ label, value, onChange, disabled }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        fontSize: 12, color: disabled ? '#4B5563' : '#9CA3AF', marginBottom: 4,
      }}>
        <span>{label}</span>
        <span>{value.toFixed(2)}</span>
      </div>
      <input
        type="range"
        min={0} max={1} step={0.05}
        value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        disabled={disabled}
        style={{ width: '100%', accentColor: '#3B82F6', opacity: disabled ? 0.4 : 1 }}
      />
    </div>
  );
}

// ── shared styles ─────────────────────────────────────────────────────

const sidebarStyle = {
  width: 284,
  minWidth: 284,
  background: '#1F2937',
  borderRight: '1px solid #374151',
  overflowY: 'auto',
  padding: '16px 14px',
  display: 'flex',
  flexDirection: 'column',
  gap: 16,
};

const sel = {
  width: '100%',
  background: '#374151',
  border: '1px solid #4B5563',
  borderRadius: 4,
  color: '#F9FAFB',
  padding: '6px 28px 6px 8px',
  outline: 'none',
  cursor: 'pointer',
  // suppress OS-native chrome so both dropdowns look identical
  appearance: 'none',
  WebkitAppearance: 'none',
  backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%239CA3AF'/%3E%3C/svg%3E\")",
  backgroundRepeat: 'no-repeat',
  backgroundPosition: 'right 9px center',
};

const inp = {
  width: '100%',
  background: '#374151',
  border: '1px solid #4B5563',
  borderRadius: 4,
  color: '#F9FAFB',
  padding: '6px 8px',
  outline: 'none',
};
