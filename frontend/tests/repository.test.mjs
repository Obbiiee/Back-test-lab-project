import assert from 'node:assert/strict';
import {readFileSync, readdirSync, existsSync, statSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const read=p=>readFileSync(path.join(root,p),'utf8');
const source=[];
function inventory(dir){for(const entry of readdirSync(path.join(root,dir),{withFileTypes:true})){const file=dir+'/'+entry.name;if(entry.isDirectory())inventory(file);else source.push(file);}}
inventory('frontend/src');
const reachable=new Set();
function visit(file){if(reachable.has(file))return;reachable.add(file);
  for(const match of read(file).matchAll(/(?:from\s*|import\s*\(?\s*)["'](\.[^"']+)["']/g)){
    const base=path.posix.normalize(path.posix.join(path.posix.dirname(file),match[1]));
    assert.ok(base.startsWith('frontend/src/'),'Production must not import archives/fixtures: '+base);
    const target=[base,base+'.js',base+'.jsx',base+'.css',base+'/index.js'].find(p=>existsSync(path.join(root,p))&&statSync(path.join(root,p)).isFile());
    assert.ok(target,'Missing local module: '+base);visit(target);
  }
}
visit('frontend/src/main.jsx');
const compatibility=['frontend/src/components/TradingLevels.jsx','frontend/src/drawings/position.js'];
assert.deepEqual(source.filter(p=>!reachable.has(p)).sort(),compatibility.sort(),'Unreachable source must have reviewed architectural purpose');
assert.ok(read('frontend/tests/drawings.test.mjs').includes('../legacy/phase3/src/drawings/tools.js'));
assert.ok(read('frontend/tests/phase5.test.mjs').includes('PHASE4_STORAGE_BEFORE.json'));
assert.ok(read('frontend/tests/phase6.test.mjs').includes('PHASE5_STORAGE_BEFORE.json'));
const config=JSON.parse(read('frontend/scripts/ai-bundle.config.json'));
for(const category of ['context','implementation','tests','supporting'])for(const file of config[category]){
  assert.ok(existsSync(path.join(root,file)),'Missing bundle source: '+file);
  assert.ok(!/^(legacy\/|backend\/|data\/|frontend\/(legacy|public|node_modules|dist)\/)/.test(file),'Bundle must remain task-specific');
}
const pkg=JSON.parse(read('frontend/package.json')),lock=JSON.parse(read('frontend/package-lock.json'));
for(const section of ['dependencies','devDependencies'])assert.deepEqual(pkg[section],lock.packages[''][section],'Lock manifest drift');
for(const rule of ['/AI_BUNDLE/','/frontend/tests/artifacts/','/docs/_generated/','node_modules/','dist/','.env'])assert.ok(read('.gitignore').split(/\r?\n/).includes(rule),'Missing ignore boundary: '+rule);
console.log(`PASS repository boundaries: ${reachable.size} reachable production files, two retained compatibility exports, preserved fixtures, small bundle allowlist and synchronized lock manifest.`);
