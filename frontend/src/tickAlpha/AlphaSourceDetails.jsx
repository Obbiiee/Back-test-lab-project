// Presentation of already-authorized catalog / revealed-view fields only.
// No provider handles, unrestricted source metadata, EOF or future coverage.
import {stamp} from './display.js';

export default function AlphaSourceDetails({historical,catalog,view,onClose}) {
  return <section className="alpha-dialog">
    <div className="alpha-terminal-heading"><h2>Data source</h2><button onClick={onClose} aria-label="Close data source">Close</button></div>
    <p>{historical?'Thanks to Exness for the historical quote source used in this local research workspace.':'This workspace uses an authored synthetic fixture for engineering checks.'}</p>
    <dl className="alpha-reviewed-values">
      <div><dt>Instrument</dt><dd>XAUUSD · USD</dd></div>
      <div><dt>Source</dt><dd>{historical?'Exness · imported historical quotes':'Synthetic fixture'}</dd></div>
      <div><dt>Selected start month</dt><dd>{view?.metadata.startPeriod??catalog?.startPeriod??'Unavailable'}</dd></div>
      <div><dt>Revealed through (UTC)</dt><dd>{view?stamp(view.state.throughNs):'No Session selected'}</dd></div>
    </dl>
    <p>{historical?'Quote quality and ordering within equal timestamps are unverified. Missing or insufficient evidence remains unresolved; no intrabar path or fill is invented.':'Synthetic results test the application workflow and do not represent broker fills.'}</p>
    <p>Candles and indicators are research displays. Order execution uses observed Bid/Ask ticks. Unavailable months are refused without substituting a feed.</p>
    <p>This is a private local workspace. Source credit does not imply broker endorsement or permission to redistribute data on a public website.</p>
    <details><summary tabIndex={0}>Source disclosure</summary><p>{view?.label??catalog?.label??'Source unavailable'}</p></details>
  </section>;
}
