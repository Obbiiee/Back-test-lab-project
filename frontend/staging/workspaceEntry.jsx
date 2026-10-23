import {StrictMode, Suspense, lazy, useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {createBetaClient} from '../src/beta/betaClient.js';
import '../src/tickAlpha/tickAlpha.css';
import '../src/beta/beta.css';
import AlphaBrand from '../src/tickAlpha/AlphaBrand.jsx';
import './workspace.css';
const BetaWorkspace = lazy(() => import('../src/beta/BetaWorkspace.jsx'));

export default function WorkspaceStaging() {
  const [client] = useState(() => createBetaClient());
  const [user, setUser] = useState(null), [ready, setReady] = useState(false);
  const [demo, setDemo] = useState(false);
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
        setDemo(providers.demoConfigured === true);
        setNotice(returning ? 'Finishing Google sign-in…' : '');
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
  async function logout(all = false) {
    try { await client.logout(all); setNotice('Signed out; server session revoked.'); }
    catch { setNotice('Local session cleared. Server revocation was not confirmed.'); }
    finally { setUser(null); setItems([]); setSelected(null); setLoaded(false); setUncertain(false); }
  }
  return <main className={`google-workspace beta-account${demo && selected ? ' demo-mode' : ''}`}>
    <header className="beta-nav staging-nav"><AlphaBrand href="/"/><span className="beta-nav-badge">Practice preview</span>
      {user && <details className="staging-menu"><summary>Account</summary><p>{user.email}</p>
        <button disabled={busy} onClick={() => run(() => logout())}>Sign out</button>
        <button disabled={busy} onClick={() => run(() => logout(true))}>Sign out on all devices</button>
      </details>}
    </header><section className="staging-content">
    <p className="staging-eyebrow">RIKSORA BACKTEST LAB · PRIVATE STAGING</p><h1>{user ? (selected ? selected.name : 'Choose a workspace') : 'Your next trading experiment starts here.'}</h1>
    <p role="status" aria-live="polite">{notice}</p>
    {user ? <>
      {!selected && <><p>Signed in as <strong>{user.email}</strong></p>
      <button disabled={busy} onClick={() => run(logout)}>Sign out</button>
      <button disabled={busy} onClick={() => run(refresh)}>Refresh workspaces</button>
      {loaded && !items.length && <p>No saved workspaces yet.</p>}
      <ul className="staging-workspaces">{items.map(ws => <li key={ws.id}><button disabled={busy} onClick={() => { client.selectWorkspace(ws.id); setSelected(ws); }}>{ws.name}</button> <span>{ws.role === 'OWNER' ? 'Workspace owner' : 'Workspace member'}</span></li>)}</ul>
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
      </>}
      {selected && (demo ? <article className="beta-account-workspace">
        <h2>{selected.name}</h2>
        <p role="note"><strong>SHORT SYNTHETIC DEMO.</strong> Practice only. This is not acquired historical data or five-year coverage. Payments are disabled.</p>
        <button disabled={busy} onClick={() => {client.selectWorkspace(selected.id); setSelected(null);}}>Back to workspaces</button>
        <Suspense fallback={<p role="status">Loading practice workspace…</p>}>
          <BetaWorkspace key={selected.id} client={client} workspace={selected} onExpired={() => {
            client.clear(); setUser(null); setItems([]); setSelected(null); setLoaded(false);
            setNotice('Sign-in expired. Sign in again to recover your saved practice Sessions.');
          }}/>
        </Suspense>
      </article> : <article><h2>{selected.name}</h2><p>This workspace is saved on the server. Trading Sessions and real-data replay are not enabled in this release.</p></article>)}
    </> : ready ? <div className="staging-signin"><p>Save your practice Sessions, journal and statistics in your own workspace.</p><a className="staging-primary" href={client.googleStart()}>Continue with Google</a></div> : <p>Sign-in unavailable.</p>}
    <p className="staging-footer">{demo ? 'Practice Sessions, journal and statistics use short synthetic demos only. Real market data, five-year backtests and payments are unavailable.' : 'Backtest, statistics, payments and real market data are not enabled here.'} Workspace ownership does not grant application administration. Refreshing this page requires signing in again; saved workspaces remain on the server.</p>
  </section></main>;
}

createRoot(document.getElementById('root')).render(<StrictMode><WorkspaceStaging/></StrictMode>);
