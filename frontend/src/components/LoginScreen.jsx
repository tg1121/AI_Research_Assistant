import { useState } from 'react';
import { login, signup } from '../api';

export default function LoginScreen({ onLogin }) {
  const [mode, setMode]         = useState('signin'); // 'signin' | 'signup'
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState(null);
  const [loading, setLoading]   = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  const isSignup = mode === 'signup';

  const switchMode = (next) => {
    setMode(next);
    setError(null);
    setConfirmed(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (isSignup) {
        const data = await signup(email, password);
        if (data.confirm_email) {
          setConfirmed(true);
        } else {
          onLogin(data.access_token, { id: data.user_id, email: data.email });
        }
      } else {
        const data = await login(email, password);
        onLogin(data.access_token, { id: data.user_id, email: data.email });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh', background: '#111827',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#1F2937', border: '1px solid #374151', borderRadius: 14,
        padding: '40px 36px', width: 360, maxWidth: '90vw',
      }}>
        <div style={{ fontSize: 11, color: '#6B7280', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 10 }}>
          Research Paper Assistant
        </div>

        {/* Mode tabs */}
        <div style={{ display: 'flex', gap: 0, marginBottom: 28, borderBottom: '1px solid #374151' }}>
          {['signin', 'signup'].map(m => (
            <button
              key={m}
              onClick={() => switchMode(m)}
              style={{
                flex: 1, padding: '8px 0', border: 'none', background: 'none',
                color: mode === m ? '#F9FAFB' : '#6B7280',
                fontWeight: mode === m ? 700 : 400,
                fontSize: 14, cursor: 'pointer',
                borderBottom: mode === m ? '2px solid #3B82F6' : '2px solid transparent',
                transition: 'color 0.15s',
              }}
            >
              {m === 'signin' ? 'Sign in' : 'Create account'}
            </button>
          ))}
        </div>

        {confirmed ? (
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 28, marginBottom: 12 }}>📬</div>
            <div style={{ color: '#F9FAFB', fontWeight: 600, marginBottom: 8 }}>Check your email</div>
            <div style={{ color: '#9CA3AF', fontSize: 13, lineHeight: 1.6, marginBottom: 24 }}>
              We sent a confirmation link to <strong style={{ color: '#F3F4F6' }}>{email}</strong>.
              Click it to activate your account, then sign in.
            </div>
            <button
              onClick={() => switchMode('signin')}
              style={{ color: '#3B82F6', background: 'none', border: 'none', fontSize: 13, cursor: 'pointer', textDecoration: 'underline' }}
            >
              Back to sign in
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 12, color: '#9CA3AF', display: 'block', marginBottom: 6 }}>
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                autoFocus
                style={inputStyle}
                onFocus={e => e.target.style.borderColor = '#3B82F6'}
                onBlur={e => e.target.style.borderColor = '#374151'}
              />
            </div>

            <div style={{ marginBottom: 24 }}>
              <label style={{ fontSize: 12, color: '#9CA3AF', display: 'block', marginBottom: 6 }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                minLength={isSignup ? 8 : undefined}
                style={inputStyle}
                onFocus={e => e.target.style.borderColor = '#3B82F6'}
                onBlur={e => e.target.style.borderColor = '#374151'}
              />
              {isSignup && (
                <div style={{ fontSize: 11, color: '#6B7280', marginTop: 5 }}>Minimum 8 characters</div>
              )}
            </div>

            {error && (
              <div style={{ color: '#EF4444', fontSize: 12, marginBottom: 16 }}>{error}</div>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                width: '100%', padding: '11px 0', borderRadius: 8, border: 'none',
                background: loading ? '#1D4ED8' : '#2563EB',
                color: '#fff', fontWeight: 600, fontSize: 14,
                cursor: loading ? 'wait' : 'pointer',
              }}
            >
              {loading
                ? (isSignup ? 'Creating account…' : 'Signing in…')
                : (isSignup ? 'Create account' : 'Sign in')}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

const inputStyle = {
  width: '100%', background: '#111827', border: '1px solid #374151',
  borderRadius: 7, color: '#F9FAFB', padding: '9px 12px', fontSize: 13,
  outline: 'none', boxSizing: 'border-box', transition: 'border-color 0.15s',
};
