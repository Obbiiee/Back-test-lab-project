import mark from '../assets/riksora-mark.png';
import './alphaBrand.css';

export default function AlphaBrand({href}){
  return <a className="alpha-brand" href={href} aria-label="Riksora Labs · Backtest Lab"><img src={mark} alt="" width="32" height="32"/><span>RIKSORA <small>LABS / Backtest Lab</small></span></a>;
}
