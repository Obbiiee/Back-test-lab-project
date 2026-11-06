// Terminal memory/frame profile (founder follow-up on PR #36, 2026-11-06).
// Matrix: 512 / 5,120 / 45,152 candles × 0 / 1 / 8 / 16 indicators, plus the phone
// case (390×844, 4× CPU throttle). For each cell: JS heap after a forced GC (CDP),
// load time, pan/zoom frame p50/p95/max, long tasks, and the number of points each
// indicator series hands to the chart. Real AlphaWorkspace through
// tests/qa/terminal.html; the chart-history API is answered in the browser by a
// LABELED synthetic generator (same contract as performance-qa.cjs). A simulated
// browser benchmark is not low-memory device certification.
// Usage: `npx vite --port 5179` in frontend/, then
//   node tests/qa/terminal-memory-profile.cjs <outDir> [baseUrl] [--quick]
const { chromium } = require('playwright');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-memory'; fs.mkdirSync(out, { recursive: true });
const base = process.argv[3] && !process.argv[3].startsWith('--') ? process.argv[3] : 'http://localhost:5179';
const quick = process.argv.includes('--quick');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const SET = ['SMA', 'EMA', 'BOLLINGER_BANDS', 'RSI', 'MACD', 'ATR', 'STOCHASTIC', 'SUPERTREND', 'ICHIMOKU', 'KELTNER', 'HMA', 'ADX', 'CCI', 'PSAR', 'PIVOTS', 'SQUEEZE'];

// Dec 2024 at 1m (44,640 candles) before the 512 revealed candles; LABELED synthetic.
const monthStart = Date.UTC(2024, 11, 1) / 1000, monthEnd = Date.UTC(2025, 0, 1) / 1000, past = [];
let price = 2600, seed = 11; const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
for (let t = monthStart; t < monthEnd; t += 60) { const o = price, c = Math.max(1, o + (rnd() - .5) * 2 + Math.sin(t / 7200) * .3); past.push({ time: t, open: o.toFixed(3), high: (Math.max(o, c) + rnd()).toFixed(3), low: (Math.min(o, c) - rnd()).toFixed(3), close: c.toFixed(3) }); price = c; }

