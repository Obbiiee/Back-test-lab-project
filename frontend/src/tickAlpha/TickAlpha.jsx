import '../workspace/designTokens.css';
import {useEffect,useRef,useState} from 'react';
import WorkspaceModal from '../workspace/WorkspaceModal.jsx';
import AlphaReviewSheet from './AlphaReviewSheet.jsx';
import AlphaPickTicket from './AlphaPickTicket.jsx';
import {api,id,sessionPath,selectSessionUrl,loadResearchContext,loadProductCatalog,loadMoreProductCatalog,noticeText,sourceContext,pagePath,sessionsPath} from './client.js';
import {command} from './client.js';
import {sessionInstrument} from './display.js';
import AlphaWorkspace from './AlphaWorkspace.jsx';
import AlphaBrand,{RiksoraMark} from './AlphaBrand.jsx';
import AlphaSessionWizard from './AlphaSessionWizard.jsx';
import AlphaJournalPage from './AlphaJournalPage.jsx';
import {SessionsPage,SessionOverview,CatalogPage} from './AlphaSessionPages.jsx';
import AlphaTicketEstimate from './AlphaTicketEstimate.jsx';
import {targetForRR} from './orderEstimate.js';
import AlphaTerminal from './AlphaTerminal.jsx';
import AlphaJournal from './AlphaJournal.jsx';
import AlphaSourceDetails from './AlphaSourceDetails.jsx';
import AlphaFeedback from './AlphaFeedback.jsx';
import {emitLocal} from './measurement.js';
import Icon from '../workspace/WorkspaceIcon.jsx';
import {DirectionQuotes} from './AlphaOrderPresentation.jsx';
import {planningIntent} from './planningIntent.js';
import Segmented from './AlphaSegmented.jsx';
import AlphaShell,{StatePanel} from './AlphaShell.jsx';
import {MyMethods,MethodNew,MethodOverview,Analytics,Placeholder} from './AlphaProduct.jsx';
import {HelpPage,LocalAccountPage} from './AlphaHelp.jsx';
import {rememberSession} from './productData.js';
import {useRoute,navigate,linkTo,accountLink,setLeaveGuard} from './productRoute.js';
import {classifyConfirmError,committedReceipt,classifyCommandResult,UNKNOWN_TEXT} from './confirmOutcome.js';
import './tickAlpha.css';
import {isAccountPage} from './accountClient.js';

const initialPlan=view=>({side:'LONG',orderType:'MARKET',workflow:'QUICK',entry:view?.quote?.ask??'2000',sl:view?.replayStepNs?'':'1998',tp:view?.replayStepNs?'':'2004',
  quantity:'0.1',riskPercent:'1',observations:[]});

