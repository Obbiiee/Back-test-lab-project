// Navigation requests existing manual steps; it owns no replay/account state.
export class NewsNavigationController {
  target = null;
  waiting = null;
  begin(target, state) {
    if (!Number.isFinite(target) || target <= state.time) throw new Error('Choose a future eligible event.');
    this.target = target; this.waiting = null;
  }
  cancel() { this.target = null; this.waiting = null; }
  commit({ time, revision, settledTime, active, loading, error, atEnd, step }) {
    if (this.target === null) return 'idle';
    if (!active || error) { this.cancel(); return 'cancelled'; }
    if (loading || settledTime !== time) return 'waiting';
    if (this.waiting === revision) return 'waiting';
    this.waiting = null;
    if (time >= this.target) { this.cancel(); return 'arrived'; }
    if (atEnd) return 'waiting-for-history';
    this.waiting = revision; step(1); return 'stepping';
  }
}
