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
// V21-1 deliberately admits only this reviewed execution seam, never all backend/data.
const executionReferences=new Set([
  'backend/execution/research.py','backend/execution/research_fixture.py','backend/execution/local_api.py',
  'backend/infrastructure/migrations/006_research_sessions.sql','backend/tests/test_research_sessions.py',
  'backend/execution/__init__.py','backend/execution/contracts.py','backend/execution/engine.py',
  'backend/execution/controller.py','backend/execution/postgres.py','backend/execution/fixture_demo.py',
  'backend/ticks/contracts.py','backend/ticks/provider.py','backend/ticks/timeline.py',
  'backend/contracts/primitives.py','backend/contracts/canonical.py','backend/contracts/models.py',
  'backend/application/models.py','backend/infrastructure/database.py','backend/infrastructure/codec.py',
  'backend/infrastructure/migrations/005_tick_execution.sql','backend/tests/test_execution_goldens.py',
  'backend/tests/test_tick_execution.py','backend/tests/test_tick_execution_postgres.py',
  'backend/tests/fixtures/tick_execution_v1.json',
]);
function allowedBundleSource(file){
  return file.startsWith('backend/')?executionReferences.has(file):! /^(legacy\/|data\/|frontend\/(legacy|public|node_modules|dist)\/)/.test(file);
}
for(const category of ['context','implementation','tests','supporting'])for(const file of config[category]){
  assert.ok(existsSync(path.join(root,file)),'Missing bundle source: '+file);
  assert.ok(allowedBundleSource(file),'Bundle must remain task-specific: '+file);
}
for(const file of executionReferences)assert.ok([...config.implementation,...config.tests].includes(file),'Execution seam missing from reviewed bundle: '+file);
for(const file of ['backend/cloud/app.py','backend/ticks/exness_v2.py','backend/.env','data/raw.csv','frontend/public/market/data.json','legacy/src/main.jsx'])assert.equal(allowedBundleSource(file),false,'Unreviewed source admitted: '+file);
assert.ok(config.context.includes('docs/V2_ALPHA_EXECUTION_FINANCIAL_CONTRACT.md'));
const pkg=JSON.parse(read('frontend/package.json')),lock=JSON.parse(read('frontend/package-lock.json'));
for(const section of ['dependencies','devDependencies'])assert.deepEqual(pkg[section],lock.packages[''][section],'Lock manifest drift');
for(const rule of ['/AI_BUNDLE/','/frontend/tests/artifacts/','/docs/_generated/','node_modules/','dist/','.env'])assert.ok(read('.gitignore').split(/\r?\n/).includes(rule),'Missing ignore boundary: '+rule);
console.log(`PASS repository boundaries: ${reachable.size} reachable production files, two retained compatibility exports, preserved fixtures, small bundle allowlist and synchronized lock manifest.`);

