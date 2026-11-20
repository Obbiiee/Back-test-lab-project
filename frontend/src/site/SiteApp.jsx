import {useEffect} from 'react';
import '../tickAlpha/riksoraBrand.css';
import './site.css';
import {RiksoraMark} from '../tickAlpha/AlphaBrand.jsx';
import {SITE} from './siteConfig.js';
import {COPY, CLAIMS, fill} from './content.js';
import {FREE_LIMITS, formatIdr, currentPrice, yearlySavingPercent} from './plans.js';

import {siteLang, sitePage} from './siteRoute.js';
const preview = SITE.launchState !== 'live';
const href = (page, lang) => (page === 'home' ? '/' : `/?page=${page}`) + (lang === 'en' ? (page === 'home' ? '?lang=en' : '&lang=en') : '');
const account = '/app';
const anchor = (id, lang) => (lang === 'en' ? '/?lang=en' : '/') + '#' + id;   // the landing is one page: pricing, about and contact are sections of it
const signInOpen = SITE.launchState !== 'preview';   // beta/live: Google sign-in is open; purchases stay closed until live
const entry = (lang) => (signInOpen ? account : href('contact', lang));

function Header({t, lang, page}) {
  return <header className="site-nav">
    <a className="site-brand" href={href('home', lang)} aria-label={SITE.brand}><RiksoraMark size={36}/><span>RIKSORA <small>BACKTEST LAB</small></span></a>
    <nav aria-label="Main">
      <a href={anchor('how', lang)} aria-current={page === 'home' ? 'page' : undefined}>{t.nav.how}</a>
      <a href={anchor('pricing', lang)}>{t.nav.pricing}</a>
      <a href={anchor('about', lang)}>{t.nav.about}</a>
      <a href={anchor('contact', lang)}>{t.nav.contact}</a>
    </nav>
    <div className="site-nav-actions">
      <a className="site-lang" href={href(page, t.other)} hrefLang={t.other} lang={t.other}>{t.otherLabel}</a>
      <a className="site-pill" href={entry(lang)}>{signInOpen ? t.nav.open : t.preview.nav}</a>
    </div>
  </header>;
}

function Footer({t, lang}) {
  const b = SITE.business;
  return <footer className="site-footer">
    <div className="site-footer-grid">
      <div>
        <strong>{b.publicName || SITE.brand}</strong>
        {b.legalForm && <span>{b.legalForm}</span>}
        {b.address && <span>{b.address}</span>}
        {b.email && <span><a href={`mailto:${b.email}`}>{b.email}</a></span>}
        {b.phone && <span>{b.phone}</span>}
        {b.nib && <span>NIB {b.nib}</span>}
      </div>
      <nav aria-label="Legal">
        <a href={anchor('pricing', lang)}>{t.nav.pricing}</a>
        <a href={anchor('about', lang)}>{t.nav.about}</a>
        <a href={anchor('contact', lang)}>{t.nav.contact}</a>
        <a href={href('terms', 'id')} hrefLang="id">{t.nav.terms}</a>
        <a href={href('privacy', 'id')} hrefLang="id">{t.nav.privacy}</a>
        <a href={href('refund', 'id')} hrefLang="id">{t.nav.refund}</a>
      </nav>
    </div>
    <p>{t.footer.disclaimer}</p>
    <p>© {new Date().getFullYear()} {b.publicName || SITE.brand}. {t.footer.rights}</p>
  </footer>;
}

function ProCard({t, period, withCta}) {
  const today = new Date().toISOString().slice(0, 10);
  const price = currentPrice(SITE, period, today);
  const p = t.pricing.pro;
  return <article className="site-plan site-plan-pro">
    <h3>{period === 'monthly' ? p.monthlyName : p.yearlyName}</h3>
    <p className="site-price">
      {price
        ? <>{price.listPriceIdr && <s className="site-was" aria-label={`${p.was} ${formatIdr(price.listPriceIdr)}`}>{formatIdr(price.listPriceIdr)}</s>} {formatIdr(price.priceIdr)} <small>{period === 'monthly' ? p.perMonth : p.perYear}</small></>
        : <span className="site-pending">{t.pricing.pending}</span>}
    </p>
    {price && price.listPriceIdr && <p className="site-promo">{p.saving} {price.savingPercent}% · {p.until} {price.endsOn}</p>}
    {price && period === 'yearly' && yearlySavingPercent(SITE) > 0 && <p className="site-promo">{p.saving} {yearlySavingPercent(SITE)}% {p.vsMonthly} · {p.perMonthEquivalent} {formatIdr(Math.round(price.priceIdr / 12))} / {t.lang === 'en' ? 'month' : 'bulan'}</p>}
    <ul>{p.features.map(item => <li key={item}>{item}</li>)}</ul>
    {SITE.pro.taxNote && <p className="site-fine">{SITE.pro.taxNote}</p>}
    {withCta && (preview ? <p className="site-fine">{t.preview.buyNote}</p> : <a className="site-primary" href={account}>{t.pricing.buy}</a>)}
  </article>;
}