export default function TickAlpha(){
  const [catalog,setCatalog]=useState(null),[view,setView]=useState(null),[busy,setBusy]=useState(false);
  const [objectsOpen,setObjectsOpen]=useState(false),[terminalRequest,setTerminalRequest]=useState(null);
  const [notice,setNotice]=useState(''),[dialog,setDialog]=useState(null),[review,setReview]=useState(null);
  const [plan,setPlan]=useState(initialPlan),[planRevision,setPlanRevision]=useState(0);
  const [picked,setPicked]=useState(null);
  // Identity of a confirmation with no definitive answer (see confirmOutcome.js).
  const [unverified,setUnverified]=useState(null);
  const flight=useRef(false),returnFocus=useRef(null);
  const [connecting,setConnecting]=useState(true);
  const creationId=useRef(null);
  const [timeframe,setTimeframe]=useState('1m'),[pauseToken,setPauseToken]=useState(0);
  const [orderAction,setOrderAction]=useState(null);
  const [selectedMethod,setSelectedMethod]=useState('');
  const [createError,setCreateError]=useState(null);
  const route=useRoute();
  const showWorkspace=Boolean(view&&route.screen==='replay'&&route.session===view.metadata.id);
  const loadWorkspace=(session,tf=timeframe)=>api(sessionPath(session)+'/view',{timeframe:tf});
  // Opening a Session starts at the chart, not wherever the Sessions list was scrolled to.
  const openedSession=view?.metadata.id;
  const mainRef=useRef(null);
  useEffect(()=>{if(!openedSession)return;globalThis.scrollTo?.(0,0);mainRef.current?.scrollTo?.(0,0);},[openedSession]);
  useEffect(()=>{
    let mounted=true;
    (async()=>{try{
      const selected=new URL(window.location.href).searchParams.get('session');
      const result=await loadResearchContext(selected,{active:()=>mounted});
      if(result){setCatalog(result.catalog);setView(result.view);emitLocal('workspace_opened');}
    }catch(error){if(mounted)setNotice(error.message);}finally{if(mounted)setConnecting(false);}})();
    return ()=>{mounted=false;};
  },[]);
  const run=async action=>{
    if(flight.current)return;
    flight.current=true;setBusy(true);setNotice('');
    try{return await action()??true;}catch(error){setNotice(error.message);return false;}finally{flight.current=false;setBusy(false);}
  };
  const reopen=async (session,{push=true}={})=>{
    setPauseToken(n=>n+1);
    const saved=await loadWorkspace(session);setView(saved);setSelectedMethod(saved.method.id);rememberSession(session);if(push)navigate({screen:'replay',session});else selectSessionUrl(session);setReview(null);setDialog(null);setOrderAction(null);
    setPlan(initialPlan(saved));setPlanRevision(0);
    setNotice('Session reopened from its committed state.');
    emitLocal('session_restored');
  };
  useEffect(()=>{
    if(!catalog||route.screen!=='replay'||!route.session||view?.metadata.id===route.session)return;
    let live=true;
    Promise.resolve().then(()=>{if(live)run(()=>reopen(route.session,{push:false}));});
    return()=>{live=false;};
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[catalog,route.screen,route.session]);
  const edit=patch=>{setPlan(p=>({...p,...patch}));setPlanRevision(r=>r+1);setReview(null);};
  // Buy/Sell in the order bar only preselect the side; review and confirmation stay mandatory.
  const openTicket=(event,side)=>{returnFocus.current=event.currentTarget;setNotice('');setPauseToken(n=>n+1);if(side&&side!==plan.side)edit({side,...(plan.workflow==='PLANNED'&&plan.orderType==='MARKET'?{entry:quoteFor(side)}:{})});setDialog('ticket');};
  const quoteFor=side=>(side==='LONG'?view?.quote?.ask:view?.quote?.bid)??plan.entry;
  const protocol=view?.method.kind==='PROTOCOL';
  const planned=protocol||plan.workflow==='PLANNED';
  const openSource=event=>{returnFocus.current=event.currentTarget;setPauseToken(n=>n+1);setDialog('source');emitLocal('feature_source');};
  const openReview=()=>{return run(async()=>{
    setPauseToken(n=>n+1);
    const draft={...plan,workflow:planned?'PLANNED':'QUICK',orderType:protocol&&plan.orderType==='MARKET'?'LIMIT':plan.orderType,
      ...(protocol?{tp:null,riskPercent:null,quantity:null}:{}),
      ...(!protocol&&planned?{quantity:null}:{}),
      ...(!planned?{sl:null,tp:null}:{}),
      observations:protocol?view.method.conditions.map(c=>({conditionId:c.id,outcome:plan.observations.find(o=>o.conditionId===c.id)?.outcome||'NOT_ASSESSED'})):[]};
    const request=await api('/reviews',{sessionId:view.metadata.id,requestId:id('order'),expectedRevision:view.state.revision,
      planId:planned?id('plan'):null,planRevision:planned?planRevision:null,draft});
    setReview(request);setDialog('review');
  });};
  // Confirm returns an outcome, not a boolean (confirmOutcome.js). The POST result and
  // the Session refresh are separate: a failed refresh after a commit stays COMMITTED.
  // An UNKNOWN outcome keeps this review's identity in `unverified`, locks new orders
  // and is settled only by a read-only Session check, never by re-sending.
  const confirm=async()=>{
    if(flight.current)return {outcome:'NOT_SENT',code:'LOCAL_BUSY'};
    const sessionId=view.metadata.id,command=review.review.command;
    const identity={sessionId,commandId:command.commandId,expectedRevision:command.expectedRevision,reviewHash:review.reviewHash};
    flight.current=true;setBusy(true);setNotice('');
    // While the confirmation is in flight, in-app navigation and Back are held and
    // a page unload asks first; the sheet says to keep it open.
    const unload=event=>{event.preventDefault();event.returnValue='';};
    const leave=setLeaveGuard(()=>false);window.addEventListener('beforeunload',unload);
    const release=()=>{leave();window.removeEventListener('beforeunload',unload);};
    try{
      let result;
      try{result=await api(sessionPath(sessionId)+'/confirm',{reviewId:command.commandId,reviewHash:review.reviewHash});}
      catch(error){
        const outcome=classifyConfirmError(error);
        if(outcome.outcome==='UNKNOWN'){setUnverified(identity);return {...outcome,identity};}
        return outcome;
      }
      if(!committedReceipt(result,command.commandId)){setUnverified(identity);return {outcome:'UNKNOWN',code:'UNRECOGNISED_RESPONSE',identity};}
      emitLocal('order_command_submitted');
      return await refreshAfterCommit(sessionId);
    }finally{release();flight.current=false;setBusy(false);}
  };
  const refreshAfterCommit=async sessionId=>{
    try{setView(await loadWorkspace(sessionId));}
    catch{setNotice('Order saved. The Session view could not refresh; reload the Session to see it.');return {outcome:'COMMITTED',refreshed:false};}
    setDialog(null);setReview(null);
    setNotice('Order accepted and saved. A fill requires the next eligible tick.');
    return {outcome:'COMMITTED',refreshed:true};
  };
  // Read-only: GET the durable receipt/status for this exact reviewed command.
  // The sheet passes the identity from confirm()'s result for its immediate check,
  // before this state has re-rendered.
  const checkUnverified=async(pending=unverified)=>{
    if(!pending||flight.current)return {outcome:'UNKNOWN',code:'LOCAL_BUSY'};
    flight.current=true;setBusy(true);
    try{
      let status;
      try{status=await api(`${sessionPath(pending.sessionId)}/commands/${encodeURIComponent(pending.commandId)}`);}
      catch(error){setNotice('The durable command result could not be read, so the order status is still not verified. Check again in a moment.');return {outcome:'UNKNOWN',code:error.message};}
      const found=classifyCommandResult(status,pending);
      if(found.outcome==='UNKNOWN'){setNotice('The server has not established a durable result yet. Check again in a moment; nothing was sent again.');return found;}
      setUnverified(null);
      if(found.outcome==='REFUSED'){setNotice('The earlier confirmation was not committed: the reviewed Session revision advanced first.');return {...found,reconciled:true};}
      emitLocal('order_command_submitted');
      return {...await refreshAfterCommit(pending.sessionId),reconciled:true};
    }finally{flight.current=false;setBusy(false);}
  };
  // Instrument comes from the Session's pinned profile; without it, orders stay locked.
  const instrument=sessionInstrument(view);
  const symbolText=instrument?.symbol??'Instrument not stated';
  const symbolGlyph=instrument?(instrument.symbol.startsWith('XAU')?'Au':instrument.symbol.slice(0,2)):'?';
  const orderLocked=busy||Boolean(view?.state.unresolved)||Boolean(unverified)||Boolean(view&&!instrument);
  const requestAction=(order,kind,quantity=null)=>{
    returnFocus.current=document.activeElement;setNotice('');
    const payload={orderId:order.id,...(kind==='CLOSE'?{quantity}:{})};
    setPauseToken(n=>n+1);setOrderAction({order,kind,quantity,command:command(view,kind,payload)});setDialog('action');
  };
  const confirmAction=()=>run(async()=>{
    await api(sessionPath(view.metadata.id)+'/commands',orderAction.command);
    setDialog(null);setOrderAction(null);
    // The command is committed once the POST succeeds; a failed refresh must not read as a failed action.
    try{setView(await loadWorkspace(view.metadata.id));}
    catch{setNotice(`${orderAction.kind==='CANCEL'?'Cancellation':'Exit request'} saved. The Session view could not refresh; reload the Session to see it.`);return;}
    setNotice(orderAction.kind==='CANCEL'?'Pending order cancellation committed.':'Exit requested. Actual closure needs the next eligible liquidation-side tick.');
  });
  // Called by the New Session wizard with the same POST /sessions payload the old dialog sent.
  const createSession=fields=>{
    if(!creationId.current)creationId.current=id('session');
    setCreateError(null);
    run(async()=>{
     try{
      const saved=await api('/sessions',{id:creationId.current,name:fields.name,methodId:fields.methodId,
        initialBalance:fields.initialBalance,startPeriod:fields.startPeriod??catalog.startPeriod});
      const workspace=await loadWorkspace(saved.metadata.id);
      setCatalog(await loadProductCatalog());setView(workspace);rememberSession(saved.metadata.id);navigate({screen:'replay',session:saved.metadata.id});setDialog(null);creationId.current=null;setPlan(initialPlan(workspace));setPlanRevision(0);
      setNotice('Session saved. The chart begins with observed history; orders use subsequent quotes.');
     }catch(error){setCreateError({code:error.message,text:noticeText(error.message)});return false;}
    });
  };
  const loadMoreCatalog=kind=>run(async()=>{
    setCatalog(await loadMoreProductCatalog(catalog,kind));
  });
  const openCreation=(type,event)=>{
    returnFocus.current=event.currentTarget;setNotice('');setPauseToken(n=>n+1);
    if(type==='method'){navigate({screen:'method-new'});return;}
    creationId.current=id('session');navigate({screen:'session-new',method:selectedMethod||view?.method.id});
  };
  const sessionMenu=<details className="alpha-session-menu"><summary>Session settings</summary>    <section className="alpha-context" aria-label="Method and Session">
      <button disabled={busy||!catalog} onClick={event=>openCreation('method',event)}>New Method</button>
      <button disabled={busy||!catalog?.methods.length} onClick={event=>openCreation('session',event)}>Create Session</button>
      <label>Reopen Session<select aria-label="Reopen Session" disabled={busy||!catalog} value={view?.metadata.id||''} onChange={e=>{if(e.target.value)run(()=>reopen(e.target.value));}}>
        <option value="">Choose saved Session</option>{catalog?.sessions.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      {view&&<><span>{view.method.name} · {view.method.kind==='PROTOCOL'?'Protocol':'Free Style'}</span><button disabled={busy} onClick={()=>run(()=>reopen(view.metadata.id))}>Reload saved Session</button></>}
    </section>
</details>;
  return <main ref={mainRef} className={`tick-alpha${showWorkspace?' has-workspace':' has-product'}`} onClickCapture={event=>{
    if(event.target.closest?.('nav[aria-label="Drawing tools"] button'))emitLocal('feature_drawing');
    if(event.target.closest?.('button')?.textContent==='Indicators')emitLocal('feature_indicator');
  }}>
    {showWorkspace&&<header><div className="alpha-workspace-brand"><AlphaBrand href={pagePath('home')}/><span className="alpha-badge">{isAccountPage()?'Verified workspace':'Private local workspace'}</span></div><nav aria-label="Workspace navigation">{view&&<a href={sessionsPath()}>All Sessions</a>}<a href={pagePath('home')}>{isAccountPage()?'Account home':'Research home'}</a>{!isAccountPage()&&<a href="/?legacy=local">Legacy rollback</a>}</nav></header>}
    {!showWorkspace?<AlphaShell route={route} label={isAccountPage()?'Verified workspace':'Private local workspace'}>
      {!catalog?(connecting?<StatePanel level={1} kind="loading" title="Connecting to your workspace…"/>:<StatePanel level={1} kind={isAccountPage()?'unavailable':'offline'} title={isAccountPage()?'Workspace service unavailable':'Local service unavailable'} action={<button className="rk-btn rk-btn-primary" disabled={busy||connecting} onClick={()=>run(async()=>{
        setConnecting(true);try{const result=await loadResearchContext(route.screen==='replay'?route.session:null,{timeframe});setCatalog(result.catalog);setView(result.view);}finally{setConnecting(false);}
      })}>Retry connection</button>}><p>{isAccountPage()?'Retry, or sign out and sign in again. Nothing was changed.':'Start the local alpha service and database, then retry. Saved Sessions are kept.'}</p></StatePanel>)
      :route.screen==='methods'?<MyMethods catalog={catalog} onOpen={sessionId=>run(()=>reopen(sessionId))}/>
      :route.screen==='method-new'?<MethodNew key={route.family||'new'} catalog={catalog} route={route} onSaved={async methodId=>{setCatalog(await loadProductCatalog());setSelectedMethod(methodId);navigate({screen:'method',method:methodId},{replace:true});setNotice(route.family?'New immutable Method version saved.':'Method saved. Create a Session to start replay.');}}/>
      :route.screen==='method'?<MethodOverview catalog={catalog} route={route} onLifecycle={async()=>setCatalog(await loadProductCatalog())} onOpen={sessionId=>run(()=>reopen(sessionId))} onNewSession={methodId=>{setSelectedMethod(methodId);setNotice(null);creationId.current=id('session');navigate({screen:'session-new',method:methodId});}}/>
      :route.screen==='sessions'?<SessionsPage catalog={catalog} onOpen={sessionId=>run(()=>reopen(sessionId))}/>
      :route.screen==='session'?<SessionOverview catalog={catalog} route={route} onOpen={sessionId=>run(()=>reopen(sessionId))}/>
      :route.screen==='session-new'?<AlphaSessionWizard key={route.method||'any'} catalog={catalog} route={route} busy={busy} error={createError} onCreate={createSession}/>
      :route.screen==='catalog'?<CatalogPage catalog={catalog} onSource={openSource}/>
      :route.screen==='journal'?<AlphaJournalPage catalog={catalog} route={route} onOpen={sessionId=>run(()=>reopen(sessionId))}/>
      :route.screen==='analytics'?<Analytics catalog={catalog} route={route}/>
      :route.screen==='replay'&&route.session?(busy||!notice?<StatePanel level={1} kind="loading" title="Opening Session…"/>:<StatePanel level={1} kind="unavailable" title="This Session could not be opened" action={<a className="rk-btn" {...linkTo({screen:'methods'})}>Back to My Methods</a>}><p>{noticeText(notice)} Nothing was changed.</p></StatePanel>)
      :route.screen==='help'?<HelpPage catalog={catalog} onSource={openSource} onFeedback={event=>{returnFocus.current=event?.currentTarget??null;setDialog('feedback');}}/>
      :route.screen==='account'?<LocalAccountPage catalog={catalog}/>
      :<Placeholder catalog={catalog} onOpen={sessionId=>run(()=>reopen(sessionId))}/>}
      {isAccountPage()&&catalog?.productPagination&&
        (!catalog.productPagination.methods.complete||!catalog.productPagination.sessions.complete)&&
        <nav className="alpha-catalog-more" aria-label="Load more workspace records">
          {!catalog.productPagination.methods.complete&&<button type="button" disabled={busy} onClick={()=>loadMoreCatalog('methods')}>Load more Methods</button>}
          {!catalog.productPagination.sessions.complete&&<button type="button" disabled={busy} onClick={()=>loadMoreCatalog('sessions')}>Load more Sessions</button>}
        </nav>}
    </AlphaShell>:<>
      <section className="alpha-session"><h1>{view.metadata.name}</h1><p><strong>{symbolText}</strong> · <button onClick={openSource} aria-label="Data source">{sourceContext()==='historical'?'Exness':'Synthetic fixture'}</button> · {view.metadata.startPeriod} · {view.method.name}</p><p>Saved balance <strong>${view.state.balance}</strong> · {view.state.unresolved?'Unresolved evidence':'Ready'}</p></section>
      <div className="alpha-workspace"><AlphaWorkspace lead={<><a className="alpha-ws-back" {...linkTo({screen:'method',method:view.method.id})} aria-label={`Back to ${view.method.name}`}><span aria-hidden="true">‹</span><RiksoraMark size={26}/></a><button className="alpha-symbol-chip" onClick={openSource} aria-label={`${symbolText} data source`} title={sourceContext()==='historical'?'Exness source':'Synthetic fixture'}><span aria-hidden="true">{symbolGlyph}</span>{symbolText}</button><span className="alpha-ws-phone-title"><strong>{symbolText} · {timeframe}</strong><small>{new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString().slice(0,16).replace("T"," ")} UTC</small></span></>}
        trail={<><span className="alpha-ws-title"><strong>{view.metadata.name}</strong> <span>· {view.method.name} · {view.method.kind==='PROTOCOL'?'Protocol':'Free Style'}{view.state.unresolved?' · evidence unresolved':''}</span></span>{sessionMenu}</>} objectsOpen={objectsOpen} onToggleObjects={()=>setObjectsOpen(value=>!value)} key={view.metadata.id} view={view} timeframe={timeframe} busy={busy} pauseToken={pauseToken} onNotice={setNotice}
        onTimeframe={tf=>run(async()=>{const saved=await loadWorkspace(view.metadata.id,tf);setView(saved);setTimeframe(tf);})}
        onReplay={(kind,targetNs)=>run(async()=>{
          await api(sessionPath(view.metadata.id)+'/commands',command(view,kind,{targetNs}));
          const saved=await loadWorkspace(view.metadata.id);setView(saved);
          if(saved.state.nextGroupIndex!==view.state.nextGroupIndex)emitLocal(kind==='ADVANCE'?'replay_advanced':'replay_seeked');
          if(saved.state.unresolved)emitLocal('order_outcome_unresolved');
          if(saved.analysis.metrics.tradeCount>view.analysis.metrics.tradeCount)emitLocal('order_outcome_committed');
          if(kind==='ADVANCE'&&saved.state.nextGroupIndex===view.state.nextGroupIndex){setNotice('No additional quote was revealed at this requested boundary. Replay paused.');return false;}
          return true;
        })} onPriceSelect={price=>{setPauseToken(n=>n+1);setPicked({price,at:Date.now()});}} onPlanDrawing={drawing=>{
          setPauseToken(n=>n+1);returnFocus.current=document.activeElement;setDialog('ticket');
          try{edit(planningIntent(drawing,{protocol,tickSize:view.state.profile.tickSize}));setNotice('Planning levels rounded to the Session price grid and copied to the draft. Review these proposed values before confirming; quantity and risk use Session rules.');}
          catch(error){setNotice(error.message);}
        }}/><aside className="alpha-action-rail" aria-label="Workspace tools"><button aria-label="Drawing objects" aria-expanded={objectsOpen} title="Drawing objects" onClick={()=>setObjectsOpen(value=>!value)}><Icon name="layers"/><span>Objects</span></button><button disabled={orderLocked} aria-label="Open order panel" title="Order" onClick={event=>{returnFocus.current=event.currentTarget;setNotice('');setPauseToken(n=>n+1);setDialog('ticket');}}><Icon name="order"/><span>Order</span></button><button aria-label="Open news panel" title="News" onClick={event=>{returnFocus.current=event.currentTarget;setPauseToken(n=>n+1);setDialog('news');}}><Icon name="news"/><span>News</span></button><button aria-label="Open journal panel" title="Journal" onClick={event=>{returnFocus.current=event.currentTarget;setPauseToken(n=>n+1);setDialog("journal");}}><Icon name="journal"/><span>Journal</span></button><button onClick={openSource} aria-label="Open source details" title="Source details"><Icon name="layers"/><span>Source</span></button></aside>
      </div>
      {unverified&&unverified.sessionId===view.metadata.id&&dialog!=='review'&&<div className="alpha-unverified" role="status"><p><strong>Order status not verified.</strong> {UNKNOWN_TEXT} New orders stay locked until the saved Session shows the result.</p><button type="button" disabled={busy} onClick={()=>checkUnverified()}>Check again</button></div>}
      <div className="alpha-order-bar"><button type="button" className="alpha-quick-side alpha-quick-sell" aria-label={`Sell at Bid ${view.quote?.bid??'unavailable'}`} disabled={orderLocked||!view.quote} onClick={event=>openTicket(event,'SHORT')}><span>Sell</span><strong>{view.quote?.bid??'—'}</strong></button><button type="button" className="alpha-quick-side alpha-quick-buy" aria-label={`Buy at Ask ${view.quote?.ask??'unavailable'}`} disabled={orderLocked||!view.quote} onClick={event=>openTicket(event,'LONG')}><span>Buy</span><strong>{view.quote?.ask??'—'}</strong></button><label className="alpha-bar-lots" title={planned?'Planned orders size from risk in the ticket':'Draft quantity; the ticket still reviews it'}><span>Lots</span><input aria-label="Draft lots" inputMode="decimal" value={planned?'':plan.quantity??''} placeholder={planned?'risk':''} disabled={busy||planned||protocol} onChange={e=>edit({quantity:e.target.value})}/></label><button className="alpha-new-order" disabled={orderLocked} onClick={event=>openTicket(event)}>New order</button><span className="alpha-order-hint">{view.state.unresolved?'Evidence unresolved · no invented fill':'Review before confirmation'}</span><span className="alpha-balance-pill" aria-label={`Saved balance ${view.state.balance} USD`}>${view.state.balance}</span></div>
      <AlphaTerminal key={view.metadata.id} request={terminalRequest} view={view} busy={busy} onAction={requestAction} onFeedback={event=>{returnFocus.current=event.currentTarget;setPauseToken(n=>n+1);setDialog('feedback');}}/>
    </>}
    {showWorkspace&&<nav className="alpha-bottom-nav" aria-label="App sections">
      <a {...linkTo({screen:'methods'})}><Icon name="layers"/><span>Methods</span></a>
      <a {...linkTo({screen:'sessions'})}><Icon name="calendar"/><span>Sessions</span></a>
      <button disabled={!view} aria-current={view?'page':undefined} onClick={()=>{globalThis.scrollTo?.({top:0,behavior:'smooth'});mainRef.current?.scrollTo?.({top:0,behavior:'smooth'});}}><Icon name="candles"/><span>Replay</span></button>
      <button disabled={!view} onClick={()=>setTerminalRequest({tab:'Analysis',id:Date.now()})}><Icon name="analytics"/><span>Analysis</span></button>
      <a {...accountLink()}><Icon name="smile"/><span>Account</span></a>
    </nav>}
    <footer><p className="alpha-status-line" role="status" aria-live="polite">{noticeText(notice)||(busy?'Processing your request… Replay and order controls will unlock when it finishes.':catalog?`${isAccountPage()?'Verified workspace research':'Private local research'} · source limitations available in Data source`:'Service required. No fallback market feed.')}</p></footer>
    {dialog==='feedback'&&<WorkspaceModal returnFocusRef={returnFocus} label="Optional research feedback" onClose={()=>setDialog(null)}><AlphaFeedback onClose={()=>setDialog(null)}/></WorkspaceModal>}
    {dialog==='source'&&<WorkspaceModal returnFocusRef={returnFocus} label="Data source" onClose={()=>setDialog(null)}><AlphaSourceDetails historical={sourceContext()==='historical'} account={isAccountPage()} catalog={catalog} view={view} onClose={()=>setDialog(null)}/></WorkspaceModal>}
    {dialog==='journal'&&view&&<WorkspaceModal returnFocusRef={returnFocus} movable label="Research journal" onClose={()=>setDialog(null)}><section className="alpha-dialog alpha-journal-popup"><button className="alpha-popup-close" aria-label="Close journal panel" onClick={()=>setDialog(null)}>Close</button><AlphaJournal view={view}/></section></WorkspaceModal>}
    {dialog==='news'&&<WorkspaceModal returnFocusRef={returnFocus} movable label="News context" onClose={()=>setDialog(null)}><section className="alpha-dialog"><div className="alpha-terminal-heading"><h2>News context</h2><button onClick={()=>setDialog(null)}>Close</button></div><p>No point-in-time news dataset is connected to this Session.</p><p>News is not inferred from prices or fetched from today's calendar. Historical availability and revisions must be verified before events can be shown alongside replay.</p><p>Your trading evidence and saved balance are unchanged.</p></section></WorkspaceModal>}
    {dialog==='ticket'&&view&&<WorkspaceModal returnFocusRef={returnFocus} movable label="Plan an order" onClose={()=>{if(!busy)setDialog(null);}}>      <section className="alpha-ticket alpha-dialog"><div className="alpha-terminal-heading"><h2>Plan an order</h2><button aria-label="Close order panel" disabled={busy} onClick={()=>setDialog(null)}>Close</button></div><p className="alpha-ticket-guide">1. Set the intent · 2. Review exact values · 3. Confirm · 4. Reveal the next tick</p>
        <Segmented className="alpha-ticket-tabs" label="Workflow" value={planned?'PLANNED':'QUICK'} disabled={busy||protocol} options={[['QUICK','Quick'],['PLANNED','Plan · R:R']]} onChange={value=>edit({workflow:value,orderType:value==='QUICK'?'MARKET':'LIMIT'})}/>
        <DirectionQuotes side={plan.side} quote={view.quote} disabled={busy} onChange={side=>edit({side,...(planned&&plan.orderType==='MARKET'?{entry:quoteFor(side)}:{})})}/>
        <Segmented className="alpha-ticket-types" label="Order type" value={protocol&&plan.orderType==='MARKET'?'LIMIT':plan.orderType} disabled={busy||!planned} options={[...(protocol?[]:[['MARKET','Market']]),['LIMIT','Limit'],['STOP','Stop']]} onChange={value=>edit({orderType:value})}/>
        {planned?<><label>Entry<input aria-label="Entry" inputMode="decimal" value={plan.entry} disabled={busy} onChange={e=>edit({entry:e.target.value})}/></label><label>Stop Loss<input aria-label="Stop Loss" inputMode="decimal" value={plan.sl} disabled={busy} onChange={e=>edit({sl:e.target.value})}/></label>{protocol?<p>Target and quantity derive from locked RR {view.method.rr} and risk {view.method.riskPercent}%.</p>:<><label>Take Profit<input aria-label="Take Profit" inputMode="decimal" value={plan.tp} disabled={busy} onChange={e=>edit({tp:e.target.value})}/></label><div className="alpha-ticket-chips" role="group" aria-label="Set take profit by reward to risk">{['1','1.5','2','3'].map(rr=><button type="button" key={rr} disabled={busy} onClick={()=>{const tp=targetForRR({side:plan.side,entry:plan.entry,sl:plan.sl,rr,tickSize:view.state.profile.tickSize});if(tp)edit({tp});else setNotice('Enter a valid entry and stop first; the stop must be on the losing side.');}}>TP {rr}R</button>)}</div><fieldset className="alpha-ticket-risk"><legend>Risk per trade</legend><div className="alpha-ticket-chips" role="group" aria-label="Risk presets">{['0.5','1','2','3'].map(r=><button type="button" key={r} aria-pressed={plan.riskPercent===r} disabled={busy} onClick={()=>edit({riskPercent:r})}>{r}%</button>)}</div><label>Risk %<input aria-label="Risk %" inputMode="decimal" value={plan.riskPercent} disabled={busy} onChange={e=>edit({riskPercent:e.target.value})}/></label></fieldset><AlphaTicketEstimate plan={plan} view={view}/></>}</>:<><label>Quantity (lots)<input aria-label="Quantity (lots)" inputMode="decimal" value={plan.quantity} disabled={busy} onChange={e=>edit({quantity:e.target.value})}/></label>{!protocol&&<p className="alpha-ticket-hint">Quick sends a market order without a stop or target.<button type="button" disabled={busy} onClick={()=>edit({workflow:'PLANNED',orderType:'MARKET',entry:quoteFor(plan.side)})}>Add stop &amp; target</button></p>}</>}
        {protocol&&<fieldset><legend>Checklist · enforcement {view.method.checklistOn?'ON':'OFF'}</legend>{view.method.conditions.map(c=><label key={c.id}>{c.label}<select aria-label={c.label} disabled={busy} value={plan.observations.find(o=>o.conditionId===c.id)?.outcome||'NOT_ASSESSED'} onChange={e=>edit({observations:[...plan.observations.filter(o=>o.conditionId!==c.id),{conditionId:c.id,outcome:e.target.value}]})}><option value="NOT_ASSESSED">Not assessed</option><option value="PASS">Pass</option><option value="FAIL">Fail</option></select></label>)}</fieldset>}
        {notice&&<p className="alpha-ticket-notice" role="alert">{notice==="INVALID_INPUT"?"Check the order values: quantity must be positive and match the Session lot step. For Planned orders, check the entry, stop and target values. (INVALID_INPUT)":noticeText(notice)}</p>}
        <button disabled={orderLocked} onClick={openReview}>Review order</button><p>Quote-based simulation; no broker fill, margin, liquidity or slippage claim. The explicit QUOTE_BASELINE model uses zero commission; broker terms are not certified.</p>
      </section></WorkspaceModal>}
    {dialog==='action'&&orderAction&&<WorkspaceModal returnFocusRef={returnFocus} label="Confirm position action" onClose={()=>{if(!busy){setDialog(null);setOrderAction(null);}}}><section className="alpha-dialog"><h2>{orderAction.kind==='CANCEL'?'Cancel pending order':orderAction.quantity===null?'Request full close':'Request partial close'}</h2><p>{orderAction.order.side} · {orderAction.order.id}</p><p>{orderAction.kind==='CLOSE'?`Quantity: ${orderAction.quantity??orderAction.order.remaining} lots. A request does not settle the trade; the next eligible observed Bid/Ask determines its exit.`:'This cancels an unfilled intent; it does not close a position.'}</p>{notice&&<p role="alert">{noticeText(notice)}</p>}<button disabled={busy} onClick={()=>{setDialog(null);setOrderAction(null);}}>Keep current order</button><button disabled={busy} onClick={confirmAction}>Confirm action</button></section></WorkspaceModal>}
    {picked&&view&&!dialog&&<AlphaPickTicket key={picked.at} price={picked.price} tickSize={view.state.profile?.tickSize} plan={plan} protocol={protocol}
      onCancel={()=>{setPicked(null);[...document.querySelectorAll('button')].find(button=>button.textContent==='Pick order price')?.focus();}} onApply={(field,patch)=>{const value=patch[field];edit(patch);setPicked(null);returnFocus.current=document.querySelector('.alpha-order-bar button')||null;setDialog('ticket');
        setNotice(`${({entry:'Entry',sl:'Stop loss',tp:'Take profit'})[field]} set to ${value} from the chart. Review before confirming.`);}}/>}
    {dialog==='review'&&review&&<WorkspaceModal returnFocusRef={returnFocus} label="Confirm reviewed order" onClose={()=>{if(!busy){setDialog(null);setReview(null);}}}><AlphaReviewSheet key={review.reviewHash} review={review} view={view} busy={busy}
      onConfirm={confirm} onCheck={checkUnverified} onReload={()=>run(()=>reopen(view.metadata.id,{push:false}))} onCancel={()=>{setReview(null);setDialog(null);setOrderAction(null);}} onReviewAgain={()=>{setReview(null);openReview();}}/></WorkspaceModal>}
  </main>;
}
