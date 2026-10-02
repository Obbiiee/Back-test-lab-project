import assert from "node:assert/strict";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DRAWING_TOOLS, logicalAtTime, timeAtLogical, regression, anchoredVWAP, volumeProfile } from "../legacy/phase3/src/drawings/tools.js";

const irregular = [{ time: 100 }, { time: 160 }, { time: 400 }, { time: 460 }];
assert.equal(timeAtLogical(irregular, 2), 400);
assert.equal(logicalAtTime(irregular, 400), 2);
assert.equal(logicalAtTime(irregular, 280), 1.5);
assert.equal(timeAtLogical(irregular, 4), 520);
assert.equal(timeAtLogical(irregular, -1), 40);
assert.equal(logicalAtTime(irregular, 520), 4);
const trend = [10, 12, 14, 16].map((close, i) => ({ time: 100 + i * 60, open: close, close, high: close + 1, low: close - 1, volume: 100 }));
assert.deepEqual(regression(trend), { slope: 2, intercept: 10, deviation: 0 });
assert.equal(regression([]), null);
const weighted = anchoredVWAP(trend);
assert.equal(weighted[0].price, 10);
assert.equal(weighted.at(-1).price, 13);
assert.equal(anchoredVWAP(trend.map(bar => ({ ...bar, volume: 0 }))).length, 0);
assert.ok(Math.abs(volumeProfile(trend).reduce((sum, row) => sum + row.volume, 0) - 400) < 1e-9, "Profile must conserve total volume");
assert.deepEqual(volumeProfile([]), []);

const server = await createServer({ server: { middlewareMode: true }, appType: "custom" });
try {
  const { default: Geometry } = await server.ssrLoadModule("/legacy/phase3/src/components/DrawingGeometry.jsx");
  const bars = Array.from({ length: 100 }, (_, i) => ({ time: 100 + i * 60, open: 100 + Math.sin(i), close: 101 + Math.sin(i), high: 103 + Math.sin(i), low: 99 + Math.sin(i), volume: 100 + i }));
  const anchors = [10, 35, 50, 60, 70, 80, 85, 90].map((i, j) => ({ time: bars[i].time, price: 100 + (j % 2 ? 2 : -2) }));
  const project = point => ({ x: logicalAtTime(bars, point.time) * 7, y: 280 - (point.price - 95) * 20 });
  let count = 0;
  for (const tool of Object.values(DRAWING_TOOLS)) {
    if (tool.type.includes("position")) continue; // The position renderer lives in DrawingsLayer, checked in browser.
    const points = anchors.slice(0, tool.points <= 0 ? 5 : tool.points);
    const markup = renderToStaticMarkup(createElement(Geometry, { drawing: { type: tool.type, points, text: "Plan | Price\nEntry | 100" }, projected: points.map(project), project, candles: bars, width: 1000, height: 500 }));
    assert.ok(markup.length > 0, tool.name + " must have drawable geometry");
    assert.ok(!/NaN|Infinity|undefined/.test(markup), tool.name + " contains invalid geometry");
    if (tool.points >= 2) {
      const collapsed = Array.from({ length: tool.points }, () => ({ time: bars[10].time, price: 100 }));
      const flat = renderToStaticMarkup(createElement(Geometry, { drawing: { type: tool.type, points: collapsed }, projected: collapsed.map(project), project, candles: bars, width: 1000, height: 500 }));
      assert.ok(!/NaN|Infinity|undefined/.test(flat), tool.name + " must handle coincident anchors");
    }
    count++;
  }
  console.log("PASS: math, volume conservation, irregular time anchors, and geometry for " + count + " tools (including coincident anchors).");
} finally { await server.close(); }
