import ChartObjectOverlay from "../chart/ChartObjectOverlay";
import { FREEHAND_TOOLS } from "../drawings/tools";
import { isRiskReward } from "../trading/RiskRewardController";
import DrawingGeometry from "./DrawingGeometry";

const isFreehand = type => FREEHAND_TOOLS.has(type);
const renderGeometry = props => <DrawingGeometry {...props} />;

export default function DrawingsLayer(props) {
  // Defensive boundary: legacy drawing lifecycle can never render a trading tool.
  return <ChartObjectOverlay {...props} drawings={props.drawings.filter(object => !isRiskReward(object))}
    drawingMode={isRiskReward(props.drawingMode) ? "none" : props.drawingMode}
    isFreehand={isFreehand} renderGeometry={renderGeometry} />;
}
