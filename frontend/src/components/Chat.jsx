import { useState, useRef, useEffect } from 'react';
import { sendChat } from '../api';
import Md from './Md';

// Fully controlled: messages live in App state so the conversation persists
// across tab switches. chatPaperId is the stable backend anchor (first done
// paper); allPaperIds passes every done paper to the agent.
export default function Chat({ chatPaperId, allPaperIds = [], messages, onMessages, model, apiKey, readerParams, onToggle, onExpand, onClear, expanded = false }) {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const ready = !!chatPaperId;

  const send = async () => {
    const q = input.trim();
    if (!q || loading || !ready) return;
    setInput('');
    setLoading(true);
    setError(null);

    try {
      const res = await sendChat(chatPaperId, q, readerParams, model, apiKey, allPaperIds, messages);
      onMessages(res.messages);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      background: '#111827',
      minHeight: 0,
      height: '100%',
    }}>
      <div style={{
        padding: '8px 16px',
        background: '#1F2937',
        borderBottom: '1px solid #374151',
        fontSize: 13,
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}>
        💬 Chat
        {allPaperIds.length > 1 && (
          <span style={{
            background: '#1E3A5F',
            color: '#93C5FD',
            fontSize: 11,
            padding: '2px 8px',
            borderRadius: 10,
          }}>
            {allPaperIds.length} papers
          </span>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 2 }}>
          {onClear && messages.length > 0 && (
            <button
              onClick={onClear}
              title="Clear chat history"
              style={{ background: 'none', border: 'none', color: '#4B5563', cursor: 'pointer', fontSize: 13, padding: '0 6px', lineHeight: 1 }}
              onMouseEnter={e => e.target.style.color = '#EF4444'}
              onMouseLeave={e => e.target.style.color = '#4B5563'}
            >🗑</button>
          )}
          {onExpand && (
            <button
              onClick={onExpand}
              title={expanded ? 'Shrink chat' : 'Expand chat'}
              style={{ background: 'none', border: 'none', color: '#4B5563', cursor: 'pointer', fontSize: 14, padding: '0 6px', lineHeight: 1 }}
              onMouseEnter={e => e.target.style.color = '#9CA3AF'}
              onMouseLeave={e => e.target.style.color = '#4B5563'}
            >{expanded ? '⊡' : '⤢'}</button>
          )}
          {onToggle && (
            <button
              onClick={onToggle}
              title="Close chat"
              style={{ background: 'none', border: 'none', color: '#4B5563', cursor: 'pointer', fontSize: 18, padding: '0 4px', lineHeight: 1 }}
              onMouseEnter={e => e.target.style.color = '#9CA3AF'}
              onMouseLeave={e => e.target.style.color = '#4B5563'}
            >×</button>
          )}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {!ready && (
          <div style={{ color: '#4B5563', textAlign: 'center', marginTop: 24, fontSize: 13 }}>
            Upload and process a paper to start chatting…
          </div>
        )}

        {ready && messages.length === 0 && !loading && (
          <div style={{ color: '#4B5563', textAlign: 'center', marginTop: 24, fontSize: 13 }}>
            {allPaperIds.length > 1
              ? `Ask anything across all ${allPaperIds.length} papers…`
              : 'Ask anything about the paper…'}
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              marginBottom: 10,
              display: 'flex',
              justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
            }}
          >
            <div style={{
              maxWidth: '90%',
              padding: '8px 12px',
              borderRadius: 10,
              background: m.role === 'user' ? '#1D4ED8' : '#1F2937',
              color: '#F9FAFB',
              fontSize: 13,
              wordBreak: 'break-word',
            }}>
              {m.role === 'user'
                ? <span style={{ whiteSpace: 'pre-wrap' }}>{m.content}</span>
                : <Md>{m.content}</Md>
              }
            </div>
          </div>
        ))}

        {loading && (
          <div style={{ color: '#6B7280', fontSize: 12, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ animation: 'spin 1s linear infinite', display: 'inline-block' }}>⏳</span>
            Agent thinking…
          </div>
        )}

        {error && (
          <div style={{ color: '#EF4444', fontSize: 12, marginBottom: 8 }}>
            Error: {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div style={{
        padding: '8px 12px',
        borderTop: '1px solid #374151',
        display: 'flex',
        gap: 8,
        flexShrink: 0,
      }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={ready ? 'Ask a question… (Enter to send)' : 'No paper loaded…'}
          disabled={!ready}
          rows={2}
          style={{
            flex: 1,
            background: '#1F2937',
            border: '1px solid #374151',
            borderRadius: 6,
            color: ready ? '#F9FAFB' : '#4B5563',
            padding: '8px 10px',
            resize: 'none',
            fontSize: 13,
            outline: 'none',
          }}
          onFocus={e => { if (ready) e.target.style.borderColor = '#3B82F6'; }}
          onBlur={e => e.target.style.borderColor = '#374151'}
        />
        <button
          onClick={send}
          disabled={loading || !input.trim() || !ready}
          style={{
            background: (loading || !input.trim() || !ready) ? '#374151' : '#2563EB',
            color: (loading || !input.trim() || !ready) ? '#6B7280' : '#fff',
            border: 'none',
            borderRadius: 6,
            padding: '0 14px',
            fontWeight: 600,
            fontSize: 13,
            transition: 'background 0.15s',
          }}
        >
          Send
        </button>
      </div>
    </div>
  );
}
