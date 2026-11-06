// Issue #21 C-08: performance and responsive QA in a real browser.
// Largest chart the API policy allows (512 revealed + one previous calendar
// month of 1m context = 45,152 candles, under the 50,000 display limit) + 100
// drawings + 16 indicators: load time,
// pan/zoom frame times, hover/hit-test latency, long tasks and JS heap; then
// 320/375/390/768/1024/1440 and phone landscape: no horizontal overflow,
// chart visible, tools reachable.
// Usage: start `npx vite --port 5179` in frontend/, then
//   node tests/qa/performance-qa.cjs <outDir> [baseUrl]
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-out', base = process.argv[3] || 'http://localhost:5179';
fs.mkdirSync(out, { recursive: true });
const results = [], metrics = {};
const step = (name, detail = '') => { results.push({ name, detail }); console.log('PASS', name, detail); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const TYPES = ['trend-line', 'rectangle', 'fibonacci-retracement', 'parallel-channel', 'regression-trend', 'fib-extension', 'ellipse', 'polyline', 'price-range', 'pitchfork', 'gann-fan', 'xabcd-pattern', 'text', 'brush'];
const COUNTS = { 'parallel-channel': 3, 'fib-extension': 3, pitchfork: 3, 'xabcd-pattern': 5, text: 1, polyline: 4, brush: 40 };

(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  const cdp = await page.context().newCDPSession(page); await cdp.send('Performance.enable');
  // Serve the real chart-history API contract: Dec 2024 at 1m in 512-candle pages.
  const monthStart = Date.UTC(2024, 11, 1) / 1000, monthEnd = Date.UTC(2025, 0, 1) / 1000, past = [];
  let price = 2600, seed = 11; const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  for (let t = monthStart; t < monthEnd; t += 60) { const o = price, c = Math.max(1, o + (rnd() - .5) * 2 + Math.sin(t / 7200) * .3); past.push({ time: t, open: o.toFixed(3), high: (Math.max(o, c) + rnd()).toFixed(3), low: (Math.min(o, c) - rnd()).toFixed(3), close: c.toFixed(3) }); price = c; }
  let pagesServed = 0;
  await page.context().route('http://127.0.0.1:5188/**', async route => {
    const cors = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'GET,POST,OPTIONS' };
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors });
    if (!route.request().url().endsWith('/chart-history')) return route.fulfill({ status: 503, headers: cors, contentType: 'application/json', body: JSON.stringify({ detail: 'QA: not served' }) });
    const { timeframe, offset } = JSON.parse(route.request().postData());
    const candles = timeframe === '1m' ? past.slice(offset, offset + 512) : [];
    const nextOffset = candles.length === 512 && offset + 512 < past.length ? offset + 512 : null;
    pagesServed++;
    return route.fulfill({ status: 200, headers: cors, contentType: 'application/json', body: JSON.stringify({ schemaVersion: 1, artifact: 'BTL-PAST-CHART-CONTEXT-1', datasetId: 'qa-dataset', datasetVersion: 'qa',
      startTime: monthStart, endTime: monthEnd, timeframe, priceBasis: 'EXACT_REVEALED_MID_DISPLAY_ONLY', volumeAvailable: false, coverage: 'UNKNOWN', executionAuthority: false, status: 'READY', candles, nextOffset }) });
  });
  const URL_BIG = base + '/tests/qa/terminal.html?objects=0&tf=1m&bars=512&history=1';
  const contextLoaded = () => page.waitForFunction(() => /Previous calendar month/.test(document.body.textContent), null, { timeout: 60000 });
  const heap = async () => { await cdp.send('HeapProfiler.collectGarbage'); return (await cdp.send('Performance.getMetrics')).metrics.find(m => m.name === 'JSHeapUsedSize').value / 1048576; };

  // Seed: one real drawing + one indicator through the UI to learn the storage keys.
  await page.goto(URL_BIG + '&reset=1'); await contextLoaded(); await sleep(800);
  const box = await page.locator('.candle-chart canvas').first().boundingBox();
  await page.getByLabel('Lines drawing tools').click(); await page.getByRole('button', { name: 'Horizontal Line', exact: true }).click();
  await page.mouse.click(box.x + 300, box.y + 200); await sleep(500);
  assert.equal(JSON.parse(await page.locator('.candle-chart').getAttribute('data-primitive-drawings')).length, 1);
  await page.getByRole('button', { name: 'Indicators', exact: true }).click(); await sleep(200);
  await page.getByRole('button', { name: 'Add SMA', exact: true }).click(); await sleep(200);
  await page.getByRole('button', { name: 'Close indicators' }).click(); await sleep(200);
  await page.evaluate(({ TYPES, COUNTS }) => {
    const dKey = Object.keys(localStorage).find(k => k.startsWith('backtest-drawing-manager-v2:'));
    const iKey = Object.keys(localStorage).find(k => k.startsWith('backtest-indicators-v1:'));
    const doc = JSON.parse(localStorage.getItem(dKey));
    const last = Date.UTC(2025, 0, 1) / 1000 + 511 * 60;
    for (let i = 0; doc.drawings.length < 100; i++) {
      const type = TYPES[i % TYPES.length], n = COUNTS[type] ?? 2, start = last - (40 + i * 7) * 60;
      const points = Array.from({ length: n }, (_, k) => ({ time: start + k * 60 * (type === 'brush' ? 1 : 12), price: 2580 + ((i * 13 + k * 29) % 120) }));
      doc.drawings.push({ id: 'perf-' + i, type, points, options: { color: '#58a6ff', lineWidth: 2 }, visible: true, locked: false, metadata: {}, ...(type === 'text' ? { text: 'Note ' + i } : {}) });
    }
    localStorage.setItem(dKey, JSON.stringify(doc));
    const ind = JSON.parse(localStorage.getItem(iKey));
    const set = ['SMA', 'EMA', 'BOLLINGER_BANDS', 'RSI', 'MACD', 'ATR', 'STOCHASTIC', 'SUPERTREND', 'ICHIMOKU', 'KELTNER', 'HMA', 'ADX', 'CCI', 'PSAR', 'PIVOTS', 'SQUEEZE'];
    ind.instances = set.map((type, i) => ({ id: 'perf-ind-' + i, type, parameters: {}, visible: true }));
    localStorage.setItem(iKey, JSON.stringify(ind));
  }, { TYPES, COUNTS });
  // Fill parameters with registry defaults by letting the app normalise: stored configs need full parameters.
  const loadStart = Date.now(); pagesServed = 0;
  await page.goto(URL_BIG);
  await page.waitForFunction(() => { const el = document.querySelector('.candle-chart'); return el && JSON.parse(el.getAttribute('data-primitive-drawings') || '[]').length >= 100; }, null, { timeout: 30000 });
  await contextLoaded(); await sleep(500);
  metrics.candles = past.length + 512; metrics.historyPages = pagesServed;
  metrics.loadMs = Date.now() - loadStart;
  const drawn = JSON.parse(await page.locator('.candle-chart').getAttribute('data-primitive-drawings')).length;
  const indicatorCount = await page.evaluate(() => JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k => k.startsWith('backtest-indicators-v1:')))).instances.length);
  assert.equal(drawn, 100); assert.equal(indicatorCount, 16);
  metrics.heapAfterLoadMB = Number((await heap()).toFixed(1));
  step(`${metrics.candles} candles + 100 drawings + 16 indicators loaded`, `${metrics.loadMs} ms incl. ${metrics.historyPages} API pages, heap ${metrics.heapAfterLoadMB} MB`);
  await page.screenshot({ path: `${out}/01-load-50k-100-drawings-16-indicators.png` });

  // Frame timing + long tasks during pan, zoom and hover.
  await page.evaluate(() => {
    window.__frames = []; window.__long = [];
    new PerformanceObserver(list => { for (const e of list.getEntries()) window.__long.push(e.duration); }).observe({ entryTypes: ['longtask'] });
    let last = performance.now(); const tick = now => { window.__frames.push(now - last); last = now; window.__raf = requestAnimationFrame(tick); }; window.__raf = requestAnimationFrame(tick);
  });
  const cx = box.x + box.width * .5, cy = box.y + box.height * .5;
  await page.mouse.move(cx, cy); await page.mouse.down();
  for (let i = 0; i < 60; i++) await page.mouse.move(cx - i * 6, cy + Math.sin(i / 6) * 10);
  await page.mouse.up();
  for (let i = 0; i < 10; i++) { await page.mouse.wheel(0, i % 2 ? 240 : -240); await sleep(40); }
  const hoverStart = Date.now();
  for (let i = 0; i < 120; i++) await page.mouse.move(box.x + 60 + i * 7, box.y + 120 + (i % 20) * 12);
  metrics.hoverMovesPerSec = Math.round(120 / ((Date.now() - hoverStart) / 1000));
  await sleep(300);
  const timing = await page.evaluate(() => { cancelAnimationFrame(window.__raf); const f = window.__frames.slice(2).sort((a, b) => a - b); return { frames: f.length, p50: f[Math.floor(f.length * .5)], p95: f[Math.floor(f.length * .95)], max: f.at(-1), longTasks: window.__long.length, longTaskMax: Math.max(0, ...window.__long) }; });
  Object.assign(metrics, { frameP50ms: Number(timing.p50.toFixed(1)), frameP95ms: Number(timing.p95.toFixed(1)), frameMaxMs: Number(timing.max.toFixed(1)), longTasks: timing.longTasks, longTaskMaxMs: Math.round(timing.longTaskMax) });
  metrics.heapAfterInteractionMB = Number((await heap()).toFixed(1));
  assert.ok(timing.p95 < 50, `p95 frame ${timing.p95} ms`);
  assert.ok(timing.max < 500, `no lock-up: worst frame ${timing.max} ms`);
  step('Pan, zoom and hover stay responsive', `frame p50 ${metrics.frameP50ms} ms · p95 ${metrics.frameP95ms} ms · max ${metrics.frameMaxMs} ms · long tasks ${metrics.longTasks} (max ${metrics.longTaskMaxMs} ms) · hover ${metrics.hoverMovesPerSec} moves/s`);

  // Selecting and dragging among 100 drawings: hit test + drag latency.
  const selStart = Date.now();
  await page.mouse.click(box.x + 300, box.y + 200); await sleep(100);
  metrics.selectMs = Date.now() - selStart;
  // Regression guard: selecting once re-ran every indicator over the full history (~14 s).
  assert.ok(metrics.selectMs < 1000, `select latency ${metrics.selectMs} ms`);
  step('Select among 100 drawings', `${metrics.selectMs} ms incl. 100 ms settle`);

  // Responsive sweep.
  const storageState = await page.context().storageState();
  for (const [name, viewport, touch] of [['320', { width: 320, height: 640 }, true], ['375', { width: 375, height: 812 }, true], ['390', { width: 390, height: 844 }, true],
    ['390-landscape', { width: 844, height: 390 }, true], ['768', { width: 768, height: 1024 }, true], ['1024', { width: 1024, height: 768 }, false], ['1440', { width: 1440, height: 900 }, false]]) {
    const p = await (await browser.newContext({ storageState, viewport, hasTouch: touch, isMobile: touch && viewport.width < 900, deviceScaleFactor: 1 })).newPage();
    p.on('pageerror', e => errors.push(name + ': ' + e.message));
    await p.goto(base + '/tests/qa/terminal.html?objects=0'); await sleep(1500);
    const overflow = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const chart = await p.locator('.candle-chart canvas').first().boundingBox();
    const rail = p.getByLabel('Lines drawing tools');
    const tools = await ((await rail.isVisible()) ? rail : p.getByRole('button', { name: 'Draw', exact: true })).boundingBox();
    assert.ok(overflow <= 0, `${name}: horizontal overflow ${overflow}px`);
    assert.ok(chart && chart.width > 150 && chart.height > 120, `${name}: chart visible`);
    assert.ok(tools && tools.x >= 0 && tools.x + tools.width <= viewport.width, `${name}: drawing tools reachable`);
    await p.screenshot({ path: `${out}/02-viewport-${name}.png` });
    step(`Viewport ${name}: no overflow, chart ${Math.round(chart.width)}×${Math.round(chart.height)}, tools reachable`);
    await p.context().close();
  }

  // C-14 mobile gate (record only, no pass threshold): the same 45k candles + 100 drawings +
  // 16 indicators reloaded at 390×844 with 4× CPU throttling. JS heap is measured after a
  // forced GC through CDP; there is no real low-memory device in this container.
  if (process.env.PERF_PHONE) {
    await page.setViewportSize({ width: 390, height: 844 });
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
    const phoneStart = Date.now();
    await page.reload(); await contextLoaded(); await sleep(1500);
    metrics.phoneLoadMs = Date.now() - phoneStart;
    metrics.phoneHeapAfterLoadMB = Number((await heap()).toFixed(1));
    const pbox = await page.locator('.candle-chart canvas').first().boundingBox();
    await page.evaluate(() => { window.__frames = []; let last = performance.now(); const tick = now => { window.__frames.push(now - last); last = now; window.__raf = requestAnimationFrame(tick); }; window.__raf = requestAnimationFrame(tick); });
    await page.mouse.move(pbox.x + pbox.width * .6, pbox.y + pbox.height * .5); await page.mouse.down();
    for (let i = 0; i < 30; i++) await page.mouse.move(pbox.x + pbox.width * .6 - i * 5, pbox.y + pbox.height * .5);
    await page.mouse.up(); await sleep(300);
    const pt = await page.evaluate(() => { cancelAnimationFrame(window.__raf); const f = window.__frames.slice(2).sort((a, b) => a - b); return { p50: f[Math.floor(f.length * .5)], p95: f[Math.floor(f.length * .95)], max: f.at(-1) }; });
    Object.assign(metrics, { phoneFrameP50ms: Number(pt.p50.toFixed(1)), phoneFrameP95ms: Number(pt.p95.toFixed(1)), phoneFrameMaxMs: Number(pt.max.toFixed(1)) });
    metrics.phoneHeapAfterPanMB = Number((await heap()).toFixed(1));
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 });
    await page.screenshot({ path: `${out}/03-phone-390-cpu4x.png` });
    step('Phone 390×844 at 4× CPU (record only)', `load ${metrics.phoneLoadMs} ms · heap ${metrics.phoneHeapAfterLoadMB} → ${metrics.phoneHeapAfterPanMB} MB · pan frame p50 ${metrics.phoneFrameP50ms} / p95 ${metrics.phoneFrameP95ms} / max ${metrics.phoneFrameMaxMs} ms`);
  }

  assert.deepEqual(errors, [], 'No page errors');
  fs.writeFileSync(`${out}/results.json`, JSON.stringify({ metrics, results, errors }, null, 2));
  await browser.close();
  console.log('metrics', JSON.stringify(metrics));
  console.log(`performance QA: ${results.length} steps passed`);
})().catch(e => { console.error(e); process.exit(1); });
