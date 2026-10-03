// Specs are trusted pure functions; the production registry starts empty.
export class IndicatorRegistry {
  #specs = new Map();
  register(spec) {
    if (!spec || typeof spec.type !== 'string' || !/^[A-Z][A-Z0-9_]*$/.test(spec.type)
      || !['line', 'histogram'].includes(spec.output) || typeof spec.calculate !== 'function'
      || !Number.isInteger(spec.warmup) || spec.warmup < 0 || !spec.parameters
      || Object.getPrototypeOf(spec.parameters) !== Object.prototype) throw Error('Invalid indicator spec');
    if (this.#specs.has(spec.type)) throw Error('Duplicate indicator type');
    const parameters = {};
    for (const [key, rule] of Object.entries(spec.parameters)) {
      if (!/^[a-z][a-zA-Z0-9_]*$/.test(key) || !rule || typeof rule.validate !== 'function' || !rule.validate(rule.default)
        || !['number', 'string', 'boolean'].includes(typeof rule.default)
        || (typeof rule.default === 'number' && !Number.isFinite(rule.default))) throw Error('Invalid parameter rule');
      parameters[key] = Object.freeze({ ...rule });
    }
    this.#specs.set(spec.type, Object.freeze({ ...spec, parameters: Object.freeze(parameters) }));
    return this;
  }
  get(type) { const spec = this.#specs.get(type); if (!spec) throw Error('Unknown indicator type'); return spec; }
}

export const defaultIndicatorRegistry = new IndicatorRegistry();
