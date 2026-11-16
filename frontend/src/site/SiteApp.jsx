import {useEffect} from 'react';
import '../tickAlpha/riksoraBrand.css';
import './site.css';
import {RiksoraMark} from '../tickAlpha/AlphaBrand.jsx';
import {SITE} from './siteConfig.js';
import {COPY, CLAIMS, fill} from './content.js';
import {FREE_LIMITS, formatIdr, currentPrice, yearlySavingPercent} from './plans.js';

export const PAGES = ['home', 'pricing', 'about', 'contact', 'terms', 'privacy', 'refund', 'account'];
const preview = SITE.launchState !== 'live';

export function siteLang(search) {
  const value = new URLSearchParams(search).get('lang');
  return value === 'en' ? 'en' : 'id';
}
export function sitePage(search) {
  const value = new URLSearchParams(search).get('page');
  return PAGES.includes(value) ? value : 'home';
}
const href = (page, lang) => (page === 'home' ? '/' : `/?page=${page}`) + (lang === 'en' ? (page === 'home' ? '?lang=en' : '&lang=en') : '');
const account = '/?page=account';
const entry = (lang) => (preview ? href('contact', lang) : account);

function Header({t, lang, page}) {
  return <header className="site-nav">
    <a className="site-brand" href={href('home', lang)} aria-label={SITE.brand}><RiksoraMark size={36}/><span>RIKSORA <small>BACKTEST LAB</small></span></a>
    <nav aria-label="Main">
      <a href={href('home', lang) + (lang === 'en' ? '#how' : '#how')} aria-current={page === 'home' ? 'page' : undefined}>{t.nav.how}</a>
      <a href={href('pricing', lang)} aria-current={page === 'pricing' ? 'page' : undefined}>{t.nav.pricing}</a>
      <a href={href('about', lang)} aria-current={page === 'about' ? 'page' : undefined}>{t.nav.about}</a>
      <a href={href('contact', lang)} aria-current={page === 'contact' ? 'page' : undefined}>{t.nav.contact}</a>
    </nav>
    <div className="site-nav-actions">
      <a className="site-lang" href={href(page, t.other)} hrefLang={t.other} lang={t.other}>{t.otherLabel}</a>
      <a className="site-pill" href={entry(lang)}>{preview ? t.preview.nav : t.nav.open}</a>
    </div>
  </header>;
}

function Footer({t, lang}) {
  const b = SITE.business;
  return <footer className="site-footer">
    <div className="site-footer-grid">
      <div>
        <strong>{b.legalName || SITE.brand}</strong>
        {b.legalForm && <span>{b.legalForm}</span>}
        {b.address && <span>{b.address}</span>}
        {b.email && <span><a href={`mailto:${b.email}`}>{b.email}</a></span>}
        {b.phone && <span>{b.phone}</span>}
        {b.nib && <span>NIB {b.nib}</span>}
      </div>
      <nav aria-label="Legal">
        <a href={href('pricing', lang)}>{t.nav.pricing}</a>
        <a href={href('about', lang)}>{t.nav.about}</a>
        <a href={href('contact', lang)}>{t.nav.contact}</a>
        <a href={href('terms', 'id')} hrefLang="id">{t.nav.terms}</a>
        <a href={href('privacy', 'id')} hrefLang="id">{t.nav.privacy}</a>
        <a href={href('refund', 'id')} hrefLang="id">{t.nav.refund}</a>
      </nav>
    </div>
    <p>{t.footer.disclaimer}</p>
    <p>© {new Date().getFullYear()} {b.legalName || SITE.brand}. {t.footer.rights}</p>
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
      {withCta && <a className="site-secondary" href={entry(t.lang)}>{preview ? t.hero.previewPrimary : t.hero.primary}</a>}
    </article>
    <ProCard t={t} period="monthly" withCta={withCta}/>
    <ProCard t={t} period="yearly" withCta={withCta}/>
  </div>;
}

