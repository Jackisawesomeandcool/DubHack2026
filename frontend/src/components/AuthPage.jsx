import { useEffect, useState } from 'react';
import FashionCanvas from './FashionCanvas.jsx';
import { randomFit } from '../lib/api.js';
import { withPositions } from '../lib/haul.js';
import { USERNAME_RE, cleanUsername, continueAsGuest, go, loadUser, logIn, signUp } from '../lib/session.js';

const COPY = {
  login: {
    title: 'Welcome back',
    sub: 'Log in to pick up your hauls.',
    submit: 'Log in',
    headline: 'Build outfits from real stores.',
    tagline: 'Mix pieces, swap in dupes, share the haul.',
  },
  signup: {
    title: 'Create your account',
    sub: 'It takes about a minute.',
    submit: 'Continue',
    headline: 'Save your hauls. Share them in one link.',
    tagline: 'Keep several hauls going at once and come back to them anytime.',
  },
};

// Log in and sign up share one screen: a live outfit board on the left, the
// form on the right. Accounts are stored by the backend (see lib/session.js).
export default function AuthPage({ mode = 'login' }) {
  const copy = COPY[mode];
  const isSignup = mode === 'signup';
  const known = loadUser();

  const [firstName, setFirstName] = useState('');
  const [username, setUsername] = useState('');
  // Sign up: the email field. Log in: "email or username".
  const [email, setEmail] = useState(isSignup ? '' : known?.email || known?.username || '');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState([]);
  const [previewLoading, setPreviewLoading] = useState(true);

  // A real random haul makes the left panel feel like the product, not a poster.
  useEffect(() => {
    let alive = true;
    randomFit()
      .then(({ items }) => alive && setPreview(withPositions(items)))
      .catch(() => {})
      .finally(() => alive && setPreviewLoading(false));
    return () => { alive = false; };
  }, []);

  async function submit(e) {
    e.preventDefault();
    if (busy) return;
    const id = email.trim();
    if (isSignup) {
      if (!firstName.trim()) return setError('Enter your first name.');
      if (!USERNAME_RE.test(cleanUsername(username))) return setError('Usernames are 3–20 characters: letters, numbers, _ or .');
      if (!/^\S+@\S+\.\S+$/.test(id)) return setError('Enter a valid email.');
      if (password.length < 8) return setError('Password needs at least 8 characters.');
    } else {
      if (!id) return setError('Enter your email or username.');
      if (!password) return setError('Enter your password.');
    }
    setBusy(true);
    try {
      if (isSignup) await signUp({ firstName, username, email: id, password });
      else await logIn(id, password);
      go('/');
    } catch (err) {
      setError(err.message === 'Failed to fetch' ? 'Can\u2019t reach the server \u2014 is the backend running?' : err.message);
      setBusy(false);
    }
  }

  function guest(e) {
    e.preventDefault();
    continueAsGuest();
    go('/');
  }

  return (
    <main className="auth">
      <section className="auth__panel" aria-label="Haul preview">
        <div className="auth__brand">Haul</div>
        <div className="auth__board" aria-hidden="true">
          <FashionCanvas items={preview} fitKey="auth" loading={previewLoading} />
        </div>
        <div className="auth__pitch">
          <h2>{copy.headline}</h2>
          <p>{copy.tagline}</p>
        </div>
      </section>

      <section className="auth__side">
        <form className="auth__form" onSubmit={submit} noValidate>
          <div className="auth__head">
            <h1>{copy.title}</h1>
            <p>{copy.sub}</p>
          </div>


          {isSignup && (
            <div className="field__pair">
              <div className="field">
                <label htmlFor="auth-first">First name</label>
                <input
                  id="auth-first" type="text" autoComplete="given-name"
                  value={firstName} onChange={(e) => { setFirstName(e.target.value); setError(''); }}
                />
              </div>
              <div className="field">
                <label htmlFor="auth-user">Username</label>
                <div className="field__at">
                  <span aria-hidden="true">@</span>
                  <input
                    id="auth-user" type="text" autoComplete="username" autoCapitalize="none" spellCheck="false"
                    maxLength={21} aria-describedby="auth-user-hint"
                    value={username} onChange={(e) => { setUsername(e.target.value.replace(/^@+/, '')); setError(''); }}
                  />
                </div>
              </div>
              <small id="auth-user-hint" className="field__hint">Username: 3–20 letters, numbers, _ or .</small>
            </div>
          )}
          <div className="field">
            <label htmlFor="auth-email">{isSignup ? 'Email' : 'Email or username'}</label>
            <input
              id="auth-email" type={isSignup ? 'email' : 'text'} autoCapitalize="none" spellCheck="false"
              autoComplete={isSignup ? 'email' : 'username'} placeholder={isSignup ? 'you@uw.edu' : 'you@uw.edu or @username'}
              value={email} onChange={(e) => { setEmail(e.target.value); setError(''); }}
            />
          </div>
          <div className="field">
            <div className="field__row">
              <label htmlFor="auth-pw">Password</label>
              {!isSignup && <a href="#" onClick={(e) => e.preventDefault()}>Forgot?</a>}
            </div>
            <input
              id="auth-pw" type="password" autoComplete={isSignup ? 'new-password' : 'current-password'}
              aria-describedby={isSignup ? 'auth-pw-hint' : undefined}
              value={password} onChange={(e) => { setPassword(e.target.value); setError(''); }}
            />
            {isSignup && <small id="auth-pw-hint">At least 8 characters.</small>}
          </div>

          {error && <p className="auth__error" role="alert">{error}</p>}

          <button type="submit" className="auth__submit" disabled={busy}>{busy ? '\u2026' : copy.submit}</button>

          {isSignup ? (
            <p className="auth__switch">Already have an account? <a href="/login">Log in</a></p>
          ) : (
            <>
              <p className="auth__switch">New to Haul? <a href="/signup">Create an account</a></p>
              <p className="auth__guest">Just looking? <a href="/" onClick={guest}>Continue as guest</a></p>
            </>
          )}
        </form>
      </section>
    </main>
  );
}
