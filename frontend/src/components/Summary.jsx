import { useState } from 'react';
import Md from './Md';

const QUESTIONS = [
  ['Q1_problem',      '❓ What was broken?'],
  ['Q2_insight',      '💡 Key insight?'],
  ['Q3_mechanism',    '⚙️ How does it work?'],
  ['Q4_evidence',     '✅ Does it work?'],
  ['Q5_assumptions',  '🔍 Assumptions?'],
  ['Q6_implications', '🌐 Implications?'],
  ['Q7_limitations',  '⚠️ Limitations?'],
];

export default function Summary({ summaryData }) {
  const [collapsed, setCollapsed] = useState(false);
  const [arcsOpen, setArcsOpen] = useState(false);
  const [qsOpen, setQsOpen] = useState(true);
  const [chainOpen, setChainOpen] = useState(false);

  if (!summaryData?.holistic_summary) return null;
  const s = summaryData.holistic_summary;

  return (
    <div style={{ borderBottom: '1px solid #374151', flexShrink: 0 }}>
      <div
        onClick={() => setCollapsed(c => !c)}
        style={{
          padding: '8px 16px',
          cursor: 'pointer',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: '#1F2937',
          userSelect: 'none',
          fontSize: 13,
          position: 'sticky',
          top: 0,
          zIndex: 1,
        }}
      >
        <span>📖 Summary</span>
        <span style={{ color: '#6B7280' }}>{collapsed ? '▼' : '▲'}</span>
      </div>

      {!collapsed && (
        <div style={{ padding: 16 }}>
          {s.one_liner && (
            <div style={{ background: '#1E3A5F', color: '#93C5FD', padding: '10px 14px', borderRadius: 6, marginBottom: 14, fontSize: 13 }}>
              <Md>{s.one_liner}</Md>
            </div>
          )}

          <Collapsible open={arcsOpen} onToggle={() => setArcsOpen(o => !o)} label="Narrative Arcs">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 12 }}>Arc 1 — What it is</div>
                <Md style={{ color: '#D1D5DB', fontSize: 12 }}>{s.arc1}</Md>
              </div>
              <div>
                <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 12 }}>Arc 2 — What it means</div>
                <Md style={{ color: '#D1D5DB', fontSize: 12 }}>{s.arc2}</Md>
              </div>
            </div>
          </Collapsible>

          <Collapsible open={qsOpen} onToggle={() => setQsOpen(o => !o)} label="7 Questions">
            {QUESTIONS.map(([key, label]) =>
              s[key] ? (
                <div key={key} style={{ marginBottom: 12 }}>
                  <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 3 }}>{label}</div>
                  <Md style={{ color: '#D1D5DB', fontSize: 12 }}>{s[key]}</Md>
                </div>
              ) : null
            )}
          </Collapsible>

          {summaryData.mathematical_chain && (
            <Collapsible open={chainOpen} onToggle={() => setChainOpen(o => !o)} label="⛓ Math Chains">
              {summaryData.mathematical_chain.mathematical_story && (
                <Md style={{ color: '#D1D5DB', fontSize: 12, marginBottom: 12 }}>
                  {summaryData.mathematical_chain.mathematical_story}
                </Md>
              )}
              {(summaryData.mathematical_chain.chains || []).map(chain => (
                <div key={chain.chain_id} style={{
                  marginBottom: 12,
                  borderLeft: '2px solid #374151',
                  paddingLeft: 10,
                }}>
                  <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 4, color: '#93C5FD' }}>
                    {chain.name}
                  </div>
                  <Md style={{ color: '#D1D5DB', fontSize: 12, marginBottom: 6 }}>{chain.story}</Md>
                  {chain.equations?.length > 0 && (
                    <div style={{ background: '#111827', borderRadius: 4, padding: '6px 10px', marginBottom: 4 }}>
                      {chain.equations.map((eq, i) => (
                        <Md key={i} style={{ fontSize: 11, color: '#9CA3AF' }}>{`$$${eq}$$`}</Md>
                      ))}
                    </div>
                  )}
                  {chain.depends_on?.length > 0 && (
                    <div style={{ fontSize: 11, color: '#6B7280' }}>
                      Depends on: {chain.depends_on.join(', ')}
                    </div>
                  )}
                </div>
              ))}
            </Collapsible>
          )}
        </div>
      )}
    </div>
  );
}

function Collapsible({ open, onToggle, label, children }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div
        onClick={onToggle}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          cursor: 'pointer',
          color: '#9CA3AF',
          fontSize: 12,
          marginBottom: open ? 10 : 0,
          userSelect: 'none',
        }}
      >
        <span>{open ? '▼' : '▶'}</span>
        <span>{label}</span>
      </div>
      {open && children}
    </div>
  );
}