function PlanCards({t, withCta = true}) {
  return <div className="site-plans">
    <article className="site-plan">
      <h3>{t.pricing.free.name}</h3>
      <p className="site-price">{t.pricing.free.price} <small>{t.pricing.free.per}</small></p>
      <ul>{t.pricing.free.features.map(item => <li key={item}>{item}</li>)}</ul>
      {withCta && <a className="site-secondary" href={entry(t.lang)}>{signInOpen ? t.hero.primary : t.hero.previewPrimary}</a>}
    </article>
    <ProCard t={t} period="monthly" withCta={withCta}/>
    <ProCard t={t} period="yearly" withCta={withCta}/>
  </div>;
}

// Deterministic candles for the illustration only (no market data).
const CANDLES = (() => {
  let seed = 5, p = 140;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const out = {bUp: '', bDn: '', wUp: '', wDn: ''};
  for (let i = 0; i < 26; i++) {
    const o = p, c = o - (rnd() - 0.45) * 22, h = Math.min(o, c) - rnd() * 10, l = Math.max(o, c) + rnd() * 10;
    const x = 10 + i * 9, top = Math.min(o, c), hh = Math.max(2, Math.abs(c - o));
    const body = `M${x} ${top.toFixed(1)}h6v${hh.toFixed(1)}h-6Z`, wick = `M${x + 3} ${h.toFixed(1)}V${l.toFixed(1)}`;
    if (c <= o) { out.bUp += body; out.wUp += wick; } else { out.bDn += body; out.wDn += wick; }
    p = Math.max(40, Math.min(190, c));
  }
  return out;
})();

function HeroVisual({t}) {
  return <div className="lp-visual">
    <span className="lp-blob lp-blob-blue" aria-hidden="true"/><span className="lp-blob lp-blob-red" aria-hidden="true"/>
    <div className="lp-terminal" role="img" aria-label={t.lp.previewLabel}>
      <div className="lp-terminal-bar"><b>XAUUSD · 5m</b><span>{t.lp.replaying}</span></div>
      <svg viewBox="0 0 420 220" aria-hidden="true">
        <rect x="250" y="40" width="150" height="62" rx="6" fill="#1378F5" fillOpacity="0.25"/>
        <rect x="250" y="102" width="150" height="34" rx="6" fill="#FF7373" fillOpacity="0.25"/>
        <path d={CANDLES.wUp} stroke="#2BB39A" strokeWidth="1.5" fill="none"/><path d={CANDLES.wDn} stroke="#FF7373" strokeWidth="1.5" fill="none"/>
        <path d={CANDLES.bUp} fill="#2BB39A"/><path d={CANDLES.bDn} fill="#FF7373"/>
        <line x1="250" x2="400" y1="102" y2="102" stroke="#FFFFFF" strokeWidth="2"/>
      </svg>
    </div>
    <div className="lp-chip lp-chip-hit" aria-hidden="true"><b>{t.lp.hitTitle}</b><span>{t.lp.hitValue}</span></div>
    <div className="lp-chip lp-chip-buy" aria-hidden="true">{t.lp.buyChip}</div>
    <p className="lp-note">{t.lp.previewNote}</p>
  </div>;
}

