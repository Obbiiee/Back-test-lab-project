// Bounded canonical snapshots only: no chart, primitive, selection or trading state.
export class DrawingHistory {
  undoStack = [];
  redoStack = [];
  applying = false;
  constructor(manager, limit = 100) {
    if (!Number.isInteger(limit) || limit < 1) throw new Error('Invalid history limit');
    this.manager = manager; this.limit = limit;
    this.unsubscribe = manager.subscribeCommitted((before, after) => {
      if (this.applying) return;
      this.undoStack.push({ before, after });
      if (this.undoStack.length > this.limit) this.undoStack.shift();
      this.redoStack = [];
    });
  }
  get canUndo() { return this.undoStack.length > 0; }
  get canRedo() { return this.redoStack.length > 0; }
  reset(models) {
    this.applying = true;
    try { this.undoStack = []; this.redoStack = []; this.manager.replaceAll(models); }
    finally { this.applying = false; }
    this.manager.notify();
  }
  undo() {
    const action = this.undoStack.pop(); if (!action) return false;
    this.redoStack.push(action); this.apply(action.before); return true;
  }
  redo() {
    const action = this.redoStack.pop(); if (!action) return false;
    this.undoStack.push(action); this.apply(action.after); return true;
  }
  apply(models) {
    this.applying = true;
    try { this.manager.replaceAll(models); } finally { this.applying = false; }
  }
}
