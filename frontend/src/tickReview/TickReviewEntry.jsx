import {lazy,Suspense} from 'react';
const Review=lazy(()=>import('./LocalTickReview.jsx'));
export default function TickReviewEntry(){
  return <Suspense fallback={<p>Loading Local Tick Review…</p>}><Review/></Suspense>;
}