function Home({t, lang}) {
  const [before, after] = t.hero.title.split(t.hero.mark);
  const cta = signInOpen ? t.hero.primary : t.hero.previewPrimary;
  return <div className="lp">
    <section className="lp-hero" aria-labelledby="hero-h">
      <div className="lp-hero-in">
        <div className="lp-copy">
          <p className="lp-badge"><span>{t.lp.badgeTag}</span>{t.hero.badge}</p>
          <h1 id="hero-h">{before}<mark>{t.hero.mark}</mark>{after}</h1>
          <p className="lp-lead">{t.hero.lead}</p>
          <div className="lp-actions">
            <a className="lp-cta" href={entry(lang)}>{cta}</a>
            <a className="lp-ghost" href="#how"><span aria-hidden="true">▶</span>{t.nav.how}</a>
          </div>
          <p className="lp-fine">{t.hero.caption}</p>
        </div>
        <HeroVisual t={t}/>
      </div>
    </section>
    <section id="how" className="lp-how" aria-labelledby="how-h">
      <div className="lp-wrap">
        <h2 id="how-h">{t.how.title}</h2>
        <ol className="lp-steps">{t.how.steps.map(([title, text], index) => <li key={title} className={`lp-step lp-step-${index + 1}`}><span aria-hidden="true">{index + 1}</span><h3>{title}</h3><p>{text}</p></li>)}</ol>
      </div>
    </section>
    <section id="why" className="lp-features" aria-labelledby="why-h">
      <div className="lp-wrap">
        <h2 id="why-h">{t.whyTitle}</h2>
        <div className="lp-bento">{CLAIMS.map((claim, index) => <article key={claim.key} className={`lp-tile lp-tile-${index % 6}`}><h3>{claim[t.lang].t}</h3><p>{claim[t.lang].d}</p>{index === 0 && <div className="lp-fills">{t.lp.fills.map(item => <span key={item}>{item}</span>)}</div>}</article>)}</div>
      </div>
    </section>
    <section id="purpose" className="site-section" aria-labelledby="purpose-h">
      <h2 id="purpose-h">{t.purpose.title}</h2>
      {t.purpose.body.map(text => <p key={text}>{text}</p>)}
    </section>
    <section id="pricing" className="lp-plans" aria-labelledby="plans-h">
      <div className="lp-wrap">
        <h2 id="plans-h">{t.plans.title}</h2><p className="lp-plans-lead">{t.plans.lead}</p>
        <PlanCards t={t} withCta={false}/>
        <div className="lp-rules">
          <h3>{t.pricing.rulesTitle}</h3>
          <ul>{t.pricing.rules.map(item => <li key={item}>{item}</li>)}</ul>
          <h3>{t.pricing.payTitle}</h3>
          <p>{t.pricing.payLead}</p>
          {Array.isArray(SITE.payment.methods) && SITE.payment.methods.length > 0
            ? <ul>{SITE.payment.methods.map(item => <li key={item}>{item}</li>)}</ul>
            : <p>{t.pricing.taxNone}</p>}
          {SITE.pro.taxNote && <p>{SITE.pro.taxNote}</p>}
        </div>
      </div>
    </section>
    <section id="limits" className="site-section" aria-labelledby="limits-h">
      <h2 id="limits-h">{t.limits.title}</h2>
      <ul className="site-list">{t.limits.items.map(item => <li key={item}>{item}</li>)}</ul>
    </section>
    <section id="faq" className="site-section site-alt" aria-labelledby="faq-h">
      <h2 id="faq-h">{t.faq.title}</h2>
      {t.faq.items.map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}
    </section>
    <About t={t} embedded/>
    <Contact t={t} embedded/>
    <section className="lp-final-wrap" aria-labelledby="final-h">
      <div className="lp-final">
        <span className="lp-blob lp-blob-yellow" aria-hidden="true"/><span className="lp-blob lp-blob-red2" aria-hidden="true"/>
        <h2 id="final-h">{t.lp.ctaTitle}</h2><p>{t.lp.ctaLead}</p>
        <a className="lp-cta lp-cta-white" href={entry(lang)}>{cta}</a>
      </div>
    </section>
  </div>;
}

function Pricing({t}) {
  const methods = SITE.payment.methods;
  return <section className="site-page site-page-wide" aria-labelledby="pr-h">
    <h1 id="pr-h">{t.pricing.title}</h1><p className="site-lead">{t.pricing.lead}</p>
    <PlanCards t={t}/>
    <h2>{t.pricing.rulesTitle}</h2>
    <ul className="site-list">{t.pricing.rules.map(item => <li key={item}>{item}</li>)}</ul>
    <p className="site-fine">Free: {FREE_LIMITS.SESSION} {t.lang === 'en' ? 'new Session / day' : 'Sesi baru / hari'} · {FREE_LIMITS.WINDOW} {t.lang === 'en' ? 'new historical month / day' : 'bulan historis baru / hari'} (UTC)</p>
    <h2>{t.pricing.payTitle}</h2>
    <p>{t.pricing.payLead}</p>
    {Array.isArray(methods) && methods.length > 0
      ? <><h3>{t.pricing.payMethods}</h3><ul className="site-list">{methods.map(item => <li key={item}>{item}</li>)}</ul></>
      : <p className="site-fine">{t.pricing.taxNone}</p>}
    {SITE.pro.taxNote && <p className="site-fine">{SITE.pro.taxNote}</p>}
  </section>;
}

