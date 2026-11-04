import Icon from '../workspace/WorkspaceIcon.jsx';
import './alphaProduct.css';
import {RiksoraMark} from './AlphaBrand.jsx';
import {linkTo,accountLink} from './productRoute.js';

// Product shell (founder instruction 2026-11-05 §4): desktop sidebar with My Methods,
// Sessions, Data Catalog, Journal, Analytics and Account/Help at the bottom; phones get
// at most five tabs. Replay needs a selected Session, so its tab explains that first.
const MAIN=[['methods','My Methods','layers'],['sessions','Sessions','calendar'],['catalog','Data Catalog','hex'],['journal','Journal','journal'],['analytics','Analytics','analytics']];
const PHONE=[['methods','Methods','layers'],['sessions','Sessions','calendar'],['replay','Replay','candles'],['analytics','Analysis','analytics']];


function active(route,key){
  if(key==='methods')return ['methods','method','method-new'].includes(route.screen);
  return route.screen===key;
}

export default function AlphaShell({route,label,children}){
  return <div className="rk-shell">
    <aside className="rk-sidebar" aria-label="Product">
      <a className="rk-sidebar-brand" {...linkTo({screen:'methods'})} aria-label="RIKSORA · My Methods"><RiksoraMark size={36}/><span>RIKSORA</span></a>
      <span className="rk-sidebar-badge">{label}</span>
      <nav aria-label="Main">
        {MAIN.map(([key,text,icon])=><a key={key} className="rk-nav-item" aria-current={active(route,key)?'page':undefined} {...linkTo({screen:key})}><Icon name={icon}/><span>{text}</span></a>)}
      </nav>
      <nav aria-label="Account and help" className="rk-sidebar-foot">
        <a className="rk-nav-item" aria-current={route.screen==='account'?'page':undefined} {...accountLink()}><Icon name="smile"/><span>Account</span></a>
        <a className="rk-nav-item" aria-current={route.screen==='help'?'page':undefined} {...linkTo({screen:'help'})}><Icon name="news"/><span>Help</span></a>
      </nav>
    </aside>
    <div className="rk-main" id="rk-main">{children}</div>
    <nav className="rk-tabbar" aria-label="App sections">
      {PHONE.map(([key,text,icon])=><a key={key} aria-current={active(route,key)?'page':undefined} {...linkTo({screen:key})}><Icon name={icon}/><span>{text}</span></a>)}
      <a aria-current={route.screen==='account'?'page':undefined} {...accountLink()}><Icon name="smile"/><span>Account</span></a>
    </nav>
  </div>;
}

// One component for every non-ready page state, so loading, empty, filtered-empty,
// error, offline, expired sign-in, forbidden and unavailable look and read the same.
const TONES={loading:'info',empty:'info',filtered:'info',error:'error',offline:'error',expired:'warn',forbidden:'warn',unavailable:'warn'};
// level=1 when the state is the whole page (connecting, offline, opening a Session) so the page keeps one h1.
export function StatePanel({kind,title,children,action,level=2}){
  const Heading=level===1?'h1':'h2';
  return <section className={`rk-state rk-state-${TONES[kind]||'info'}`} role={kind==='error'||kind==='offline'?'alert':'status'} aria-busy={kind==='loading'||undefined}>
    {kind==='loading'&&<span className="rk-spinner" aria-hidden="true"/>}
    <Heading>{title}</Heading>{children&&<div className="rk-state-body">{children}</div>}{action}
  </section>;
}

export function PageHead({eyebrow,title,lead,actions,back}){
  return <div className="rk-page-head">
    {back&&<a className="rk-back" {...linkTo(back.to)}><Icon name="back" size={16}/><span>{back.label}</span></a>}
    <div className="rk-page-title"><div>{eyebrow&&<p className="rk-eyebrow">{eyebrow}</p>}<h1>{title}</h1>{lead&&<p className="rk-lead">{lead}</p>}</div>{actions&&<div className="rk-page-actions">{actions}</div>}</div>
  </div>;
}