(async () => {
  const browser = await chromium.launch({ args: ['--enable-precise-memory-info'] });
  const route = context => async (r, history) => {
    const cors = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'GET,POST,OPTIONS' };
    if (r.request().method() === 'OPTIONS') return r.fulfill({ status: 204, headers: cors });
    if (!r.request().url().endsWith('/chart-history')) return r.fulfill({ status: 503, headers: cors, contentType: 'application/json', body: '{"detail":"QA: not served"}' });
    const { timeframe, offset } = JSON.parse(r.request().postData());
    const source = past.slice(0, history); // a shorter context ends early (nextOffset null)
    const candles = timeframe === '1m' ? source.slice(offset, offset + 512) : [];
    const nextOffset = candles.length === 512 && offset + 512 < source.length ? offset + 512 : null;
    return r.fulfill({ status: 200, headers: cors, contentType: 'application/json', body: JSON.stringify({ schemaVersion: 1, artifact: 'BTL-PAST-CHART-CONTEXT-1', datasetId: 'qa-dataset', datasetVersion: 'qa',
      startTime: monthStart, endTime: monthEnd, timeframe, priceBasis: 'EXACT_REVEALED_MID_DISPLAY_ONLY', volumeAvailable: false, coverage: 'UNKNOWN', executionAuthority: false, status: 'READY', candles, nextOffset }) });
  };

  // Learn the storage keys through the UI (one SMA), like performance-qa. A historical
  // Session (?history=1) uses its own workspace key, so learn both.
  const learn = async history => {
    const seedCtx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const seedPage = await seedCtx.newPage();
    await seedCtx.route('http://127.0.0.1:5188/**', r => route(seedCtx)(r, 512));
    await seedPage.goto(base + `/tests/qa/terminal.html?objects=0&tf=1m&bars=512${history ? '&history=1' : ''}&reset=1`); await seedPage.waitForSelector('.candle-chart canvas'); await sleep(800);
    await seedPage.getByRole('button', { name: 'Indicators', exact: true }).click(); await sleep(200);
    await seedPage.getByRole('button', { name: 'Add SMA', exact: true }).click(); await sleep(300);
    const state = await seedCtx.storageState(); await seedCtx.close();
    const origin = state.origins.find(o => o.localStorage.some(i => i.name.startsWith('backtest-indicators-v1:')));
    return { origin, iKey: origin.localStorage.find(i => i.name.startsWith('backtest-indicators-v1:') && i.name.includes(history ? 'tick-historical' : 'tick-alpha')) };
  };
  const seeds = { plain: await learn(false), history: await learn(true) };

  const cell = async ({ candles, indicators, phone = false }) => {
    const history = candles - 512;
    const { origin, iKey } = history > 0 ? seeds.history : seeds.plain;
    const doc = JSON.parse(iKey.value); doc.instances = SET.slice(0, indicators).map((type, i) => ({ id: 'mem-ind-' + i, type, parameters: {}, visible: true }));
    const storageState = { cookies: [], origins: [{ origin: origin.origin, localStorage: origin.localStorage.map(i => i.name === iKey.name ? { name: i.name, value: JSON.stringify(doc) } : i) }] };
    const ctx = await browser.newContext({ storageState, viewport: phone ? { width: 390, height: 844 } : { width: 1440, height: 900 }, isMobile: phone, hasTouch: phone, deviceScaleFactor: 1 });
    await ctx.route('http://127.0.0.1:5188/**', r => route(ctx)(r, Math.max(history, 1)));
    const page = await ctx.newPage(); const errors = []; page.on('pageerror', e => errors.push(e.message));
    const cdp = await ctx.newCDPSession(page); await cdp.send('Performance.enable');
    if (phone) await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
    const heap = async () => { await cdp.send('HeapProfiler.collectGarbage'); return (await cdp.send('Performance.getMetrics')).metrics.find(m => m.name === 'JSHeapUsedSize').value / 1048576; };
    const t0 = Date.now();
    await page.goto(base + `/tests/qa/terminal.html?objects=0&tf=1m&bars=512${history > 0 ? '&history=1' : ''}`);
    await page.waitForSelector('.candle-chart canvas', { timeout: 60000 });
    if (history > 0) await page.waitForFunction(() => /Previous calendar month/.test(document.body.textContent), null, { timeout: 120000 });
    await sleep(500);
    const loadMs = Date.now() - t0;
    const heapLoad = await heap();
    const box = await page.locator('.candle-chart canvas').first().boundingBox();
    await page.evaluate(() => {
      window.__frames = []; window.__long = [];
      new PerformanceObserver(list => { for (const e of list.getEntries()) window.__long.push(e.duration); }).observe({ entryTypes: ['longtask'] });
      let last = performance.now(); const tick = now => { window.__frames.push(now - last); last = now; window.__raf = requestAnimationFrame(tick); }; window.__raf = requestAnimationFrame(tick);
    });
    const cx = box.x + box.width * .5, cy = box.y + box.height * .5;
    await page.mouse.move(cx, cy); await page.mouse.down();
    for (let i = 0; i < 60; i++) await page.mouse.move(cx + i * 6, cy + Math.sin(i / 6) * 10); // pan back into history
    await page.mouse.up();
    for (let i = 0; i < 10; i++) { await page.mouse.wheel(0, i % 2 ? 240 : -240); await sleep(40); }
    await sleep(300);
    const t = await page.evaluate(() => { cancelAnimationFrame(window.__raf); const f = window.__frames.slice(2).sort((a, b) => a - b); return { p50: f[Math.floor(f.length * .5)], p95: f[Math.floor(f.length * .95)], max: f.at(-1), longTasks: window.__long.length, longMax: Math.max(0, ...window.__long) }; });
    // Far pan: 20 long drags back into history, so a windowed series must re-slice.
    let far = null;
    if (candles > 5000) {
      await page.evaluate(() => { window.__frames = []; window.__long = []; let last = performance.now(); const tick = now => { window.__frames.push(now - last); last = now; window.__raf = requestAnimationFrame(tick); }; window.__raf = requestAnimationFrame(tick); });
      for (let k = 0; k < 20; k++) { await page.mouse.move(box.x + 20, cy); await page.mouse.down(); for (let i = 1; i <= 10; i++) await page.mouse.move(box.x + 20 + i * (box.width - 40) / 10, cy); await page.mouse.up(); }
      await sleep(300);
      far = await page.evaluate(() => { cancelAnimationFrame(window.__raf); const f = window.__frames.slice(2).sort((a, b) => a - b); return { p95: +f[Math.floor(f.length * .95)].toFixed(1), max: +f.at(-1).toFixed(1), longTasks: window.__long.length, longMax: Math.round(Math.max(0, ...window.__long)) }; });
    }
    const heapPan = await heap();
    const legend = await page.evaluate(() => { const k = Object.keys(localStorage).find(n => n.startsWith('backtest-indicators-v1:') && n.includes(location.search.includes('history=1') ? 'tick-historical' : 'tick-alpha')); return k ? JSON.parse(localStorage.getItem(k)).instances.length : 0; });
    if (legend !== indicators) errors.push(`instances ${legend} != ${indicators}`);
    await page.screenshot({ path: `${out}/${phone ? 'phone' : 'desk'}-${candles}-${indicators}.png` });
    await ctx.close();
    const row = { view: phone ? '390 · 4× CPU' : '1440', candles, indicators, heapLoadMB: +heapLoad.toFixed(1), heapAfterPanMB: +heapPan.toFixed(1), loadMs, frameP50: +t.p50.toFixed(1), frameP95: +t.p95.toFixed(1), frameMax: +t.max.toFixed(1), longTasks: t.longTasks, longTaskMaxMs: Math.round(t.longMax), rendered: legend, farPan: far, errors: errors.length };
    console.log(JSON.stringify(row));
    return row;
  };

  const rows = [];
  const candleSet = quick ? [512, 45152] : [512, 5120, 45152];
  const indicatorSet = quick ? [0, 16] : [0, 1, 8, 16];
  for (const candles of candleSet) for (const indicators of indicatorSet) rows.push(await cell({ candles, indicators }));
  for (const indicators of quick ? [16] : [8, 16]) rows.push(await cell({ candles: 45152, indicators, phone: true }));
  fs.writeFileSync(`${out}/memory-profile.json`, JSON.stringify(rows, null, 2));
  console.log('\n| View | Candles | Indicators | Heap load MB | Heap after pan MB | Load ms | Frame p50 / p95 / max ms | Long tasks (max ms) | Far pan p95 / max ms, long tasks (max) |');
  console.log('|---|---|---|---|---|---|---|---|---|');
  for (const r of rows) console.log(`| ${r.view} | ${r.candles} | ${r.indicators} | ${r.heapLoadMB} | ${r.heapAfterPanMB} | ${r.loadMs} | ${r.frameP50} / ${r.frameP95} / ${r.frameMax} | ${r.longTasks} (${r.longTaskMaxMs}) | ${r.farPan ? `${r.farPan.p95} / ${r.farPan.max}, ${r.farPan.longTasks} (${r.farPan.longMax})` : '—'} |`);
  await browser.close();
  if (rows.some(r => r.errors)) { console.log('page errors in some cells'); process.exit(1); }
})();
