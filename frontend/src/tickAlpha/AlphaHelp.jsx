import {PageHead} from './AlphaShell.jsx';
import {linkTo} from './productRoute.js';
import {sourceContext} from './client.js';
import {capabilities,STATUS_LABEL} from './capabilities.js';

// CP4 Help (with service status) and the local Account page. Every status shown
// is either read from the catalog this page already loaded or a fixed statement
// about this build; nothing is estimated or taken from unreleased branches.

function StatusList({catalog,only}){
  const items=capabilities(catalog).filter(item=>!only||only.includes(item.id));
  return <ul className="rk-status-list" aria-label="What works today">{items.map(item=><li key={item.id}>
    <span className={`rk-status rk-status-${item.status.toLowerCase().replace('_','-')}`}>{STATUS_LABEL[item.status]}</span>
    <div><strong>{item.label}</strong><small>{item.note}</small></div></li>)}</ul>;
}

export function HelpPage({catalog,onSource,onFeedback}){
  const historical=sourceContext()==='historical';
  return <><PageHead eyebrow="Help" title="Help" lead="Short answers, and an honest list of what works today."/>
    <section className="rk-card rk-help-start" aria-labelledby="rk-help-start"><h2 id="rk-help-start">Getting started</h2>
      <ol className="rk-help-steps">
        <li><strong>Write a Method.</strong> Free Style or Protocol rules. <a {...linkTo({screen:'method-new'})}>New Method</a></li>
        <li><strong>Start a Session.</strong> Pick the Method, instrument, start month and balance. <a {...linkTo({screen:'session-new'})}>New Session</a></li>
        <li><strong>Replay and trade.</strong> Draft an order, check the server review, then confirm.</li>
        <li><strong>Review.</strong> Add notes in the <a {...linkTo({screen:'journal'})}>Journal</a> and read each Session’s <a {...linkTo({screen:'analytics'})}>Analytics</a>.</li>
      </ol></section>
    <div className="rk-grid-2">
      <section className="rk-card" aria-labelledby="rk-help-status"><h2 id="rk-help-status">Service status</h2>
        <dl className="rk-facts">
          <div><dt>Research service</dt><dd><span className="rk-status rk-status-available">Connected</span></dd></div>
          <div><dt>Data</dt><dd>{historical?'Historical quotes':'Synthetic test feed'} · {catalog.label}</dd></div>
        </dl>
        <StatusList catalog={catalog}/>
      </section>
      <div className="rk-help-faq">
        <details className="rk-card rk-disclosure" open><summary>How replay works</summary><p>History is revealed step by step from the Session’s saved time. Orders fill on later observed Bid/Ask quotes only, never on prices that were not yet visible.</p></details>
        <details className="rk-card rk-disclosure"><summary>Draft, review, confirm</summary><p>Buy or Sell opens a draft. The server reviews exact values, and nothing is placed until you confirm. Drawing a position is a planning tool, not a trade.</p></details>
        <details className="rk-card rk-disclosure"><summary>Data limitations</summary><p>Each Session pins one source and version. Missing or refused months are never filled with another feed.</p><button type="button" className="rk-btn" onClick={onSource}>Source details</button></details>
        <details className="rk-card rk-disclosure"><summary>Report a problem</summary><p>Send optional research feedback. Do not include passwords or tokens.</p><button type="button" className="rk-btn" onClick={onFeedback}>Open feedback</button></details>
      </div>
    </div></>;
}

export function LocalAccountPage({catalog}){
  return <><PageHead eyebrow="Account" title="Account" lead="This is the private local workspace: no sign-in, and research stays on this computer."
      actions={<a className="rk-btn rk-btn-primary" href="/?page=account">Open account page</a>}/>
    <div className="rk-grid-2">
      <section className="rk-card" aria-labelledby="rk-acc-here"><h2 id="rk-acc-here">This workspace</h2>
        <dl className="rk-facts">
          <div><dt>Workspace</dt><dd>Private local workspace</dd></div>
          <div><dt>Sign-in</dt><dd>Not used here</dd></div>
          <div><dt>Where data lives</dt><dd>The local service and database on this computer</dd></div>
          <div><dt>Methods / Sessions</dt><dd className="rk-num">{catalog.methods.length} / {catalog.sessions.length}</dd></div>
          <div><dt>Data</dt><dd>{catalog.label}</dd></div>
        </dl></section>
      <section className="rk-card" aria-labelledby="rk-acc-online"><h2 id="rk-acc-online">Online account</h2>
        <p className="rk-note">Signing in, workspaces and sign-out on all devices live on the secure account page, which needs the https:// address.</p>
        <StatusList catalog={catalog} only={['google','plans']}/>
      </section>
    </div></>;
}
