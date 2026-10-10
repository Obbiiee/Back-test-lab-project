import {lazy,Suspense} from 'react';
const Alpha=lazy(()=>import('./TickAlpha.jsx'));
const Home=lazy(()=>import('./AlphaHome.jsx'));
export default function TickAlphaEntry(){const home=new URLSearchParams(window.location.search).get('page')==='home';return <Suspense fallback={<p>Loading local tick alpha…</p>}>{home?<Home/>:<Alpha/>}</Suspense>;}
