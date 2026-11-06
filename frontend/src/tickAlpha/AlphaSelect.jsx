import {useEffect,useId,useMemo,useRef,useState} from 'react';

// SearchableSelect: one closed field instead of a permanent list of choices.
// ARIA 1.2 pattern: a trigger button opens a popover holding a search input
// (role=combobox, aria-activedescendant) and a listbox. On phones the popover
// becomes a bottom sheet (CSS only). Options are whatever the caller passes in:
// this component never invents availability.
//
// option: {value, label, description?, badge?, disabled?, disabledReason?, keywords?}
export function SearchableSelect({label,options,value,onChange,placeholder='Select',searchPlaceholder='Search…',
  loading=false,error=null,emptyText='Nothing matches your search.',noOptionsText='Nothing to choose yet.',
  clearable=false,disabled=false,hint=null,id:givenId}){
  const autoId=useId();const id=givenId||autoId;
  const [open,setOpen]=useState(false);
  const [query,setQuery]=useState('');
  const [active,setActive]=useState(0);
  const wrap=useRef(null),trigger=useRef(null),search=useRef(null),list=useRef(null);
  const selected=options.find(option=>option.value===value)||null;
  const filtered=useMemo(()=>{
    const q=query.trim().toLowerCase();
    if(!q)return options;
    return options.filter(option=>[option.label,option.description,option.value,...(option.keywords||[])].filter(Boolean).some(text=>String(text).toLowerCase().includes(q)));
  },[options,query]);
  const enabledIndex=(start,step)=>{
    if(!filtered.length)return -1;
    for(let i=0,at=start;i<filtered.length;i++,at=(at+step+filtered.length)%filtered.length)if(!filtered[at].disabled)return at;
    return -1;
  };
  const show=()=>{
    if(disabled)return;
    setQuery('');
    const current=options.findIndex(option=>option.value===value);
    setActive(current>=0?current:Math.max(0,options.findIndex(option=>!option.disabled)));
    setOpen(true);
  };
  const close=(refocus=true)=>{setOpen(false);if(refocus)trigger.current?.focus();};
  const choose=option=>{if(!option||option.disabled)return;onChange(option.value);close();};
  useEffect(()=>{if(open)search.current?.focus();},[open]);
  useEffect(()=>{
    if(!open)return undefined;
    const outside=event=>{if(wrap.current&&!wrap.current.contains(event.target))setOpen(false);};
    document.addEventListener('pointerdown',outside);
    return()=>document.removeEventListener('pointerdown',outside);
  },[open]);
  useEffect(()=>{
    if(!open)return;
    list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView?.({block:'nearest'});
  },[active,open]);
  const onKey=event=>{
    if(event.key==='ArrowDown'){event.preventDefault();setActive(index=>enabledIndex((index+1)%Math.max(1,filtered.length),1));}
    else if(event.key==='ArrowUp'){event.preventDefault();setActive(index=>enabledIndex((index-1+filtered.length)%Math.max(1,filtered.length),-1));}
    else if(event.key==='Home'){event.preventDefault();setActive(enabledIndex(0,1));}
    else if(event.key==='End'){event.preventDefault();setActive(enabledIndex(filtered.length-1,-1));}
    else if(event.key==='Enter'){event.preventDefault();choose(filtered[active]);}
    else if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close();}
    else if(event.key==='Tab')close(false);
  };
  const listId=`${id}-list`,labelId=`${id}-label`;
  return <div className={`rk-combo${open?' is-open':''}`} ref={wrap}>
    <span className="rk-combo-label" id={labelId}>{label}</span>
    <div className="rk-combo-field">
      <button ref={trigger} type="button" id={id} className="rk-combo-trigger" aria-haspopup="listbox" aria-expanded={open} aria-labelledby={`${labelId} ${id}`} disabled={disabled}
        onClick={()=>open?close():show()} onKeyDown={event=>{if(!open&&(event.key==='ArrowDown'||event.key==='ArrowUp')){event.preventDefault();show();}}}>
        {selected?<span className="rk-combo-value"><strong>{selected.label}</strong>{selected.description&&<small>{selected.description}</small>}</span>:<span className="rk-combo-placeholder">{loading?'Loading…':placeholder}</span>}
        <span className="rk-combo-chevron" aria-hidden="true">▾</span>
      </button>
      {clearable&&selected&&!disabled&&<button type="button" className="rk-combo-clear" aria-label={`Clear ${label}`} onClick={()=>{onChange(null);trigger.current?.focus();}}>×</button>}
    </div>
    {hint&&<span className="rk-combo-hint">{hint}</span>}
    {open&&<>
      <div className="rk-combo-backdrop" aria-hidden="true" onClick={()=>close()}/>
      <div className="rk-combo-panel" role="dialog" aria-label={label}>
        <span className="rk-combo-handle" aria-hidden="true"/>
        <div className="rk-combo-search"><span aria-hidden="true">⌕</span>
          <input ref={search} role="combobox" aria-expanded="true" aria-controls={listId} aria-autocomplete="list" aria-label={`Search ${label}`}
            aria-activedescendant={filtered[active]?`${id}-opt-${active}`:undefined} placeholder={searchPlaceholder} value={query}
            onChange={event=>{setQuery(event.target.value);setActive(0);}} onKeyDown={onKey} autoComplete="off" spellCheck={false}/>
        </div>
        {loading?<p className="rk-combo-note" role="status">Loading…</p>
          :error?<p className="rk-combo-note is-error" role="alert">{error}</p>
          :!options.length?<p className="rk-combo-note" role="status">{noOptionsText}</p>
          :!filtered.length?<p className="rk-combo-note" role="status">{emptyText}</p>
          :<ul ref={list} id={listId} role="listbox" aria-labelledby={labelId} className="rk-combo-list">
            {filtered.map((option,index)=><li key={option.value} id={`${id}-opt-${index}`} data-index={index} role="option" aria-selected={option.value===value} aria-disabled={option.disabled||undefined}
              className={`${index===active?'is-active':''}${option.disabled?' is-disabled':''}`} onMouseEnter={()=>!option.disabled&&setActive(index)} onClick={()=>choose(option)}>
              <span className="rk-combo-opt-text"><strong>{option.label}</strong>{(option.disabled&&option.disabledReason||option.description)&&<small>{option.disabled&&option.disabledReason?option.disabledReason:option.description}</small>}</span>
              {option.badge&&<span className="rk-combo-opt-badge">{option.badge}</span>}
              {option.value===value&&<span className="rk-combo-opt-check" aria-hidden="true">✓</span>}
            </li>)}
          </ul>}
      </div>
    </>}
  </div>;
}

