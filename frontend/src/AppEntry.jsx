import {lazy, Suspense} from 'react';
import {entryRoute} from './entryRoute.js';

const Account = lazy(() => import('./tickAlpha/AlphaAccount.jsx'));
const Home = lazy(() => import('./tickAlpha/AlphaHome.jsx'));
const Site = lazy(() => import('./site/SiteApp.jsx'));
const Workspace = lazy(() => import('./tickAlpha/TickAlphaEntry.jsx'));
const Review = lazy(() => import('./tickReview/TickReviewEntry.jsx'));
const Prototype = lazy(() => import('./tradingUx/PrototypeEntry.jsx'));
const Legacy = lazy(() => import('./FigmaWorkspace.jsx'));

const entries = {
  account: <Account/>,
  'hosted-home': <Home hosted/>,
  workspace: <Workspace/>,
  review: <Review/>,
  prototype: <Prototype/>,
  legacy: <Legacy/>,
};

export default function AppEntry({location}) {
  const route = entryRoute(location);
  return <Suspense fallback={<main role="status">Loading RIKSORA…</main>}>
    {route === 'site' ? <Site location={location}/> : entries[route]}
  </Suspense>;
}
