import { useEffect, useRef, useState, useCallback } from 'react';

const NODE_COLORS = {
  // math
  definition:   '#7F77DD',
  theorem:      '#1D9E75',
  lemma:        '#BA7517',
  proof:        '#888780',
  corollary:    '#D85A30',
  section:      '#378ADD',
  proposition:  '#1D9E75',
  equation:     '#44AADD',
  remark:       '#aaaaaa',
  example:      '#BA7517',
  // english
  claim:        '#E879A0',
  concept:      '#A78BFA',
  evidence:     '#34D399',
  critic_view:  '#FB923C',
  primary_text: '#60A5FA',
  // shared
  external:     '#FF8C00',
};

const EDGE_COLORS = {
  regex:      '#1D9E75',
  positional: '#BA7517',
  llm:        '#A78BFA',
  section:    '#223355',
};

const MATH_LEGEND = [
  { color: '#7F77DD', label: 'Definition' },
  { color: '#1D9E75', label: 'Theorem/Prop' },
  { color: '#BA7517', label: 'Lemma' },
  { color: '#888780', label: 'Proof' },
  { color: '#D85A30', label: 'Corollary' },
  { color: '#378ADD', label: 'Section' },
];

const ENGLISH_LEGEND = [
  { color: '#378ADD', label: 'Section' },
  { color: '#E879A0', label: 'Claim' },
  { color: '#A78BFA', label: 'Concept' },
  { color: '#34D399', label: 'Evidence' },
  { color: '#FB923C', label: 'Critic view' },
  { color: '#60A5FA', label: 'Primary text' },
  { color: '#FF8C00', label: 'External refs' },
];