function Home({t, lang}) {
  return <>
    <section className="site-hero">
      <p className="site-badge">{t.hero.badge}</p>
      <h1>{t.hero.title}</h1>
      <p className="site-lead">{t.hero.lead}</p>
      <div className="site-actions"><a className="site-primary" href={entry(lang)}>{preview ? t.hero.previewPrimary : t.hero.primary}</a><a className="site-secondary" href={href('pricing', lang)}>{t.hero.secondary}</a></div>
      <p className="site-fine">{t.hero.caption}</p>
    </section>
    <section id="purpose" className="site-section" aria-labelledby="purpose-h">
      <h2 id="purpose-h">{t.purpose.title}</h2>
      {t.purpose.body.map(text => <p key={text}>{text}</p>)}
    </section>
    <section id="why" className="site-section site-alt" aria-labelledby="why-h">
      <h2 id="why-h">{t.whyTitle}</h2>
      <div className="site-grid">{CLAIMS.map(claim => <article key={claim.key}><h3>{claim[t.lang].t}</h3><p>{claim[t.lang].d}</p></article>)}</div>
    </section>
    <section id="how" className="site-section" aria-labelledby="how-h">
      <h2 id="how-h">{t.how.title}</h2>
      <ol className="site-steps">{t.how.steps.map(([title, text], index) => <li key={title}><span aria-hidden="true">{index + 1}</span><h3>{title}</h3><p>{text}</p></li>)}</ol>
    </section>
    <section id="plans" className="site-section site-alt" aria-labelledby="plans-h">
      <h2 id="plans-h">{t.plans.title}</h2><p>{t.plans.lead}</p>
      <PlanCards t={t} withCta={false}/>
      <p><a className="site-link" href={href('pricing', lang)}>{t.plans.cta} →</a></p>
    </section>
    <section id="limits" className="site-section" aria-labelledby="limits-h">
      <h2 id="limits-h">{t.limits.title}</h2>
      <ul className="site-list">{t.limits.items.map(item => <li key={item}>{item}</li>)}</ul>
    </section>
    <section id="faq" className="site-section site-alt" aria-labelledby="faq-h">
      <h2 id="faq-h">{t.faq.title}</h2>
      {t.faq.items.map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}
    </section>
  </>;
}

function Pricing({t}) {
  const methods = SITE.payment.methods;
  return <section className="site-page" aria-labelledby="pr-h">
    <h1 id="pr-h">{t.pricing.title}</h1><p className="site-lead">{t.pricing.lead}</p>
    <PlanCards t={t}/>
    <h2>{t.pricing.rulesTitle}</h2>
    <ul className="site-list">{t.pricing.rules.map(item => <li key={item}>{item}</li>)}</ul>
    <p className="site-fine">Free: {FREE_LIMITS.SESSION} / {t.lang === 'en' ? 'month' : 'bulan'} · {FREE_LIMITS.WINDOW} / {t.lang === 'en' ? 'day' : 'hari'} (UTC)</p>
    <h2>{t.pricing.payTitle}</h2>
    <p>{t.pricing.payLead}</p>
    {Array.isArray(methods) && methods.length > 0
      ? <><h3>{t.pricing.payMethods}</h3><ul className="site-list">{methods.map(item => <li key={item}>{item}</li>)}</ul></>
      : <p className="site-fine">{t.pricing.taxNone}</p>}
    {SITE.pro.taxNote && <p className="site-fine">{SITE.pro.taxNote}</p>}
  </section>;
}

function About({t}) {
  const b = SITE.business;
  return <section className="site-page" aria-labelledby="ab-h">
    <h1 id="ab-h">{t.about.title}</h1>
    {t.about.body.map(text => <p key={text}>{text}</p>)}
    <h2>{t.about.principlesTitle}</h2>
    <ul className="site-list">{t.about.principles.map(item => <li key={item}>{item}</li>)}</ul>
    <h2>{t.about.identityTitle}</h2>
    <dl className="site-facts">
      <dt>{t.lang === 'en' ? 'Name' : 'Nama'}</dt><dd>{b.legalName || '—'}</dd>
      {b.legalForm && <><dt>{t.lang === 'en' ? 'Form' : 'Bentuk usaha'}</dt><dd>{b.legalForm}</dd></>}
      {b.nib && <><dt>NIB</dt><dd>{b.nib}</dd></>}
      <dt>{t.contact.address}</dt><dd>{b.address || '—'}</dd>
      <dt>{t.contact.email}</dt><dd>{b.email ? <a href={`mailto:${b.email}`}>{b.email}</a> : '—'}</dd>
    </dl>
  </section>;
}

function Contact({t}) {
  const b = SITE.business;
  return <section className="site-page" aria-labelledby="ct-h">
    <h1 id="ct-h">{t.contact.title}</h1><p className="site-lead">{t.contact.lead}</p>
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
