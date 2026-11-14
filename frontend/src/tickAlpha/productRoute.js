import {useEffect,useState} from 'react';
import {isAccountPage} from './accountClient.js';

// Product routes live in query parameters so the same build serves the local
// workspace (?tick-alpha=local) and the account page (?page=account) without a
// server rewrite. Old links keep working: ?session=<id> still opens replay.
export const SCREENS=['account','methods','method','method-new','sessions','session','session-new','analytics','journal','catalog','help','replay'];
export const METHOD_TABS=['overview','sessions','analytics','rules'];
const EVENT='riksora:route';

export function readRoute(href=typeof window==='undefined'?'http://localhost/':window.location.href){
  const params=new URL(href).searchParams;
  const session=params.get('session');
  const asked=params.get('screen');
  const screen=SCREENS.includes(asked)?asked:session?'replay':'methods';
  const tab=METHOD_TABS.includes(params.get('tab'))?params.get('tab'):'overview';
  return {screen,session,method:params.get('method'),tab,analyticsSession:params.get('of')};
}

// Builds a URL for a product route while keeping the transport selectors
// (tick-alpha, page=account) and dropping route parameters that do not apply.
export function routeHref(next,href=typeof window==='undefined'?'http://localhost/':window.location.href){
  const url=new URL(href);
  for(const key of ['screen','method','tab','of','session'])url.searchParams.delete(key);
  if(next.screen==='replay'&&next.session){url.searchParams.set('session',next.session);return url.pathname+url.search;}
  if(next.screen&&next.screen!=='methods')url.searchParams.set('screen',next.screen);
  if(next.method)url.searchParams.set('method',next.method);
  if(next.screen==='method'&&next.tab&&next.tab!=='overview')url.searchParams.set('tab',next.tab);
  if(next.of)url.searchParams.set('of',next.of);
  return url.pathname+url.search;
}

// One page at a time may hold unsaved work (Journal note drafts). Its guard
// receives `proceed` and returns true to let the route change happen now, or
// false to hold it and call proceed() later (after the person confirms).
let leaveGuard=null;
export function setLeaveGuard(guard){
  leaveGuard=guard;
  return()=>{if(leaveGuard===guard)leaveGuard=null;};
}
const here=()=>typeof window==='undefined'?'':window.location.pathname+window.location.search;
let shown=here();

export function navigate(next,{replace=false,force=false}={}){
  const href=routeHref(next);
  if(!force&&leaveGuard&&href!==here()&&!leaveGuard(()=>navigate(next,{replace,force:true})))return;
  window.history[replace?'replaceState':'pushState'](null,'',href);
  window.dispatchEvent(new Event(EVENT));
}

export function useRoute(){
  const [route,setRoute]=useState(()=>readRoute());
  useEffect(()=>{
    const sync=event=>{
      // Browser Back/Forward cannot be cancelled: put the guarded page back and
      // replay the move once the person confirms.
      if(event?.type==='popstate'&&leaveGuard&&here()!==shown){
        const target=here();
        const proceed=()=>{window.history.pushState(null,'',target);shown=target;setRoute(readRoute());};
        window.history.pushState(null,'',shown);
        if(leaveGuard(proceed))proceed();
        return;
      }
      shown=here();setRoute(readRoute());
    };
    window.addEventListener('popstate',sync);window.addEventListener(EVENT,sync);
    return()=>{window.removeEventListener('popstate',sync);window.removeEventListener(EVENT,sync);};
  },[]);
  return route;
}

// Link click helper: keeps real hrefs (open in new tab works) but routes in-app.
export function linkTo(next){
  return {href:routeHref(next),onClick:event=>{
    if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
    event.preventDefault();navigate(next);
  }};
}

// Inside the account page the token lives in memory, so Account must route in-app
// (a full reload would sign the person out). Locally it opens the separate account page.
// A link that loads another document (the local Account page) still asks the leave
// guard first, so unsaved work gets the same in-app dialog as an in-app link.
export function documentLink(href){
  return {href,onClick:event=>{
    if(!leaveGuard||event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
    event.preventDefault();
    const go=()=>window.location.assign(href);
    if(leaveGuard(go))go();
  }};
}
export function accountLink(){return isAccountPage()?linkTo({screen:'account'}):documentLink('/?page=account');}
