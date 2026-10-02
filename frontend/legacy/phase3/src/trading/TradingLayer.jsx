import TradingLevels from './TradingLevels';
import RiskRewardLayer from './RiskRewardLayer';

export default function TradingLayer({ positions, orders, onAmend, onClose, onCancel, onError, ...riskRewardProps }) {
  const { chart, series, drawingMode } = riskRewardProps;
  return <>
    {onAmend && ['none', 'cursor-dot', 'cursor-arrow'].includes(drawingMode) &&
      <TradingLevels chart={chart} series={series} positions={positions} orders={orders}
        onAmend={onAmend} onClose={onClose} onCancel={onCancel} onError={onError} />}
    <RiskRewardLayer {...riskRewardProps} />
  </>;
}
