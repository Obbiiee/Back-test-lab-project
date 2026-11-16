import {spreadLabel} from './display.js';

// Chart legend: the latest revealed candle (display only, exact wire strings) and the observed
// Bid / Ask / spread at the replay cursor. It makes the execution basis visible: orders fill on
// the Bid/Ask ticks shown here, not on candle prices.
export default function AlphaLegend({view}){
  const bar=view.chart.candles.at(-1),quote=view.quote;
  const spread=quote?spreadLabel(quote.bid,quote.ask):null;
  const up=bar&&Number(bar.close)>=Number(bar.open);
  return <div className="alpha-legend" aria-label="Latest revealed candle and observed quote">
    {bar?<span className={`alpha-legend-ohlc ${up?'is-up':'is-down'}`}><i>O</i>{bar.open}<i>H</i>{bar.high}<i>L</i>{bar.low}<i>C</i>{bar.close}{bar.incomplete&&<em>forming</em>}</span>:<span className="alpha-legend-ohlc">No revealed candle yet</span>}
    <span className="alpha-legend-quote" title="Orders fill on these observed ticks, never on candle prices"><i>Bid</i>{quote?.bid??'—'}<i>Ask</i>{quote?.ask??'—'}{spread!==null&&<><i>Spr</i>{spread}</>}</span>
  </div>;
}
