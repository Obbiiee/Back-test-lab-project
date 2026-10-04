// Deterministic treap: timestamp + opaque ID keys, stable hashed priorities.
// Only eligible projections enter these trees; no future fact values.
const compare = (a, b) => a.time - b.time || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
function priority(id) { let hash = 2166136261; for (const character of id) hash = Math.imul(hash ^ character.charCodeAt(0), 16777619); return hash >>> 0; }
function merge(a, b) {
  if (!a || !b) return a ?? b;
  if (a.priority < b.priority) { a.right = merge(a.right, b); return a; }
  b.left = merge(a, b.left); return b;
}
function remove(root, key) {
  if (!root) return null;
  const order = compare(key, root);
  if (!order) return merge(root.left, root.right);
  if (order < 0) root.left = remove(root.left, key); else root.right = remove(root.right, key);
  return root;
}
function split(root, key) {
  if (!root) return [null, null];
  if (compare(root, key) < 0) { const [a, b] = split(root.right, key); root.right = a; return [root, b]; }
  const [a, b] = split(root.left, key); root.left = b; return [a, root];
}
function insert(root, item) {
  if (!root) return item;
  if (item.priority < root.priority) { [item.left, item.right] = split(root, item); return item; }
  if (compare(item, root) < 0) root.left = insert(root.left, item); else root.right = insert(root.right, item);
  return root;
}
export class TimeIndex {
  root = null;
  keys = new Map();
  dateOnly = new Map();
  operations = 0;
  put(event) {
    this.delete(event.occurrenceId);
    const item = { time: event.fields.schedule.value, id: event.occurrenceId, event, priority: priority(event.occurrenceId), left: null, right: null };
    this.keys.set(item.id, { time: item.time, id: item.id }); this.root = insert(this.root, item);
  }
  delete(id) { const key = this.keys.get(id); if (key) { this.root = remove(this.root, key); this.keys.delete(id); } }
  range(from, to, limit = Infinity) {
    const output = []; this.operations = 0;
    const walk = root => {
      if (!root || output.length >= limit) return;
      this.operations++;
      if (root.time >= from) walk(root.left);
      if (root.time >= from && root.time < to && output.length < limit) output.push(root.event);
      if (root.time < to) walk(root.right);
    };
    walk(this.root); return output;
  }
  neighbor(time, direction) {
    let root = this.root, found = null; this.operations = 0;
    while (root) {
      this.operations++;
      if (direction > 0 ? root.time > time : root.time < time) { found = root; root = direction > 0 ? root.left : root.right; }
      else root = direction > 0 ? root.right : root.left;
    }
    return found?.time ?? null;
  }
}
