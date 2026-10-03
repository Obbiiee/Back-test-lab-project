// Specs are trusted pure functions. The foundation registry remains catalog-neutral.
export class IndicatorRegistry {
  #specs = new Map();
  register(spec) {
    if (!spec || typeof spec.type !== 'string' || !/^[A-Z][A-Z0-9_]*$/.test(spec.type)
      || typeof spec.calculate !== 'function'
      || !Number.isInteger(spec.warmup) || spec.warmup < 0 || !spec.parameters
      || Object.getPrototypeOf(spec.parameters) !== Object.prototype) throw Error('Invalid indicator spec');
    if (this.#specs.has(spec.type)) throw Error('Duplicate indicator type');
    const placement = spec.placement ?? 'price';
    if (!['price', 'pane'].includes(placement)
      || (spec.validateParameters !== undefined && typeof spec.validateParameters !== 'function')) throw Error('Invalid placement/parameter contract');
    const references = spec.references ?? [];
    if (!Array.isArray(references) || references.some(price => !Number.isFinite(price))
      || new Set(references).size !== references.length || (references.length && placement !== 'pane')) throw Error('Invalid reference lines');
    const range = spec.range;
    if (range !== undefined && (placement !== 'pane' || !Array.isArray(range) || range.length !== 2
      || !range.every(Number.isFinite) || range[0] >= range[1])) throw Error('Invalid pane range');
    if (spec.outputs !== undefined && spec.output !== undefined) throw Error('Ambiguous outputs');
    const outputs = spec.outputs ?? [{ key: 'value', outputType: spec.output, options: spec.options }];
    if (!Array.isArray(outputs) || !outputs.length || new Set(outputs.map(item => item?.key)).size !== outputs.length) throw Error('Invalid outputs');
    const frozenOutputs = outputs.map(item => {
      if (!item || !/^[a-z][a-zA-Z0-9_]*$/.test(item.key) || !['line', 'histogram'].includes(item.outputType)) throw Error('Invalid output spec');
      const options = item.options ?? {};
      if (Object.getPrototypeOf(options) !== Object.prototype || Object.keys(options).some(key => !['color', 'lineWidth'].includes(key))
        || (options.color !== undefined && (typeof options.color !== 'string' || !options.color.trim()))
        || (options.lineWidth !== undefined && (!Number.isInteger(options.lineWidth) || options.lineWidth < 1 || options.lineWidth > 4))) throw Error('Invalid output options');
      return Object.freeze({ key: item.key, outputType: item.outputType, options: Object.freeze({ ...options }) });
    });
    const parameters = {};
    for (const [key, rule] of Object.entries(spec.parameters)) {
      if (!/^[a-z][a-zA-Z0-9_]*$/.test(key) || !rule || typeof rule.validate !== 'function' || !rule.validate(rule.default)
        || !['number', 'string', 'boolean'].includes(typeof rule.default)
        || (typeof rule.default === 'number' && !Number.isFinite(rule.default))) throw Error('Invalid parameter rule');
      parameters[key] = Object.freeze({ ...rule });
    }
    this.#specs.set(spec.type, Object.freeze({ ...spec, placement, references: Object.freeze([...references]),
      ...(range ? { range: Object.freeze([...range]) } : {}), outputs: Object.freeze(frozenOutputs), parameters: Object.freeze(parameters) }));
    return this;
  }
  get(type) { const spec = this.#specs.get(type); if (!spec) throw Error('Unknown indicator type'); return spec; }
  types() { return Object.freeze([...this.#specs.keys()]); }
}

export const defaultIndicatorRegistry = new IndicatorRegistry();
