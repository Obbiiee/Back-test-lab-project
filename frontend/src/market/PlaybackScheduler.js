export const PLAYBACK_SPEEDS = Object.freeze([1, 2, 5, 10, 20]);

// A timer may request one step. Only acknowledgement of a committed revision
// allows another timer; speed changes cannot queue a second in-flight step.
export class PlaybackScheduler {
  #timer = null;
  #waiting = null;
  #generation = 0;
  constructor(clock = { set: (fn, delay) => setTimeout(fn, delay), clear: id => clearTimeout(id) }) { this.clock = clock; }
  cancel() { this.#generation++; if (this.#timer !== null) this.clock.clear(this.#timer); this.#timer = null; }
  commit({ enabled, speed, revision, step }) {
    this.cancel();
    if (!enabled) { this.#waiting = null; return; }
    if (this.#waiting !== null && this.#waiting === revision) return;
    this.#waiting = null;
    const generation = this.#generation;
    this.#timer = this.clock.set(() => {
      if (generation !== this.#generation) return;
      this.#timer = null;
      this.#waiting = revision;
      step();
    }, 1000 / (PLAYBACK_SPEEDS.includes(speed) ? speed : 1));
  }
  dispose() { this.cancel(); this.#waiting = null; }
}
