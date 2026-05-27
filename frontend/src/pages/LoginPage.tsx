import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import { useAuthStore } from '../store/auth';

const DEMO_ACCOUNTS = [
  { email: 'demo@acme.com', password: 'demo123', org: 'Acme Corp' },
  { email: 'analyst@globex.com', password: 'demo123', org: 'Globex Corp' },
  { email: 'admin@initech.com', password: 'demo123', org: 'Initech Ltd' },
];

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { setTokens, setUser } = useAuthStore();
  const navigate = useNavigate();

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const { data } = await api.post('/auth/token/', { email, password });
      setTokens(data.access, data.refresh);
      const me = await api.get('/me/');
      setUser(me.data);
      navigate('/');
    } catch {
      setError('Invalid email or password.');
    } finally {
      setLoading(false);
    }
  }

  function fillDemo(account: typeof DEMO_ACCOUNTS[0]) {
    setEmail(account.email);
    setPassword(account.password);
    setError('');
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <p className="login-eyebrow">Analyst Portal</p>
        <h1 className="login-title">BreatheESG</h1>
        <p className="login-subtitle">
          ESG data ingestion and review platform
        </p>

        <form className="login-form" onSubmit={handleLogin}>
          <div className="form-group">
            <label className="form-label" htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              className="form-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              autoComplete="email"
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              autoComplete="current-password"
              required
            />
          </div>
          {error && <div className="login-error">{error}</div>}
          <button
            id="btn-login"
            type="submit"
            className="btn btn-primary btn-lg w-full"
            disabled={loading}
          >
            {loading ? <span className="spinner" /> : null}
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <div className="demo-creds">
          <p className="demo-creds-title">Demo accounts (click to fill)</p>
          {DEMO_ACCOUNTS.map((a) => (
            <div
              key={a.email}
              className="demo-cred-row"
              onClick={() => fillDemo(a)}
              title={`Login as ${a.org}`}
            >
              <span>{a.email}</span>
              <span style={{ color: 'var(--color-ink-tertiary)', fontSize: '11px' }}>{a.org}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
