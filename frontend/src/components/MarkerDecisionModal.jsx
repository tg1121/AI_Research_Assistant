import { useState } from 'react';
import { submitMarkerDecision } from '../api';

export default function MarkerDecisionModal({ paperId, adminMode, onDone }) {
  const [datalabKey, setDatalabKey] = useState('');
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState(null);

  const decide = async (useMarker) => {
    setLoading(true);
    setError(null);
    try {
      await submitMarkerDecision(paperId, useMarker, useMarker ? datalabKey : null);
      onDone();
    } catch (e) {
      setError(e.message);
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        background: '#1F2937', border: '1px solid #374151', borderRadius: 12,
        padding: 28, width: 420, maxWidth: '90vw',
      }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: '#F9FAFB', marginBottom: 8 }}>
          ∑ Math-heavy paper detected
        </div>
        <div style={{ fontSize: 13, color: '#9CA3AF', marginBottom: 20, lineHeight: 1.6 }}>
          This paper contains theorems, proofs, or equations. Re-parsing with{' '}
          <strong style={{ color: '#93C5FD' }}>Marker</strong> will extract LaTeX
          accurately and improve the knowledge graph and synthesis quality.
        </div>

        {!adminMode && (
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 12, color: '#9CA3AF', display: 'block', marginBottom: 6 }}>
              Datalab API key (leave blank to skip Marker)
            </label>
            <input
              type="password"
              value={datalabKey}
              onChange={e => setDatalabKey(e.target.value)}
              placeholder="dl-…"
              style={{
                width: '100%', background: '#111827', border: '1px solid #374151',
                borderRadius: 6, color: '#F9FAFB', padding: '8px 10px', fontSize: 13,
                outline: 'none', boxSizing: 'border-box',
              }}
              onFocus={e => e.target.style.borderColor = '#3B82F6'}
              onBlur={e => e.target.style.borderColor = '#374151'}
            />
          </div>
        )}

        {adminMode && (
          <div style={{
            marginBottom: 20, padding: '8px 12px', background: '#1A2E1A',
            borderRadius: 6, fontSize: 12, color: '#86EFAC',
          }}>
            Local Marker is available on this machine — no API key needed.
          </div>
        )}

        {error && (
          <div style={{ color: '#EF4444', fontSize: 12, marginBottom: 12 }}>{error}</div>
        )}

        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={() => decide(true)}
            disabled={loading || (!adminMode && !datalabKey.trim())}
            style={{
              flex: 1, padding: '10px 0', borderRadius: 7, border: 'none',
              background: (!adminMode && !datalabKey.trim()) ? '#374151' : '#2563EB',
              color: (!adminMode && !datalabKey.trim()) ? '#6B7280' : '#fff',
              fontWeight: 600, fontSize: 13, cursor: loading ? 'wait' : 'pointer',
            }}
          >
            {adminMode ? 'Parse with local Marker' : 'Parse with Marker'}
          </button>
          <button
            onClick={() => decide(false)}
            disabled={loading}
            style={{
              flex: 1, padding: '10px 0', borderRadius: 7,
              border: '1px solid #374151', background: 'none',
              color: '#9CA3AF', fontWeight: 600, fontSize: 13, cursor: 'pointer',
            }}
          >
            Continue with PyMuPDF
          </button>
        </div>
      </div>
    </div>
  );
}
