import ChartObjectOverlay from "../chart/ChartObjectOverlay";
import { isRiskReward } from "./RiskRewardController";
import RiskRewardGeometry from "./RiskRewardGeometry";

const renderGeometry = props => <RiskRewardGeometry {...props} />;
const isPriceOnlyAnchor = (_, index) => index === 1 || index === 2;
const handleProjection = points => {
  const entry = points[0], end = points[3]?.x ?? entry.x + 150;
  const x = entry.x + Math.max(20, end - entry.x);
  return points.map((point, index) => index === 1 || index === 2 ? { ...point, x } : point);
};

export default function RiskRewardLayer(props) {
  const mode = isRiskReward(props.drawingMode) || ["none", "cursor-dot", "cursor-arrow", "eraser"].includes(props.drawingMode)
    ? props.drawingMode : "none";
  return <ChartObjectOverlay {...props} drawingMode={mode} drawings={props.objects}
    renderGeometry={renderGeometry} isPriceOnlyAnchor={isPriceOnlyAnchor} handleProjection={handleProjection}
    layerName="Risk/Reward objects" layerClass={'risk-reward-layer ' + (mode !== props.drawingMode ? 'tool-active' : '')} />;
}
