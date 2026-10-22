import {StrictMode, useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {createBetaClient} from '../src/beta/betaClient.js';
import './workspace.css';

export default function WorkspaceStaging() {
  const [client] = useState(() => createBetaClient());
  const [user, setUser] = useState(null), [ready, setReady] = useState(false);
  const [items, setItems] = useState([]), [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false), [loaded, setLoaded] = useState(false);
  const [uncertain, setUncertain] = useState(false), [notice, setNotice] = useState('Checking availability…');
  const flight = useRef(false), live = useRef(true);
  async function refresh() {
    const list = await client.workspaces();
    if (live.current) { setItems(list); setLoaded(true); setUncertain(false); }
  }
  async function run(operation) {
    if (flight.current) return;
    flight.current = true; setBusy(true); setNotice('');
    try { await operation(); }
    catch (error) {
      if (!live.current) return;
      if (error.reconciliationRequired) setUncertain(true);
      setNotice(error.reconciliationRequired
        ? 'The save result is uncertain. Refresh the workspace list before creating again; check for your previous name.'
        : 'Request unavailable (' + (error.code || 'SERVICE_UNAVAILABLE') + ').');
      if (!client.hasSession()) { setUser(null); setItems([]); setSelected(null); setLoaded(false); }
    } finally { flight.current = false; if (live.current) setBusy(false); }
  }
  useEffect(() => {
    let active = true; live.current = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      const returning = new URLSearchParams(location.search).get('auth') === 'google';
      if (returning) history.replaceState(null, '', '/login/');
      try {
        const providers = await client.providers();
        if (!active) return;
        setReady(providers.googleConfigured === true);
        setNotice('Google sign-in and saved workspace metadata staging.');
        if (returning) {
          const me = await client.exchangeGoogle();
          if (!active) return;
          setUser(me);
          await refresh();
        }
      } catch (error) {
        if (active) {
          if (!client.hasSession()) setUser(null);
          setNotice('Sign-in or workspace unavailable (' + (error.code || 'SERVICE_UNAVAILABLE') + ').');
        }
      }
    });
    return () => { active = false; live.current = false; client.clear(); };
    // One memory-only client per mounted account; cancelled StrictMode setup does no exchange.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client]);
  async function logout() {
    try { await client.logout(); setNotice('Signed out; server session revoked.'); }
    catch { setNotice('Local session cleared. Server revocation was not confirmed.'); }
    finally { setUser(null); setItems([]); setSelected(null); setLoaded(false); setUncertain(false); }
  }
  return <main><a href="/">RIKSORA · Backtest Lab</a><section>
    <p>PRIVATE STAGING</p><h1>{user ? 'Your workspaces' : 'Sign in'}</h1>
    <p role="status" aria-live="polite">{notice}</p>
    {user ? <>
      <p>Signed in as <strong>{user.email}</strong></p>
      <button disabled={busy} onClick={() => run(logout)}>Sign out</button>
      <button disabled={busy} onClick={() => run(refresh)}>Refresh workspaces</button>
      {loaded && !items.length && <p>No saved workspaces yet.</p>}
      <ul>{items.map(ws => <li key={ws.id}><button disabled={busy} onClick={() => setSelected(ws)}>{ws.name}</button> <span>{ws.role === 'OWNER' ? 'Workspace owner' : 'Workspace member'}</span></li>)}</ul>
      <form onSubmit={event => {
        event.preventDefault(); const form = event.currentTarget;
        const name = String(new FormData(form).get('name') || '').trim();
        if (!name || !loaded || uncertain || busy) return;
        setUncertain(true);
        void run(async () => { await client.createWorkspace(name); await refresh(); form.reset(); });
      }}>
        <label>Workspace name<input name="name" required maxLength={128} disabled={busy || !loaded || uncertain}/></label>
        <button disabled={busy || !loaded || uncertain}>Create workspace</button>
      </form>
      {selected && <article><h2>{selected.name}</h2><p>This workspace is saved on the server. Trading Sessions and real-data replay are not enabled in this release.</p></article>}
    </> : ready ? <a href={client.googleStart()}>Continue with Google</a> : <p>Sign-in unavailable.</p>}
    <p>Backtest, statistics, payments and real market data are not enabled here. Workspace ownership does not grant application administration. Refreshing this page requires signing in again; saved workspaces remain on the server.</p>
  </section></main>;
}

createRoot(document.getElementById('root')).render(<StrictMode><WorkspaceStaging/></StrictMode>);
