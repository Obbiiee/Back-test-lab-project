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
let visit=function(file){if(reachable.has(file))return;reachable.add(file);
  for(const match of read(file).matchAll(/(?:from\s*|import\s*\(?\s*)["'](\.[^"']+)["']/g)){
    const base=path.posix.normalize(path.posix.join(path.posix.dirname(file),match[1]));
    assert.ok(base.startsWith('frontend/src/'),'Production must not import archives/fixtures: '+base);
    const target=[base,base+'.js',base+'.jsx',base+'.css',base+'/index.js'].find(p=>existsSync(path.join(root,p))&&statSync(path.join(root,p)).isFile());
    assert.ok(target,'Missing local module: '+base);visit(target);
  }
}
// Brand fonts are reachable only through stylesheet url() references; verify each exists.
const visitModules=visit;visit=file=>{const known=reachable.has(file);visitModules(file);if(known||!file.endsWith('.css'))return;
  for(const match of read(file).matchAll(/url\(\s*["']?(\.[^"')]+)["']?\s*\)/g)){
    const asset=path.posix.normalize(path.posix.join(path.posix.dirname(file),match[1]));
    assert.ok(asset.startsWith('frontend/src/')&&existsSync(path.join(root,asset)),'Missing stylesheet asset: '+asset);reachable.add(asset);
  }};
visit('frontend/src/main.jsx');
const compatibility=['frontend/src/components/TradingLevels.jsx','frontend/src/drawings/position.js'];
assert.deepEqual(source.filter(p=>!reachable.has(p)).sort(),compatibility.sort(),'Unreachable source must have reviewed architectural purpose');
assert.ok(read('frontend/tests/drawings.test.mjs').includes('../legacy/phase3/src/drawings/tools.js'));
assert.ok(read('frontend/tests/phase5.test.mjs').includes('PHASE4_STORAGE_BEFORE.json'));
assert.ok(read('frontend/tests/phase6.test.mjs').includes('PHASE5_STORAGE_BEFORE.json'));
const config=JSON.parse(read('frontend/scripts/ai-bundle.config.json'));
for(const file of reachable)if(file.startsWith('frontend/src/tickAlpha/'))
  assert.ok(config.implementation.includes(file),'Reachable Alpha module missing from AI bundle: '+file);
// V21-1 deliberately admits only this reviewed execution seam, never all backend/data.
const executionReferences=new Set([
  'backend/tests/test_odoo_recovery.py','backend/tests/test_local_reliability.py',
  'backend/cloud/support.py','backend/infrastructure/migrations/014_support_intake.sql','backend/tests/test_support.py','backend/tests/test_odoo_sync.py',
  'backend/tests/test_odoo_projection.py',
  'backend/cloud/billing.py','backend/infrastructure/migrations/013_sandbox_billing.sql','backend/tests/test_billing.py',
  'backend/cloud/midtrans.py','backend/tests/test_midtrans.py',
  'backend/ticks/dukascopy_batch.py','backend/tests/test_dukascopy_batch.py',
  'backend/identity/google.py','backend/identity/google_store.py','backend/infrastructure/migrations/012_google_identity.sql','backend/tests/test_google_identity.py',
  'backend/cloud/sandbox_access.py','backend/cloud/research_v2.py','backend/infrastructure/migrations/011_v2_sandbox_access.sql','backend/tests/test_sandbox_v2.py',
  'backend/execution/analysis_v2.py','backend/tests/test_analysis_v2.py',
    'backend/execution/research_v2.py','backend/execution/research_fixture_v2.py','backend/infrastructure/migrations/010_v2_research.sql','backend/tests/test_research_v2.py',
  'backend/execution/kernel_v2.py','backend/execution/controller_v2.py','backend/execution/postgres_v2.py','backend/tests/test_kernel_v2.py','backend/tests/test_execution_v2_postgres.py','backend/tests/fixtures/execution_v2.json',
  'backend/execution/sources_v2.py','backend/tests/test_sources_v2.py',
  'backend/execution/finance_v2.py','backend/tests/test_finance_v2.py',
  'backend/execution/profile_v2.py','backend/tests/test_profile_v2.py','backend/tests/fixtures/execution_profiles_v2.json','backend/tests/verify_profile_v2_vectors.mjs',
  'backend/execution/conversion.py','backend/tests/test_conversion.py',
  // Reviewed private tick-context seam and its intake/warmup dependencies only.
  'backend/market_data/context_warmup.py','backend/market_data/tick_context.py',
  'backend/tests/test_context_warmup.py','backend/tests/test_tick_context.py',
  'backend/ticks/histdata_v2.py','backend/tests/test_histdata_v2.py',
  // Offline CSV foundation: exact files only; no data/downloader admission.
  'backend/market_data/instruments.py','backend/ticks/dukascopy_csv.py','backend/tests/test_dukascopy_csv.py',
  'backend/cloud/worker.py','backend/tests/test_worker_deadline.py','backend/tests/alpha_capacity_probe.py','backend/cloud/queue.py','backend/infrastructure/migrations/009_replay_queue.sql','backend/infrastructure/migrations/008_research_queue.sql','backend/tests/test_research_queue.py',
  'backend/infrastructure/resources.py','backend/tests/test_resource_bounds.py',
  'backend/cloud/app.py','backend/cloud/research.py','backend/cloud/workspaces.py','backend/tests/test_cloud_research.py',
  'backend/identity/store.py','backend/identity/manager.py','backend/identity/boundary.py','backend/identity/delivery.py',
  'backend/workspace/store.py','backend/workspace/policy.py','backend/workspace/intake.py',
  'backend/execution/journal.py','backend/tests/test_tick_journal.py','backend/infrastructure/migrations/007_tick_journal.sql',
  'backend/execution/analysis.py','backend/execution/bootstrap.py','backend/execution/observability.py','backend/tests/test_tick_analysis.py','backend/tests/stitch_analytics.py',
  'backend/execution/workspace.py','backend/tests/test_tick_workspace.py',
  'backend/execution/research.py','backend/execution/research_fixture.py','backend/execution/local_api.py',
  'backend/execution/historical.py','backend/ticks/contracts_v2.py','backend/ticks/storage_v2.py','backend/ticks/exness_v2.py','backend/ticks/timeline_v2.py','backend/ticks/evidence_v2.py','backend/ticks/benchmark_v2.py',
  'backend/tests/test_historical_workspace.py','backend/tests/test_tick_storage_v2.py','backend/tests/test_tick_evidence_v2.py','backend/tests/test_identity.py',
  'backend/infrastructure/migrations/006_research_sessions.sql','backend/tests/test_research_sessions.py',
  'backend/execution/__init__.py','backend/execution/contracts.py','backend/execution/engine.py',
  'backend/execution/controller.py','backend/execution/postgres.py','backend/execution/fixture_demo.py',
  'backend/ticks/contracts.py','backend/ticks/provider.py','backend/ticks/timeline.py',
  'backend/contracts/primitives.py','backend/contracts/canonical.py','backend/contracts/models.py',
  'backend/application/models.py','backend/infrastructure/database.py','backend/infrastructure/codec.py',
  'backend/infrastructure/migrations/005_tick_execution.sql','backend/tests/test_execution_goldens.py',
  'backend/tests/test_tick_execution.py','backend/tests/test_tick_timeline.py','backend/tests/test_tick_execution_postgres.py',
  'backend/tests/fixtures/tick_execution_v1.json',
]);
function allowedBundleSource(file){
  // Required attribution for the reviewed presentation and Ray adaptations;
  // no general public/ asset or dataset admission.
  if(['frontend/public/licenses/opencharts-LICENSE.txt','frontend/public/licenses/lightweight-charts-drawing-ray-LICENSE.txt','frontend/public/licenses/NOTICE.txt'].includes(file))return true;
  return file.startsWith('backend/')?executionReferences.has(file):! /^(legacy\/|data\/|frontend\/(legacy|public|node_modules|dist)\/)/.test(file);
}
for(const category of ['context','implementation','tests','supporting'])for(const file of config[category]){
  assert.ok(existsSync(path.join(root,file)),'Missing bundle source: '+file);
  assert.ok(allowedBundleSource(file),'Bundle must remain task-specific: '+file);
}
for(const file of executionReferences)assert.ok([...config.implementation,...config.tests].includes(file),'Execution seam missing from reviewed bundle: '+file);
for(const file of ['backend/market_data/unreviewed.py','backend/cloud/unreviewed.py','backend/ticks/unreviewed.py','backend/.env','data/raw.csv','frontend/public/market/data.json','frontend/public/licenses/unreviewed.js','legacy/src/main.jsx'])assert.equal(allowedBundleSource(file),false,'Unreviewed source admitted: '+file);
for(const file of ['frontend/public/licenses/opencharts-LICENSE.txt','frontend/public/licenses/NOTICE.txt'])assert.ok(config.supporting.includes(file),'Adapted presentation must retain attribution in its bundle');
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

// S-7: every planned catalog entry is classified by one existing ledger owner.
// Derive names from authoritative specs instead of duplicating those catalogs.
const acceptanceBlocks=[...read('docs/V2_ALPHA_FROZEN_EXECUTION_LEDGER.md').matchAll(/```json\s*([\s\S]*?)```/g)].map(m=>JSON.parse(m[1]));
const stitchAcceptance=acceptanceBlocks.filter(b=>b.CLASSIFICATION==='STITCH_S7_BOUNDED_ACCEPTANCE');assert.equal(stitchAcceptance.length,1);
const acceptance=stitchAcceptance[0];
const drawingCatalog=read('docs/DRAWING_ENGINE_SPEC.md').split('## Planned professional tool set')[1].split('The exact implementation order')[0].trim().split(/\r?\n/).filter(line=>line.includes(': ')).flatMap(line=>line.split(': ')[1].replace(/\.$/,'').split(', '));
const indicatorCatalog=read('docs/INDICATOR_ENGINE_SPEC.md').split('Add: ')[1].split(', subject to')[0].replace(/ and /g,', ').split(', ');
assert.equal(drawingCatalog.length,25);assert.equal(indicatorCatalog.length,17);
assert.deepEqual([...acceptance.drawing.implemented,...acceptance.drawing.deferred].sort(),drawingCatalog.sort());
assert.deepEqual([...acceptance.indicators.deferred].sort(),indicatorCatalog.sort());
for(const owner of Object.values(acceptance.deferred_owners))assert.ok(existsSync(path.join(root,owner.split('#')[0])),'Deferred capability has no existing owner');
assert.equal(acceptance.professional_catalog_complete,false);assert.equal(acceptance.historical_precision_accepted,false);
console.log('PASS S-7 single ledger classifies all 25 professional drawing tools and 17 expanded indicators with existing owners; no professional/precision completion claim.');

// Alpha closure: protect scope/owner/screen coherence without copying runtime status.
function validateAlphaClosure(docs,bundleConfig){
  const spec='docs/V2_ALPHA_FROZEN_SPEC.md';
  const contracts=Object.entries(docs).flatMap(([file,doc])=>[...doc.matchAll(/```json\s*([\s\S]*?)```/g)].map(m=>({file,value:JSON.parse(m[1])})))
    .filter(block=>block.value.CONTRACT==='ALPHA_PRODUCT_CLOSURE_20261010');
  assert.equal(contracts.length,1,'One Alpha closure scope owner');
  assert.equal(contracts[0].file,spec);
  const closure=contracts[0].value;
  assert.equal(closure.financial_contract_unchanged,true);
  assert.equal(closure.historical_uncertainty_preserved,true);
  assert.equal(closure.external_rollout_requires_separate_gate,true);
  assert.equal(closure.additional_drawing,'Ray');
  assert.equal(new Set(closure.screen_ids).size,closure.screen_ids.length,'Screen identities must be unique');
  assert.ok(closure.screen_ids.length>0);
  for(const key of ['measurement_owner','design_owner','oss_owner','decision_owner','sequence_owner']){
    const owner=closure[key];assert.ok(docs[owner],'Missing Alpha owner '+key);
    assert.ok(bundleConfig.context.includes(owner),'Alpha owner excluded from handoff bundle: '+owner);
    assert.ok(docs[owner].includes('V2_ALPHA_FROZEN_SPEC.md'),'Owner must link to Alpha scope: '+owner);
  }
  assert.ok(bundleConfig.context.includes(spec),'Scope excluded from bundle');
  for(const screen of closure.screen_ids)assert.ok(docs[closure.design_owner].includes('| '+screen+' |'),'Missing screen acceptance: '+screen);
  const changes=Object.entries(docs).filter(([,doc])=>/^### CR-ALPHA-20261010 —/m.test(doc));
  assert.deepEqual(changes.map(([file])=>file),[closure.decision_owner],'One supplemental drawing/measurement decision');
}
validateAlphaClosure(documents,config);
assert.throws(()=>validateAlphaClosure({...documents,'docs/duplicate-alpha.md':documents['docs/V2_ALPHA_FROZEN_SPEC.md']},config));
assert.throws(()=>validateAlphaClosure({...documents,'docs/PRODUCT_DESIGN_BLUEPRINT.md':documents['docs/PRODUCT_DESIGN_BLUEPRINT.md'].replace('| order_review |','| removed_screen |')},config));
assert.throws(()=>validateAlphaClosure({...documents,'docs/V2_ALPHA_FROZEN_SPEC.md':documents['docs/V2_ALPHA_FROZEN_SPEC.md'].replace('"financial_contract_unchanged": true','"financial_contract_unchanged": false')},config));
assert.throws(()=>validateAlphaClosure(documents,{...config,context:config.context.filter(p=>p!=='docs/V2_1_PRODUCT_MEASUREMENT_CONTRACT.md')}));
console.log('PASS Alpha closure single scope/decision, screen acceptance, existing owners/bundle, separate external gate and preserved financial/uncertainty contracts; negative drift rejected.');