// Phase 7.6: authority ownership and drift checks. Existing test owner extended.
const contextFiles=readdirSync(path.join(root,'AI_CONTEXT')).filter(p=>p.endsWith('.md')).sort();
const owners={
  onboarding:'AI_CONTEXT/00_START_HERE.md',state:'AI_CONTEXT/01_PROJECT_STATE.md',architecture:'AI_CONTEXT/02_ARCHITECTURE.md',history:'AI_CONTEXT/03_PHASE_HISTORY.md',
  'current-phase':'AI_CONTEXT/04_CURRENT_PHASE.md',protected:'AI_CONTEXT/05_PROTECTED_SYSTEMS.md',workflow:'AI_CONTEXT/06_WORKFLOW_RULES.md',tests:'AI_CONTEXT/07_TEST_COMMANDS.md',roadmap:'docs/ROADMAP.md',
};
assert.deepEqual(contextFiles,Object.values(owners).filter(p=>p.startsWith('AI_CONTEXT/')).map(p=>path.posix.basename(p)).sort(),'No competing context entrypoints/trackers/workflows');
function authority(document){const blocks=[...document.matchAll(/```json\s*([\s\S]*?)```/g)].map(match=>JSON.parse(match[1]));return blocks.find(block=>block.AUTHORITY);}
function documentationFiles(directory){return readdirSync(path.join(root,directory),{withFileTypes:true}).flatMap(entry=>{const file=directory+'/'+entry.name;if(entry.name==='_generated')return [];return entry.isDirectory()?documentationFiles(file):entry.name.endsWith('.md')?[file]:[];});}
const documents=Object.fromEntries([...contextFiles.map(p=>'AI_CONTEXT/'+p),...documentationFiles('docs')].map(p=>[p,read(p)]));
function validateControl(docs,bundleConfig){
  for(const kind of ['current-phase','workflow','roadmap']){
    const found=Object.keys(docs).filter(p=>authority(docs[p])?.AUTHORITY===kind);
    assert.deepEqual(found,[owners[kind]],'Exactly one '+kind+' authority');
    assert.ok(bundleConfig.context.includes(owners[kind]),'Authority missing from AI bundle: '+kind);
  }
  const start=docs[owners.onboarding],workflow=docs[owners.workflow],pointer=authority(docs[owners['current-phase']]);
  for(const [kind,file] of Object.entries(owners)){assert.ok(bundleConfig.context.includes(file),'Bundle missing '+kind);if(kind!=='onboarding')assert.ok(start.includes(path.posix.basename(file)),'Onboarding missing '+kind);}
  assert.ok(workflow.includes('04_CURRENT_PHASE.md'),'Workflow must link to status authority');
  for(const key of ['LAST_COMPLETED_PHASE','CURRENT_IMPLEMENTATION_PHASE','NEXT_PHASE','NEXT_PHASE_STATUS','AUTHORIZED_IMPLEMENTATION_PHASE','TARGET_CHECKPOINT','FINAL_ROADMAP_PHASE']){
    assert.ok(Object.hasOwn(pointer,key),'Missing operational field '+key);
    for(const [file,doc] of Object.entries(docs))if(file!==owners['current-phase'])assert.ok(!doc.includes('"'+key+'"'),'Operational field duplicated: '+key);
  }
  assert.equal(pointer.FINAL_ROADMAP_PHASE,'75');
  assert.ok(pointer.CURRENT_IMPLEMENTATION_PHASE===null||pointer.CURRENT_IMPLEMENTATION_PHASE===pointer.AUTHORIZED_IMPLEMENTATION_PHASE,'Active phase must be authorized');
  if(pointer.CURRENT_IMPLEMENTATION_PHASE===null)assert.equal(pointer.AUTHORIZED_IMPLEMENTATION_PHASE,null,'Idle state cannot pre-authorize a next phase');
  const policy=authority(workflow);
  for(const gate of ['REQUIRE_HUMAN_AUTHORIZATION','ONE_PHASE_ONLY','REQUIRE_TESTS','REQUIRE_DIFF_REVIEW','REQUIRE_CONTEXT_STATUS_UPDATE','REQUIRE_GITHUB_COMMIT','REQUIRE_GITHUB_PUSH','REQUIRE_REMOTE_HEAD_VERIFICATION','REQUIRE_CLEAN_WORKING_TREE','REQUIRE_STOP','REQUIRE_NEXT_PROMPT'])assert.equal(policy[gate],true,'Mandatory gate '+gate);
  assert.equal(policy.BROWSER_POLICY,'PRODUCT_CHANGES_REQUIRED_DOCS_ONLY_EXEMPT_WITH_REASON');
  assert.ok(workflow.includes('NEXT-PROMPT REQUIREMENT'),'Final-report next-prompt policy missing');
  const phases=[...docs[owners.roadmap].matchAll(/^\| (\d+(?:\.\d+)?) \|/gm)].map(m=>m[1]);
  assert.equal(new Set(phases).size,phases.length,'Duplicate roadmap phase');
  for(let phase=1;phase<=75;phase++)assert.ok(phases.includes(String(phase)),'Missing roadmap phase '+phase);
  assert.ok(phases.includes('14.5'),'Missing fractional checkpoint 14.5');
  assert.equal(authority(docs[owners.roadmap]).FINAL_PHASE,'75');
}
validateControl(documents,config);
// Negative cases demonstrate the checks reject drift rather than just matching today.
assert.throws(()=>validateControl({...documents,'AI_CONTEXT/duplicate.md':documents[owners['current-phase']]},config));
assert.throws(()=>validateControl({...documents,[owners.workflow]:documents[owners.workflow].replace('"REQUIRE_GITHUB_PUSH": true','"REQUIRE_GITHUB_PUSH": false')},config));
assert.throws(()=>validateControl({...documents,[owners.roadmap]:documents[owners.roadmap].replace(/^\| 14\.5 \|.*\r?\n/m,'')},config));
assert.throws(()=>validateControl(documents,{...config,context:config.context.filter(p=>p!==owners.roadmap)}));
console.log('PASS Phase 7.6 single authorities, operational fields, authorization/checkpoint/STOP/next-prompt gates, roadmap 1–75/14.5 and authoritative bundle inclusion; negative drift cases rejected.');
