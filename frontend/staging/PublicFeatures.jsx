import AlphaBrand from '../src/tickAlpha/AlphaBrand.jsx';
import '../src/tickAlpha/tickAlpha.css';
import '../src/beta/beta.css';
import './publicFeatures.css';
const features=[
  ['Sessions & replay','Saved workspace, strategies, 16 synthetic demo instruments, replay, drawings and indicators.','/login/','Google sign-in'],
  ['Strategies','Create Free Style or Protocol strategies from New Session; inspect them in Strategies.','/login/','Google sign-in'],
  ['Orders & positions','Quick Buy/Sell, planned Limit/Stop, server review and confirmation, pending/open/closed positions.','/login/','Synthetic practice'],
  ['Journal & statistics','Saved notes and tags, completed-trade metrics and balance line. Open a Session through the Journal or Statistics menu.','/login/','Google sign-in'],
  ['Trading design playground','Try the existing chart/order/R:R prototype without signing in. Authored sample data, memory only; does not save real Sessions.','/login/?view=prototype','Public interactive demo'],
  ['Account & plan','Google identity, workspace membership, plan status and sign-out on all devices. Checkout stays disabled.','/login/','Google sign-in'],
];
export default function PublicFeatures(){return <main className="beta-account public-features">
  <header className="alpha-identity-nav beta-nav"><AlphaBrand href="/"/><span className="beta-nav-badge">Public preview</span><a href="/login/">Sign in with Google</a></header>
  <section className="public-feature-content"><p>RIKSORA BACKTEST LAB</p><h1>Explore the lab</h1><p>Open the existing product and previews. Saved research needs Google sign-in; the design playground is public.</p>
    <div className="public-feature-grid">{features.map(([name,text,href,status])=><article key={name}><small>{status}</small><h2>{name}</h2><p>{text}</p><a href={href}>Open {name} →</a></article>)}</div>
    <h2>What is still being connected?</h2><dl><dt>Historical tick data</dt><dd>Files are being downloaded and checked. Real-data execution and five-year coverage are not enabled yet.</dd><dt>Payments and email accounts</dt><dd>Checkout is disabled while the provider setup is unfinished. Google sign-in is the available account path.</dd><dt>Local and legacy tools</dt><dd>Tick Review, local historical Alpha, the older workspace and local import tools require a private local runtime. Their local APIs are not exposed by this website.</dd><dt>Internal operations</dt><dd>Odoo/CRM, finance, support operations, backup and data import remain restricted to authorized operators.</dd></dl>
    <p>No real-money trading. This preview is not evidence of complete historical data or commercial readiness.</p>
  </section></main>;}