// Instruments come only from the server catalog profile. Today the catalog
// publishes exactly one instrument per workspace; more appear when Codex
// publishes a catalog-availability route.
export function InstrumentPicker({catalog,value,onChange,disabled}){
  const profile=catalog?.profile;
  const options=profile?[{value:profile.instrumentId,label:profile.instrumentId,description:`${catalog.label==='SYNTHETIC / TEST ONLY'?'Synthetic test feed':'Historical quotes'} · ${profile.quoteCurrency} account`,badge:'Available',keywords:[profile.feedInstrumentId,profile.providerId]}]:[];
  return <SearchableSelect label="Trading instrument" placeholder="Search or select instrument" searchPlaceholder="Search instruments…" options={options} value={value} onChange={onChange} disabled={disabled}
    noOptionsText="The server has not published any instrument for this workspace." hint="Only instruments the server confirms for this workspace are listed."/>;
}

export function MethodPicker({methods,value,onChange,label='Method',clearable=false,placeholder='Search or select Method',disabled}){
  const options=methods.map(method=>({value:method.id,label:method.name,description:method.kind==='PROTOCOL'?`Protocol · risk ${method.riskPercent}% · R:R ${method.rr}`:'Free Style',keywords:[method.kind]}));
  return <SearchableSelect label={label} placeholder={placeholder} searchPlaceholder="Search Methods…" options={options} value={value} onChange={onChange} clearable={clearable} disabled={disabled}
    noOptionsText="No Methods yet. Create one first."/>;
}
