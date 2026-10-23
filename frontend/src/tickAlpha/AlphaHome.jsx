import './riksoraBrand.css';
import './alphaHome.css';
import {RiksoraMark} from './AlphaBrand.jsx';
import {pagePath,landingWorkspacePath} from './client.js';

// Playful landing (docs/design/RIKSORA_PLAYFUL_UI_PLAN.md §3, screen 1). Copy stays truthful to
// the local Alpha: XAUUSD only, no accounts or plans yet, historical research without brokerage.
function previewCandles(){
  // Deterministic illustration: price drifts up into the planned long box (entry at y=102).
  let seed=7,close=176,up='',down='',upWick='',downWick='';
  const rnd=()=>(seed=(seed*16807)%2147483647)/2147483647;
  for(let i=0;i<26;i++){
    const open=close;close=176-i*2.9+(rnd()-0.5)*16;
    const high=Math.min(open,close)-2-rnd()*7,low=Math.max(open,close)+2+rnd()*7;
    const x=12+i*9,top=Math.min(open,close),height=Math.max(2,Math.abs(close-open));
    const body=`M${x} ${top.toFixed(1)}h6v${height.toFixed(1)}h-6Z`,wick=`M${x+3} ${high.toFixed(1)}V${low.toFixed(1)}`;
    if(close<=open){up+=body;upWick+=wick;}else{down+=body;downWick+=wick;}
  }
  return {up,down,upWick,downWick};
}
const candles=previewCandles();
const steps=[
  ['Pick a moment','Write your strategy, choose a start month and a starting balance. The chart stops right there.'],
  ['Press Play and trade','Candles form one by one. Buy, Sell, or plan a trade with stop and target when your setup shows up.'],
  ['Learn from the results','Every trade lands in the journal and Analysis: win rate, profit factor, drawdown and the balance line.'],
];

