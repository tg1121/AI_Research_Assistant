import { useRef } from 'react';

const STATUS_ICON = { processing: '⏳', error: '❌', done: '' };

export default function TabBar({ tabs, activeIdx, onSelect, onClose, onUpload }) {
  const fileRef = useRef(null);

  return (
    <div style={{
      display: 'flex',
      alignItems: 'flex-end',
      overflowX: 'auto',
      flex: 1,
      gap: 2,
      padding: '6px 4px 0',
      minHeight: 38,
    }}>
      {tabs.map((tab, i) => {
        const active = i === activeIdx;
        return (
          <div
            key={tab.paper_id}
            onClick={() => onSelect(i)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              padding: '4px 10px 4px 10px',
              borderRadius: '6px 6px 0 0',
              background: active ? '#111827' : '#374151',
              border: active ? '1px solid #4B5563' : '1px solid transparent',
              borderBottom: active ? '1px solid #111827' : 'none',
              cursor: 'pointer',
              flexShrink: 0,
              maxWidth: 200,
              userSelect: 'none',
            }}
          >
            <span style={{
              color: active ? '#F9FAFB' : '#9CA3AF',
              fontSize: 12,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              maxWidth: 130,
            }}>
              {STATUS_ICON[tab.status]}{STATUS_ICON[tab.status] ? ' ' : ''}
              {tab.paper_id}
            </span>
            <button
              onClick={e => { e.stopPropagation(); onClose(i); }}
              style={{
                background: 'none',
                border: 'none',
                color: '#6B7280',
                padding: '0 2px',
                fontSize: 11,
                lineHeight: 1,
                opacity: 0.7,
                flexShrink: 0,
              }}
              title="Close tab"
            >
              ✕
            </button>
          </div>
        );
      })}

      <button
        onClick={() => fileRef.current?.click()}
        title="Upload new paper"
        style={{
          padding: '4px 12px',
          background: 'none',
          border: '1px dashed #4B5563',
          borderRadius: '6px 6px 0 0',
          color: '#9CA3AF',
          fontSize: 18,
          lineHeight: 1,
          flexShrink: 0,
          alignSelf: 'flex-start',
          marginTop: 2,
        }}
      >
        +
      </button>

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
