// Presentation of already-authorized catalog / revealed-view fields only.
// No provider handles, unrestricted source metadata, EOF or future coverage.
import {stamp} from './display.js';

export default function AlphaSourceDetails({historical,account=false,catalog,view,onClose}) {
  const observed=view?.metadata.model==='CONDITIONAL_OBSERVED_TICK_SIMULATION';
  const selected=view?.metadata.period??view?.metadata.startPeriod??catalog?.startPeriod??'Unavailable';
  const configured=catalog?.datasets?.find(item=>item.key===view?.metadata.datasetKey);
  return <section className="alpha-dialog">
    <div className="alpha-terminal-heading"><h2>Data source</h2><button onClick={onClose} aria-label="Close data source">Close</button></div>
    <p>{observed?'This Session uses an operator-pinned historical Bid/Ask tick source. The selected month is bound to one immutable dataset version.':'This workspace uses an authored synthetic fixture for engineering checks.'}</p>
    <dl className="alpha-reviewed-values">
      <div><dt>Instrument</dt><dd>XAUUSD · USD</dd></div>
      <div><dt>Source</dt><dd>{observed?(configured?.label??view.label):historical?'Exness · imported historical quotes':'Synthetic fixture'}</dd></div>
      <div><dt>Selected period</dt><dd>{selected}</dd></div>
      <div><dt>Revealed through (UTC)</dt><dd>{view?stamp(view.state.throughNs):'No Session selected'}</dd></div>
    </dl>
    <p>{observed?'Source quality and rights are not established by successful structural admission. Quote quality and ordering within equal timestamps remain explicit; missing or insufficient evidence stays unresolved.':historical?'Historical source quality and rights are unverified. Missing or ambiguous quote evidence remains unresolved.':'Synthetic results test the application workflow and do not represent broker fills.'}</p>
    <p>Candles and indicators are research displays. Order execution uses observed Bid/Ask ticks. Unavailable months are refused without substituting a feed.</p>
    <p>{observed?'Source rights remain unverified. Source credit does not imply endorsement or permission to redistribute the data.':account?'This verified workspace uses the synthetic test feed; private local market files are not mounted.':'This is a private local workspace. Source credit does not imply broker endorsement or permission to redistribute data on a public website.'}</p>
    <details><summary tabIndex={0}>Source disclosure</summary><p>{view?.label??catalog?.label??'Source unavailable'}</p></details>
  </section>;
}
