import classicMark from '../assets/riksora-mark.png';
import './riksoraBrand.css';
import './alphaBrand.css';

// Playful RIKSORA marks (docs/design/RIKSORA_PLAYFUL_UI_PLAN.md §6). "C" (ribbon R) is the
// proposed product default; "A" (play R) and "B" (candle R) are owner-approved alternatives.
// The classic PNG mark stays available until the owner confirms the final mark.
const MARKS={
  A:<><rect width="100" height="100" rx="28" fill="#1378F5"/><path d="M35 29H54a14 14 0 0 1 0 28H35" fill="none" stroke="#FFFFFF" strokeWidth="14" strokeLinecap="round"/><rect x="26" y="22" width="17" height="56" rx="8.5" fill="#FFFFFF"/><path d="M56 66v18l17-9z" fill="#FFCE55" stroke="#FFCE55" strokeWidth="7" strokeLinejoin="round"/></>,
  B:<><rect width="100" height="100" rx="28" fill="#FFCE55"/><path d="M34.5 12v76" stroke="#061A3C" strokeWidth="4" strokeLinecap="round"/><path d="M40 30.5H55a12.5 12.5 0 0 1 0 25H42" fill="none" stroke="#061A3C" strokeWidth="13" strokeLinecap="round"/><path d="M50 60l20 20" stroke="#061A3C" strokeWidth="15" strokeLinecap="round"/><rect x="26" y="24" width="17" height="52" rx="6" fill="#061A3C"/><circle cx="77" cy="22" r="6" fill="#1378F5"/></>,
  C:<><rect width="100" height="100" rx="28" fill="#0C2655"/><path d="M33 31H54a13 13 0 0 1 0 26H44" fill="none" stroke="#1378F5" strokeWidth="14" strokeLinecap="round"/><rect x="24" y="24" width="18" height="54" rx="9" fill="#D9EAFE"/><path d="M50 60l20 19" stroke="#FFCE55" strokeWidth="18" strokeLinecap="round"/></>,
};

export function RiksoraMark({size=32,variant='C',className}){
  if(variant==='classic')return <img className={className} src={classicMark} alt="" width={size} height={size}/>;
  return <svg className={className} width={size} height={size} viewBox="0 0 100 100" aria-hidden="true" focusable="false">{MARKS[variant]||MARKS.C}</svg>;
}

export default function AlphaBrand({href,variant}){
  return <a className="alpha-brand" href={href} aria-label="Riksora Labs · Backtest Lab"><RiksoraMark variant={variant}/><span>RIKSORA <small>LABS / Backtest Lab</small></span></a>;
}
