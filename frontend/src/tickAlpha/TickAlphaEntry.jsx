import {lazy,Suspense} from 'react';
const Alpha=lazy(()=>import('./TickAlpha.jsx'));
export default function TickAlphaEntry(){return <Suspense fallback={<p>Loading local tick alpha…</p>}><Alpha/></Suspense>;}
