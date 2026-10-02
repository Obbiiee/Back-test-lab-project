import { isRiskReward, RiskRewardController } from '../trading/RiskRewardController.js';

// Compatibility boundary for the existing toolbar, shared undo/redo and v2 JSON.
// Risk/Reward has its own owner; the legacy drawing runtime receives drawings only.
export class ChartObjectBridge {
  riskReward = new RiskRewardController();
  drawings = [];
  order = [];

  get objects() {
    return this.order.map(({ trading, index }) =>
      (trading ? this.riskReward.objects : this.drawings)[index]).filter(Boolean);
  }

  replace(objects) {
    this.drawings = objects.filter(object => !isRiskReward(object));
    this.riskReward.replace(objects);
    let drawingIndex = 0, tradingIndex = 0;
    this.order = objects.map(object => isRiskReward(object)
      ? { trading: true, index: tradingIndex++ } : { trading: false, index: drawingIndex++ });
  }
}
