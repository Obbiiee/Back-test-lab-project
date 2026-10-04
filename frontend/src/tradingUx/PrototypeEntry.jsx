import {lazy,Suspense} from 'react';
const Prototype=lazy(()=>import('./TradingUxPrototype.jsx'));
export default function PrototypeEntry(){return <Suspense fallback={<p>Loading trading UX prototype…</p>}><Prototype/></Suspense>;}
