import { readFile, writeFile, mkdir, rm, lstat, realpath } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const marker = 'Backtest Lab disposable AI bundle v1';
export const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
async function safeFile(root, relative) {
  if (typeof relative !== 'string' || !relative || relative.includes('\\') || relative.split('/').some(part => !part || part === '..' || part === '.') || path.isAbsolute(relative)) throw new Error('Unsafe source path: ' + relative);
  const absolute = path.resolve(root, relative);
  if (!absolute.startsWith(root + path.sep) || await realpath(absolute) !== absolute) throw new Error('Symlink or escaped source: ' + relative);
  if (!(await lstat(absolute)).isFile()) throw new Error('Source is not a file: ' + relative);
  return readFile(absolute);
}
async function prepare(root) {
  const configPath = 'frontend/scripts/ai-bundle.config.json';
  const configBytes = await safeFile(root, configPath), config = JSON.parse(configBytes);
  const records = [], content = new Map();
  for (const category of ['context', 'implementation', 'tests', 'supporting']) {
    if (!Array.isArray(config[category])) throw new Error('Missing allowlist: ' + category);
    for (const source of config[category]) {
      if (records.some(record => record.source === source)) throw new Error('Duplicate source: ' + source);
      const bytes = await safeFile(root, source);
      const bundle = 'files/' + source;
      records.push({ source, bundle, category, sha256: sha256(bytes), bytes: bytes.length }); content.set(bundle, bytes);
    }
  }
  records.sort((a,b) => a.source < b.source ? -1 : a.source > b.source ? 1 : 0);
  if (typeof config.currentTask !== 'string') throw new Error('Missing task text');
  content.set('README.md', marker + '\n\nMaster repository is authoritative. Regenerate before each task; verify before review. This may be stale and is not production code, an application or a fork. Edits do not modify master. Return a reviewed patch mapped through FILE_MANIFEST; no automatic apply. Run tests in master: dependencies, data and legacy fixtures are intentionally omitted.\n');
  content.set('CONTEXT.md', config.context.map(source => '# ' + source + '\n\n' + content.get('files/' + source).toString('utf8').trim()).join('\n\n') + '\n');
  content.set('CURRENT_TASK.md', config.currentTask + '\n');
  const manifest = { version: 1, config: configPath, configSha256: sha256(configBytes), files: records };
  content.set('FILE_MANIFEST.json', JSON.stringify(manifest, null, 2) + '\n');
  return { manifest, content };
}
export async function bundle(root, verify = false) {
  root = await realpath(root);
  const target = path.join(root, 'AI_BUNDLE');
  const prepared = await prepare(root); // Validate all inputs before replacing output.
  if (verify) {
    const actual = JSON.parse(await safeFile(root, 'AI_BUNDLE/FILE_MANIFEST.json'));
    if (JSON.stringify(actual) !== JSON.stringify(prepared.manifest)) throw new Error('STALE: master source or bundle configuration changed');
    for (const [name, expected] of prepared.content) {
      if (sha256(await safeFile(root, 'AI_BUNDLE/' + name)) !== sha256(expected)) throw new Error('Bundle changed: ' + name + '; review secondary edits before regenerating');
    }
  } else {
    let existing;
    try { existing = await lstat(target); } catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (existing) {
      if (existing.isSymbolicLink() || !existing.isDirectory() || !((await safeFile(root, 'AI_BUNDLE/README.md')).toString().startsWith(marker + '\n'))) throw new Error('Refusing to replace non-generated AI_BUNDLE');
      // Fixed, verified direct child of root, never an input-controlled deletion path.
      await rm(target, { recursive: true });
    }
    for (const [name, bytes] of prepared.content) {
      const destination = path.join(target, name); await mkdir(path.dirname(destination), {recursive:true}); await writeFile(destination, bytes);
    }
  }
  const stats = { files: prepared.content.size, bytes: [...prepared.content.values()].reduce((sum,value)=>sum + Buffer.byteLength(value),0), implementation: prepared.manifest.files.filter(f=>f.category==='implementation').length, tests: prepared.manifest.files.filter(f=>f.category==='tests').length, context: prepared.manifest.files.filter(f=>f.category==='context').length + 3, supporting: prepared.manifest.files.filter(f=>f.category==='supporting').length };
  return stats;
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
  try { console.log(process.argv.includes('--verify') ? 'PASS bundle verification' : 'Generated disposable bundle', await bundle(root, process.argv.includes('--verify'))); }
  catch(error) { console.error(error.message); process.exitCode = 1; }
}