function About({t, embedded = false}) {
  const b = SITE.business, H = embedded ? 'h2' : 'h1', H2 = embedded ? 'h3' : 'h2';
  return <section id={embedded ? 'about' : undefined} className={embedded ? 'site-section' : 'site-page'} aria-labelledby="ab-h">
    <H id="ab-h">{t.about.title}</H>
    {t.about.body.map(text => <p key={text}>{text}</p>)}
    <H2>{t.about.principlesTitle}</H2>
    <ul className="site-list">{t.about.principles.map(item => <li key={item}>{item}</li>)}</ul>
    <H2>{t.about.identityTitle}</H2>
    <dl className="site-facts">
      <dt>{t.lang === 'en' ? 'Name' : 'Nama'}</dt><dd>{b.publicName || '—'}</dd>
      {b.legalForm && <><dt>{t.lang === 'en' ? 'Form' : 'Bentuk usaha'}</dt><dd>{b.legalForm}</dd></>}
      {b.nib && <><dt>NIB</dt><dd>{b.nib}</dd></>}
      <dt>{t.contact.address}</dt><dd>{b.address || '—'}</dd>
      <dt>{t.contact.email}</dt><dd>{b.email ? <a href={`mailto:${b.email}`}>{b.email}</a> : '—'}</dd>
    </dl>
  </section>;
}

function Contact({t, embedded = false}) {
  const b = SITE.business, H = embedded ? 'h2' : 'h1';
  return <section id={embedded ? 'contact' : undefined} className={embedded ? 'site-section site-alt' : 'site-page'} aria-labelledby="ct-h">
    <H id="ct-h">{t.contact.title}</H><p className="site-lead">{t.contact.lead}</p>
    <dl className="site-facts">
      <dt>{t.contact.email}</dt><dd>{b.email ? <a href={`mailto:${b.email}`}>{b.email}</a> : '—'}</dd>
      {b.phone && <><dt>{t.contact.phone}</dt><dd>{b.phone}</dd></>}
      <dt>{t.contact.address}</dt><dd>{b.address || '—'}</dd>
      {b.supportHours && <><dt>{t.contact.hours}</dt><dd>{b.supportHours}</dd></>}
      {b.responseTime && <><dt>{t.contact.response}</dt><dd>{b.responseTime}</dd></>}
    </dl>
    <p>{t.contact.data}</p>
  </section>;
}

function Preview({t, lang}) {
  return <section className="site-page" aria-labelledby="pv-h">
    <h1 id="pv-h">{t.preview.title}</h1>
    {t.preview.body.map(text => <p key={text}>{text}</p>)}
    <p><a className="site-primary" href={href('contact', lang)}>{t.preview.cta}</a></p>
  </section>;
}

function Legal({t, page}) {
  const doc = COPY.id[page];                       // legal text exists in Indonesian only
  const approved = SITE.legalApproval[page];
  return <article className="site-page site-legal" aria-labelledby="lg-h" lang="id">
    <h1 id="lg-h">{doc.title}</h1>
    {approved ? <p className="site-fine">{COPY.id.updated}: {approved}</p> : <p className="site-draft" role="note">{COPY.id.legalDraft}</p>}
    {t.lang === 'en' && <p className="site-fine" lang="en">{COPY.en.legalDraft}</p>}
    {doc.sections.map(([heading, paragraphs]) => <section key={heading}><h2>{heading}</h2>{paragraphs.map(text => <p key={text}>{fill(text, SITE)}</p>)}</section>)}
  </article>;
}

export default function SiteApp({location}) {
  const lang = siteLang(location.search), page = sitePage(location.search), t = COPY[lang];
  useEffect(() => {   // pricing, about and contact are sections of the landing now; old links keep working
    if (['pricing', 'about', 'contact'].includes(page)) window.location.replace(anchor(page === 'pricing' ? 'pricing' : page, lang));
  }, [page, lang]);
  useEffect(() => {
    const names = {account: t.preview.title, home: t.hero.badge, pricing: t.pricing.title, about: t.about.title, contact: t.contact.title, terms: COPY.id.terms.title, privacy: COPY.id.privacy.title, refund: COPY.id.refund.title};
    document.title = page === 'home' ? `${SITE.brand} — ${t.hero.badge}` : `${names[page]} — ${SITE.brand}`;
    document.documentElement.lang = page === 'terms' || page === 'privacy' || page === 'refund' ? 'id' : lang;
  }, [lang, page, t]);
  return <div className="site">
    <a className="site-skip" href="#main">{lang === 'en' ? 'Skip to content' : 'Lompat ke konten'}</a>
    <Header t={t} lang={lang} page={page}/>
    <main id="main">
      {page === 'home' && <Home t={t} lang={lang}/>}
      {page === 'pricing' && <Pricing t={t}/>}
      {page === 'about' && <About t={t}/>}
      {page === 'contact' && <Contact t={t}/>}
      {['terms', 'privacy', 'refund'].includes(page) && <Legal t={t} page={page}/>}
      {page === 'account' && <Preview t={t} lang={lang}/>}
    </main>
    <Footer t={t} lang={lang}/>
  </div>;
}