export default function KnowledgeGraph({ graphData, domain = 'math', sectionPageMap = {}, onNodeClick }) {
  const [collapsed, setCollapsed]     = useState(false);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [mousePos, setMousePos]       = useState({ x: 0, y: 0 });
  const containerRef = useRef(null);
  const networkRef   = useRef(null);

  const handleMouseMove = useCallback((e) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  }, []);

  useEffect(() => {
    if (!graphData || collapsed) return;
    const el = containerRef.current;
    if (!el) return;

    let isMounted = true;

    import('vis-network').then(({ Network }) => {
      import('vis-data').then(({ DataSet }) => {
        if (!isMounted || !containerRef.current) return;

        const nodes = new DataSet(
          Object.values(graphData.nodes).map(n => ({
            id:    n.node_id,
            label: n.label.substring(0, 28),
            color: NODE_COLORS[n.node_type] || '#888',
            size:  n.node_type === 'section' ? 18 : Math.max(10, 8 + n.in_degree * 4),
            // no `title` — we handle hover ourselves
          }))
        );

        const edges = new DataSet(
          graphData.edges.map((e, i) => {
            const isSection = e.source === 'section';
            return {
              id:    i,
              from:  e.from_id,
              to:    e.to_id,
              color: { color: EDGE_COLORS[e.source] || '#aaa', opacity: isSection ? 0.45 : 0.85 },
              arrows: isSection ? 'to' : 'to',
              dashes: e.source === 'llm' ? true : isSection ? [4, 4] : false,
              width:  isSection ? 1.0 : 1.5,
            };
          })
        );

        const options = {
          physics: {
            stabilization: { iterations: 300, fit: true },
            barnesHut: {
              gravitationalConstant: -6000,
              centralGravity:        0.05,
              springLength:          160,
              springConstant:        0.03,
              damping:               0.15,
              avoidOverlap:          0.8,
            },
          },
          interaction: { hover: true, navigationButtons: true, tooltipDelay: 99999 },
          nodes: {
            font:        { color: '#eee', size: 11, strokeWidth: 2, strokeColor: '#111827' },
            shape:       'dot',
            borderWidth: 0,
          },
          edges:  { smooth: { type: 'dynamic' }, selectionWidth: 3 },
          layout: { improvedLayout: true },
        };

        if (networkRef.current) networkRef.current.destroy();
        const network = new Network(containerRef.current, { nodes, edges }, options);
        networkRef.current = network;

        network.on('hoverNode', ({ node }) => {
          const n = graphData.nodes[node];
          if (n) setHoveredNode(n);
        });
        network.on('blurNode', () => setHoveredNode(null));
        network.on('click', ({ nodes }) => {
          if (nodes.length === 1) {
            const n = graphData.nodes[nodes[0]];
            if (n && onNodeClick) onNodeClick(n.section_id);
          }
        });
      });
    });

    return () => {
      isMounted = false;
      if (networkRef.current) {
        networkRef.current.destroy();
        networkRef.current = null;
      }
    };
  }, [graphData, collapsed]);

  if (!graphData) return null;

  const isEnglish = domain !== 'math';
  const LEGEND    = isEnglish ? ENGLISH_LEGEND : MATH_LEGEND;
  const nNodes    = Object.keys(graphData.nodes).length;
  const nEdges    = graphData.edges.length;
  const nSemantic = isEnglish
    ? Object.values(graphData.nodes).filter(n => ['claim','concept','evidence','critic_view','primary_text'].includes(n.node_type)).length
    : Object.values(graphData.nodes).filter(n => n.node_type === 'proof').length;

  // keep tooltip inside the 380px container
  const TIP_W = 260;
  const tipX  = mousePos.x + 14 + TIP_W > (containerRef.current?.clientWidth ?? 600)
    ? mousePos.x - TIP_W - 8
    : mousePos.x + 14;
  const tipY  = Math.min(mousePos.y + 10, 290);

  return (
    <div style={{ borderBottom: '1px solid #374151', flexShrink: 0 }}>
      {/* header */}
      <div
        onClick={() => setCollapsed(c => !c)}
        style={{
          padding: '8px 16px', cursor: 'pointer',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          background: '#1F2937', userSelect: 'none', fontSize: 13,
        }}
      >
        <span>
          🕸️ Knowledge Graph &nbsp;
          <span style={{ color: '#6B7280' }}>({nNodes} nodes · {nEdges} edges · {nSemantic} {isEnglish ? 'semantic' : 'proofs'})</span>
        </span>
        <span style={{ color: '#6B7280' }}>{collapsed ? '▼' : '▲'}</span>
      </div>

      {!collapsed && (
        <div style={{ position: 'relative' }}>
          {/* canvas */}
          <div
            ref={containerRef}
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setHoveredNode(null)}
            style={{ height: 380, background: '#111827' }}
          />

          {/* legend */}
          <div style={{
            position: 'absolute', top: 8, left: 8,
            background: 'rgba(0,0,0,0.75)', borderRadius: 6,
            padding: '6px 10px', fontSize: 11, lineHeight: 1.8,
            pointerEvents: 'none',
          }}>
            {LEGEND.map(({ color, label }) => (
              <span key={label} style={{ marginRight: 10 }}>
                <span style={{ color }}>■</span> {label}
              </span>
            ))}
          </div>

          {/* hover tooltip */}
          {hoveredNode && (
            <div style={{
              position:     'absolute',
              left:         tipX,
              top:          tipY,
              width:        TIP_W,
              background:   '#1F2937',
              border:       `1px solid ${NODE_COLORS[hoveredNode.node_type] || '#555'}`,
              borderRadius: 6,
              padding:      '8px 10px',
              fontSize:     11,
              lineHeight:   1.6,
              pointerEvents:'none',
              zIndex:       10,
              boxShadow:    '0 4px 12px rgba(0,0,0,0.5)',
            }}>
              <div style={{ fontWeight: 700, color: NODE_COLORS[hoveredNode.node_type] || '#eee', marginBottom: 4 }}>
                {hoveredNode.label}
              </div>
              <div style={{ color: '#9CA3AF', marginBottom: 2 }}>
                {hoveredNode.node_type}
                {hoveredNode.proof_type && ` · ${hoveredNode.proof_type}`}
                {' · '}in-degree: {hoveredNode.in_degree}
              </div>
              {hoveredNode.raw_text && (
                <div style={{ color: '#D1D5DB', marginTop: 6, fontSize: 10, lineHeight: 1.5 }}>
                  {hoveredNode.raw_text.trim().substring(0, 220)}
                  {hoveredNode.raw_text.length > 220 ? '…' : ''}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
