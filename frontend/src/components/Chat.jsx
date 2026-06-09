import { useState, useRef, useEffect } from 'react';
import { sendChat } from '../api';
import Md from './Md';

export default function Chat({ paperId, model, apiKey, readerParams }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);

  // Reset chat when paper changes
  useEffect(() => {
    setMessages([]);
    setInput('');
    setError(null);
  }, [paperId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const send = async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput('');
    setLoading(true);
    setError(null);

    try {
      const res = await sendChat(paperId, q, readerParams, model, apiKey);
      setMessages(res.messages);
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
    <div style={{ flex: '1 0 350px', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{
        padding: '8px 16px',
        background: '#1F2937',
        borderBottom: '1px solid #374151',
        fontSize: 13,
        flexShrink: 0,
      }}>
        💬 Chat
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {messages.length === 0 && !loading && (
          <div style={{ color: '#4B5563', textAlign: 'center', marginTop: 24, fontSize: 13 }}>
            Ask anything about the paper…
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
              maxWidth: '82%',
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
          placeholder="Ask a question… (Enter to send, Shift+Enter for newline)"
          rows={2}
          style={{
            flex: 1,
            background: '#1F2937',
            border: '1px solid #374151',
            borderRadius: 6,
            color: '#F9FAFB',
            padding: '8px 10px',
            resize: 'none',
            fontSize: 13,
            outline: 'none',
          }}
          onFocus={e => e.target.style.borderColor = '#3B82F6'}
          onBlur={e => e.target.style.borderColor = '#374151'}
        />
        <button
          onClick={send}
          disabled={loading || !input.trim()}
          style={{
            background: loading || !input.trim() ? '#374151' : '#2563EB',
            color: loading || !input.trim() ? '#6B7280' : '#fff',
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
