// One runner discovers existing test owners from package.json. It deliberately
// exits on the first failure instead of hiding failures behind later commands.
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
const { scripts } = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
for (const [name, command] of Object.entries(scripts)) {
  if (!name.startsWith('test:') || name === 'test:regression') continue;
  const match = /^node ([a-zA-Z0-9./_-]+)$/.exec(command);
  if (!match) throw Error(`Review regression runner support for ${name}; unsupported command must not be silently skipped.`);
  console.log(`\n${name}`);
  const result = spawnSync(process.execPath, [match[1]], { stdio: 'inherit', cwd: new URL('..', import.meta.url) });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
console.log('\nPASS all registered regression tests. Lint/build/browser/Git gates remain separately required.');
