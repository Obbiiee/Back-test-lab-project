import { logicalAtTime, timeAtLogical } from '../chart/coordinates.js';

export const RISK_REWARD_TOOLS = {
  'long-position': { name: 'Long Position', type: 'long-position', points: 1, group: 'measure' },
  'short-position': { name: 'Short Position', type: 'short-position', points: 1, group: 'measure' },
};

export const isRiskReward = object => Object.hasOwn(RISK_REWARD_TOOLS, typeof object === 'string' ? object : object?.type);

// This store belongs to trading. It has no dependency on a drawing renderer or manager.
export class RiskRewardController {
  objects = [];

  replace(objects) { this.objects = objects.filter(isRiskReward); }
  get(id) { return this.objects.find(object => object.id === id); }

  create(type, point, pointer, series, candles, id) {
    if (!isRiskReward(type)) return null;
    const long = type === 'long-position';
    const stop = series.coordinateToPrice(pointer.y + (long ? 48 : -48));
    const target = series.coordinateToPrice(pointer.y + (long ? -96 : 96));
    if (stop == null || target == null) return null;
    const endTime = timeAtLogical(candles, logicalAtTime(candles, point.time) + 30);
    return { id, type, points: [point,
      { time: point.time, price: Number(stop) },
      { time: point.time, price: point.price + (point.price - Number(stop)) },
      { time: endTime, price: point.price },
    ] };
  }

  resize(object, index, point, candles) {
    const points = object.points.map(item => ({ ...item }));
    const long = object.type === 'long-position', entry = points[0];
    if (index === 1) point = { time: entry.time, price: long ? Math.min(entry.price - .001, point.price) : Math.max(entry.price + .001, point.price) };
    if (index === 2) point = { time: entry.time, price: long ? Math.max(entry.price + .001, point.price) : Math.min(entry.price - .001, point.price) };
    if (index === 3) point = { time: Math.max(timeAtLogical(candles, logicalAtTime(candles, entry.time) + 1), point.time), price: entry.price };
    if (index === 0) {
      const deltaPrice = point.price - entry.price;
      points.forEach(item => { item.price += deltaPrice; });
      points[1].time = point.time; points[2].time = point.time;
    }
    points[index] = point;
    return { ...object, points };
  }
}

export function normalizeRiskRewardSettings(object) {
  return { ...object, points: object.points.map((point, index) =>
    index === 1 || index === 2 ? { ...point, time: object.points[0].time }
      : index === 3 ? { ...point, price: object.points[0].price } : point) };
}
