// Segmented single choice (canvas "Quick | Plan · R:R", "Market | Limit | Stop").
// A radiogroup with roving focus: arrows move and select, like native radio buttons.
export default function Segmented({label,value,options,disabled=false,onChange,className=''}){
  const index=Math.max(0,options.findIndex(([key])=>key===value));
  const move=(event)=>{
    const step={ArrowRight:1,ArrowDown:1,ArrowLeft:-1,ArrowUp:-1}[event.key];
    if(!step||disabled)return;
    event.preventDefault();
    const next=(index+step+options.length)%options.length;
    onChange(options[next][0]);
    event.currentTarget.parentElement?.children[next]?.focus();
  };
  return <div className={`alpha-segmented ${className}`.trim()} role="radiogroup" aria-label={label} aria-disabled={disabled||undefined}>
    {options.map(([key,text],i)=><button type="button" role="radio" key={key} aria-checked={key===value} tabIndex={i===index?0:-1}
      disabled={disabled} onClick={()=>{if(key!==value)onChange(key);}} onKeyDown={move}>{text}</button>)}
  </div>;
}
