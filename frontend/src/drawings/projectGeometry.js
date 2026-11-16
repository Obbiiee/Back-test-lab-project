import { HORIZONTAL_LINE, VERTICAL_LINE, RECTANGLE, REGRESSION_TREND } from './DrawingTypes.js';
import { regressionFit } from './professionalGeometry.js';
import { projectTimestamp } from './timeCoordinates.js';
export function projectGeometry(model, chart, series, bars) {
  if (!chart || !series) return [];
  const scale = chart.timeScale();
  if (model.type === HORIZONTAL_LINE) {
    const y = series.priceToCoordinate(model.points[0].price);
    const width = scale.width();
    return !Number.isFinite(y) || !Number.isFinite(width) ? [] : [{ x: 0, y }, { x: width, y }];
  }
  if (model.type === VERTICAL_LINE) {
    const x = projectTimestamp(scale, bars, model.points[0].time);
    const height = chart.paneSize().height;
    return !Number.isFinite(x) || !Number.isFinite(height) ? [] : [{ x, y: 0 }, { x, y: height }];
  }
  const points = model.points.map(p => {
    const x = projectTimestamp(scale, bars, p.time), y = series.priceToCoordinate(p.price);
    return !Number.isFinite(x) || !Number.isFinite(y) ? null : { x, y };
  });
  // Regression handles sit on the fitted line (revealed bars only); the stored
  // anchor price is not used for drawing.
  if (model.type === REGRESSION_TREND && points.every(Boolean)) {
    const fit = regressionFit(bars, model.points[0].time, model.points[1].time);
    if (fit) return points.map((point, i) => {
      const y = series.priceToCoordinate(fit.priceAt(model.points[i].time));
      return Number.isFinite(y) ? { x: point.x, y } : point;
    });
  }
  if (model.type === RECTANGLE && points.every(Boolean)) {
    const [a, b] = points;
    return [a, b, { x: b.x, y: a.y }, { x: a.x, y: b.y }];
  }
  return points;
}