export default function AlphaHome({hostedPreview=false}={}){
  const workspace=hostedPreview?'/login/':landingWorkspacePath(),home=hostedPreview?'/':pagePath('home');
  return <main className="alpha-home">
    <a className="alpha-home-skip" href="#how">Skip to how it works</a>
    <header className="alpha-home-nav">
      <a className="alpha-home-brand" href={home} aria-label="Riksora Labs home"><RiksoraMark size={40}/><span>RIKSORA <small>BACKTEST LAB</small></span></a>
      <nav aria-label="Main navigation"><a href="#how">How it works</a><a href="#features">Features</a><a href="#principles">Principles</a></nav>
      <a className="alpha-home-pill" href={workspace}>Open workspace</a>
    </header>

    <section className="alpha-home-hero">
      <div className="alpha-home-copy">
        <p className="alpha-home-badge"><span>{hostedPreview?'Public preview':'Local Alpha'}</span>{hostedPreview?'16 short synthetic demo pairs':'Replay real bid/ask ticks'}</p>
        <h1>{hostedPreview?'Explore your trading ideas in ':'Practice trading on '}<span className="alpha-home-sticker">{hostedPreview?'practice':'yesterday’s'}</span>{hostedPreview?' Sessions.':' market.'}</h1>
        <p className="alpha-home-intro">{hostedPreview?'Sign in with Google, create a practice Session and replay synthetic bid/ask quotes. Save your orders, journal and statistics. Historical data is still being validated.':'Pick a date, press Play and trade the candles as they form. No peeking at the future, no guessed fills. Just you, your plan and the replay.'}</p>
        <div className="alpha-home-actions">
          <a className="alpha-home-primary" href={workspace}>Start backtesting</a>
          <a className="alpha-home-secondary" href={hostedPreview?'/login/?view=features':'/?page=beta'}>{hostedPreview?'Explore all features':'16-pair Beta sandbox'}</a>
          <a className="alpha-home-secondary" href="#how"><span aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24"><path d="M7 4l13 8-13 8z" fill="currentColor"/></svg></span>See how it works</a>
        </div>
        <p className="alpha-home-caption">{hostedPreview?'Public staging · synthetic practice · Google sign-in for saved work · no payments':'Private local workspace · historical research · no live brokerage'}</p>
      </div>
      <div className="alpha-home-preview" role="img" aria-label="Illustration: a replaying XAUUSD chart with a planned long trade, a fill note and a target-hit note">
        <span className="alpha-home-blob alpha-home-blob-blue" aria-hidden="true"/>
        <span className="alpha-home-blob alpha-home-blob-coral" aria-hidden="true"/>
        <div className="alpha-home-chart" aria-hidden="true">
          <div><span>XAUUSD · 5m</span><span>▶ replaying</span></div>
          <svg viewBox="0 0 420 220">
            <rect x="250" y="40" width="150" height="62" rx="6" fill="#1378F5" fillOpacity=".25"/>
            <rect x="250" y="102" width="150" height="34" rx="6" fill="#FF7373" fillOpacity=".25"/>
            <path d={candles.upWick} stroke="#2BB39A" strokeWidth="1.5"/><path d={candles.downWick} stroke="#FF7373" strokeWidth="1.5"/>
            <path d={candles.up} fill="#2BB39A"/><path d={candles.down} fill="#FF7373"/>
            <line x1="250" x2="400" y1="102" y2="102" stroke="#FFFFFF" strokeWidth="2"/>
          </svg>
        </div>
        <p className="alpha-home-note alpha-home-note-fill" aria-hidden="true">Buy 0.40 · filled at Ask</p>
        <p className="alpha-home-note alpha-home-note-target" aria-hidden="true"><span><svg width="20" height="20" viewBox="0 0 24 24"><path d="M12 2l3 7 7 .6-5.3 4.7 1.6 7.2L12 17.8 5.7 21.5l1.6-7.2L2 9.6 9 9z" fill="#FFCE55"/></svg></span><b>Target hit<small>+2.00R</small></b></p>
      </div>
    </section>

    <section id="how" className="alpha-home-how">
      <h2>Three steps. One habit.</h2>
      <ol>{steps.map(([title,text],index)=><li key={title}><span className={`alpha-home-step alpha-home-step-${index+1}`} aria-hidden="true">{index+1}</span><h3>{title}</h3><p>{hostedPreview&&index===0?'Choose a demo pair, create your strategy and set a starting balance. No historical date selection is available yet.':text}</p></li>)}</ol>
    </section>

    <section id="features" className="alpha-home-features" aria-label="Features">
      <article className="alpha-home-feature-navy"><div><span className="alpha-home-tag">Honest fills</span><h3>{hostedPreview?'Bid/ask tick execution in synthetic practice.':'Real bid/ask ticks, not candle guesses.'}</h3><p>Buys fill at Ask, sells at Bid, stops trigger on the actual tick. When data is missing the result stays unresolved instead of guessed.</p></div><div className="alpha-home-quotes"><span>Bid</span><span>Ask</span></div></article>
      <article className="alpha-home-feature-yellow"><h3>Review before confirmation</h3><p>{hostedPreview?'Review your exact order values before confirming. Accepted orders wait for the next eligible tick.':'Pick 0.5, 1, 2 or 3% and see the estimated loss, profit and R:R before the server review confirms the exact size.'}</p></article>
      <article className="alpha-home-feature-blue"><h3>Journal and Statistics</h3><p>Every committed trade with its evidence, plus win rate, profit factor, drawdown and the balance line per Session.</p></article>
      <article className="alpha-home-feature-white"><h3>{hostedPreview?'16 demo instruments':'Gold first'}</h3><p>{hostedPreview?'Short synthetic datasets for practice. Five-year historical coverage is not enabled.':'The local Alpha replays XAUUSD. More instruments follow once their data is approved.'}</p></article>
      <article className="alpha-home-feature-coral"><h3>Pick up where you left off</h3><p>Each Session remembers its replay position, orders and balance.</p></article>
    </section>

    <section id="principles" className="alpha-home-principles">
      <h2>Uncertainty is part of the result.</h2>
      <p>Backtest Lab is a practice and research tool, not a forecast or a promise of trading returns. {hostedPreview?'This hosted preview uses synthetic demos; downloaded historical files are not yet enabled for execution.':'The local Alpha uses imported historical data with explicit source limitations.'} Source attribution does not imply broker endorsement or public redistribution rights.</p>
      <ul><li>Data provenance</li><li>No look-ahead</li><li>Reproducible Sessions</li><li>Explicit limitations</li></ul>
    </section>

    <section className="alpha-home-cta">
      <span className="alpha-home-cta-square" aria-hidden="true"/><span className="alpha-home-cta-circle" aria-hidden="true"/><span className="alpha-home-cta-dot" aria-hidden="true"/>
      <h2>Your next 100 trades can happen tonight.</h2>
      <p>Practice months of market in an evening.</p>
      <a href={workspace}>Start backtesting</a>
    </section>

    <footer className="alpha-home-footer"><span>© RIKSORA Labs · Backtest Lab</span><a href={workspace}>Workspace</a><span>Simulated trading for practice. Not financial advice.</span></footer>
  </main>;
}
