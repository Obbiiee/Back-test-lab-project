import {useEffect,useId,useMemo,useRef,useState} from 'react';

// SearchableSelect: one closed field instead of a permanent list of choices.
// ARIA 1.2 pattern: a trigger button opens a popover holding a search input
// (role=combobox, aria-activedescendant) and a listbox. On phones the popover
// becomes a modal bottom sheet: backdrop, Close button, focus kept inside, page
// scroll locked. Options are whatever the caller passes in: this component never
// invents availability. The active option is always an enabled one (or none).
const SHEET='(max-width: 760px)';
//
// option: {value, label, description?, badge?, disabled?, disabledReason?, keywords?}
export function SearchableSelect({label,options,value,onChange,placeholder='Select',searchPlaceholder='Search…',
  loading=false,error=null,emptyText='Nothing matches your search.',noOptionsText='Nothing to choose yet.',
  clearable=false,disabled=false,hint=null,id:givenId}){
  const autoId=useId();const id=givenId||autoId;
  const [open,setOpen]=useState(false);
  const [query,setQuery]=useState('');
  const [active,setActive]=useState(-1);
  const [sheet,setSheet]=useState(false);
  const wrap=useRef(null),trigger=useRef(null),search=useRef(null),list=useRef(null),closer=useRef(null);
  const selected=options.find(option=>option.value===value)||null;
  const filtered=useMemo(()=>{
    const q=query.trim().toLowerCase();
    if(!q)return options;
    return options.filter(option=>[option.label,option.description,option.value,...(option.keywords||[])].filter(Boolean).some(text=>String(text).toLowerCase().includes(q)));
  },[options,query]);
  // Guard: a stale or disabled index (after typing, or new options) falls back to the first enabled match.
  const firstEnabled=filtered.findIndex(option=>!option.disabled);
  const current=filtered[active]&&!filtered[active].disabled?active:firstEnabled;
  const enabledIndex=(start,step)=>{
    if(!filtered.length)return -1;
    for(let i=0,at=start;i<filtered.length;i++,at=(at+step+filtered.length)%filtered.length)if(!filtered[at].disabled)return at;
    return -1;
  };
  const show=()=>{
    if(disabled)return;
    setQuery('');
    const chosen=options.findIndex(option=>option.value===value&&!option.disabled);
    setActive(chosen);
    setSheet(Boolean(globalThis.matchMedia?.(SHEET).matches));
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
  // Phone sheet is modal: lock page scroll behind it and restore on close.
  useEffect(()=>{
    if(!open||!sheet)return undefined;
    const body=document.body,previous=body.style.overflow;
    body.style.overflow='hidden';
    return()=>{body.style.overflow=previous;};
  },[open,sheet]);
  useEffect(()=>{
    if(!open||current<0)return;
    list.current?.querySelector(`[data-index="${current}"]`)?.scrollIntoView?.({block:'nearest'});
  },[current,open]);
  const onKey=event=>{
    const length=Math.max(1,filtered.length);
    if(event.key==='ArrowDown'){event.preventDefault();setActive(enabledIndex(current<0?0:(current+1)%length,1));}
    else if(event.key==='ArrowUp'){event.preventDefault();setActive(enabledIndex(current<0?length-1:(current-1+length)%length,-1));}
    else if(event.key==='Home'){event.preventDefault();setActive(enabledIndex(0,1));}
    else if(event.key==='End'){event.preventDefault();setActive(enabledIndex(filtered.length-1,-1));}
    else if(event.key==='Enter'){event.preventDefault();if(current>=0)choose(filtered[current]);}
  };
  // Escape anywhere in the panel closes; Tab closes the desktop popover but stays inside the phone sheet.
  const onPanelKey=event=>{
    if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close();}
    else if(event.key==='Tab'){
      if(!sheet){close(false);return;}
      event.preventDefault();
      (document.activeElement===search.current?closer.current:search.current)?.focus();
    }
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
      <div className={`rk-combo-panel${sheet?' is-sheet':''}`} role="dialog" aria-label={label} aria-modal={sheet||undefined} onKeyDown={onPanelKey}>
        <span className="rk-combo-handle" aria-hidden="true"/>
        {sheet&&<div className="rk-combo-sheet-head"><strong>{label}</strong><button ref={closer} type="button" className="rk-combo-close" onClick={()=>close()}>Close</button></div>}
        <div className="rk-combo-search"><span aria-hidden="true">⌕</span>
          <input ref={search} role="combobox" aria-expanded="true" aria-controls={listId} aria-autocomplete="list" aria-label={`Search ${label}`}
            aria-activedescendant={current>=0?`${id}-opt-${current}`:undefined} placeholder={searchPlaceholder} value={query}
            onChange={event=>{setQuery(event.target.value);setActive(-1);}} onKeyDown={onKey} autoComplete="off" spellCheck={false}/>
        </div>
        {loading?<p className="rk-combo-note" role="status">Loading…</p>
          :error?<p className="rk-combo-note is-error" role="alert">{error}</p>
          :!options.length?<p className="rk-combo-note" role="status">{noOptionsText}</p>
          :!filtered.length?<p className="rk-combo-note" role="status">{emptyText}</p>
          :<ul ref={list} id={listId} role="listbox" aria-labelledby={labelId} className="rk-combo-list">
            {filtered.map((option,index)=><li key={option.value} id={`${id}-opt-${index}`} data-index={index} role="option" aria-selected={option.value===value} aria-disabled={option.disabled||undefined}
              className={`${index===current?'is-active':''}${option.disabled?' is-disabled':''}`} onMouseEnter={()=>!option.disabled&&setActive(index)} onClick={()=>choose(option)}>
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
