// Embedded PostgreSQL SQL checks; no native psycopg acceptance claim.
// No network, persistent database, market data, or application dependency change.
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile, readdir } from 'node:fs/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('../../', import.meta.url))
const dependencies = process.env.BTL_PGLITE_TEST_MODULES || path.join(root, 'frontend/node_modules/.riksora-pg-qa/node_modules')
const { PGlite } = await import(pathToFileURL(path.join(dependencies, '@electric-sql/pglite/dist/index.js')))
const directory = path.join(root, 'backend/infrastructure/migrations')
const heads = JSON.parse(await readFile(path.join(root, 'backend/tests/fixtures/migration_reconciliation_heads.json'), 'utf8'))
const p0 = new Set(Object.keys(heads.pr48.migrations).filter(name => !heads.pr44.migrations[name]))
const names = (await readdir(directory)).filter(name => /^\d{3}_.+\.sql$/.test(name)).sort()
const files = await Promise.all(names.map(async name => {
  const sql = (await readFile(path.join(directory, name), 'utf8')).replaceAll('\r\n', '\n')
  return { name, sql, checksum: createHash('sha256').update(sql).digest('hex') }
}))
for (const head of [heads.pr44, heads.pr48]) {
  for (const [name, expected] of Object.entries(head.migrations)) {
    const file = files.find(item => item.name === name)
    assert(file, `Missing published migration ${name}`)
    const bytes = Buffer.from(file.sql)
    const blob = createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex')
    assert.equal(blob, expected, `Published migration changed: ${name}`)
  }
}

// Mirrors the documented filename/checksum rule. The actual Python runner has
// its own opt-in isolated test in test_migration_reconciliation.py.
async function migrate(db, selected) {
  await db.transaction(async tx => {
    await tx.exec('CREATE TABLE IF NOT EXISTS public.btl_migrations (version text PRIMARY KEY,checksum text NOT NULL)')
    const recorded = new Map((await tx.query('SELECT version,checksum FROM public.btl_migrations')).rows.map(row => [row.version, row.checksum]))
    assert([...recorded.keys()].every(name => selected.some(file => file.name === name)), 'MIGRATION_DRIFT version')
    for (const file of selected) {
      if (recorded.has(file.name)) assert.equal(recorded.get(file.name), file.checksum, 'MIGRATION_DRIFT checksum')
      else {
        await tx.exec(file.sql)
        await tx.query('INSERT INTO public.btl_migrations VALUES ($1,$2)', [file.name, file.checksum])
      }
    }
  })
}

for (const history of ['fresh', 'pr44', 'pr48']) {
  const db = await PGlite.create()
  try {
    const old = history === 'fresh' ? [] : files.filter(file => heads[history].migrations[file.name])
    await migrate(db, old)
    const before = (await db.query('SELECT * FROM public.btl_migrations ORDER BY version')).rows
    const seed = "INSERT INTO btl.tick_sessions SELECT 'ws',id,repeat('a',64),repeat('a',64),0,decode('01','hex'),repeat('b',64) FROM unnest(ARRAY['legacy','progress']) id; INSERT INTO btl.tick_checkpoints SELECT workspace_id,session_id,revision,payload,content_hash FROM btl.tick_sessions"
    const progress = "INSERT INTO btl.observed_replay_progress VALUES ('ws','progress',0,repeat('b',64),4,200,2,decode('01','hex'),repeat('b',64))"
    if (old.length) {
      await db.exec(seed)
      if (history === 'pr44') await db.exec("INSERT INTO btl.tick_methods VALUES ('ws','method:existing',decode('01','hex'),repeat('a',64)); INSERT INTO btl.tick_research_sessions VALUES ('ws','legacy','method:existing',decode('02','hex'),repeat('b',64))")
      if (history === 'pr48') await db.exec(progress)
      // Retain nonempty evidence across the upgrade, not merely table names.
      if (history === 'pr44') await db.exec("INSERT INTO btl.tick_terminal_orders VALUES ('ws','legacy',0,'order:old','CANCELLED',1,repeat('a',64),decode('aabb','hex'),repeat('b',64)); INSERT INTO btl.tick_recovery_bases VALUES ('ws','legacy',0,repeat('a',64),repeat('b',64),repeat('c',64),decode('aabb','hex'),repeat('d',64))")
      else await db.exec("INSERT INTO btl.tick_terminal_order_archive_v1 VALUES ('ws','legacy',0,'order:old',1,repeat('a',64),decode('aabb','hex'),repeat('b',64))")
    }
    await migrate(db, files)
    await migrate(db, files)
    const after = (await db.query('SELECT * FROM public.btl_migrations ORDER BY version')).rows
    assert.equal(after.length, files.length)
    assert.deepEqual(after.filter(row => before.some(prior => prior.version === row.version)), before)
    if (!old.length) await db.exec(seed)
    if (history !== 'pr48') await db.exec(progress)
    const scalar = async sql => Object.values((await db.query(sql)).rows[0])[0]
    if (old.length) {
      const table = history === 'pr44' ? 'tick_terminal_orders' : 'tick_terminal_order_archive_v1'
      assert.equal(await scalar(`SELECT encode(payload,'hex') FROM btl.${table}`), 'aabb')
      if (history === 'pr44') assert.equal(await scalar("SELECT encode(payload,'hex') FROM btl.tick_recovery_bases"), 'aabb')
    }
    assert.equal(await scalar('SELECT revision::text FROM btl.observed_replay_progress'), '4')
    assert.equal(await scalar("SELECT to_regclass('btl.tick_method_metric_projections') IS NOT NULL"), true)
    if (history === 'pr44') {
      assert.deepEqual((await db.query("SELECT rollup_state,session_count::text FROM btl.tick_method_metric_projections WHERE method_id='method:existing'")).rows[0],
        { rollup_state: 'REBUILD_REQUIRED', session_count: '1' })
    }
    await db.exec("CREATE ROLE migration_runtime; GRANT USAGE ON SCHEMA btl TO migration_runtime; GRANT SELECT,UPDATE ON btl.tick_sessions TO migration_runtime; SET ROLE migration_runtime; UPDATE btl.tick_sessions SET revision=1 WHERE session_id='legacy'; RESET ROLE")
    await assert.rejects(db.exec("UPDATE btl.tick_sessions SET revision=5 WHERE session_id='progress'"), error => error.code === '23000')
    await assert.rejects(db.exec('DELETE FROM btl.observed_replay_progress'), error => error.code === '23000')
    const commit = "INSERT INTO btl.tick_checkpoints VALUES ('ws','progress',5,decode('02','hex'),repeat('c',64)); INSERT INTO btl.tick_commands VALUES ('ws','progress','financial',5,repeat('c',64),decode('02','hex'),repeat('c',64)); UPDATE btl.tick_sessions SET revision=5 WHERE session_id='progress';"
    await db.exec('BEGIN;'+commit+'ROLLBACK;')
    assert.equal(await scalar('SELECT count(*)::text FROM btl.observed_replay_progress'), '1')
    assert.equal(await scalar('SELECT count(*)::text FROM btl.tick_commands'), '0')
    await db.exec('BEGIN;'+commit+'COMMIT;')
    assert.equal(await scalar('SELECT count(*)::text FROM btl.observed_replay_progress'), '0')
    assert.equal(await scalar("SELECT revision::text FROM btl.tick_sessions WHERE session_id='progress'"), '5')
    for (const table of ['tick_terminal_orders', 'tick_terminal_order_archive_v1', 'tick_recovery_bases']) await assert.rejects(db.exec('TRUNCATE btl.'+table))
    await assert.rejects(migrate(db, files.filter(file => !p0.has(file.name))), /MIGRATION_DRIFT/)
    await assert.rejects(migrate(db, files.map(file => p0.has(file.name) ? { ...file, checksum: 'changed' } : file)), /MIGRATION_DRIFT/)
    assert.deepEqual((await db.query('SELECT * FROM public.btl_migrations ORDER BY version')).rows, after)
    console.log(`PASS embedded SQL: ${history} -> ${files.length} migrations; ledger identity, retry, drift, legacy role, progress commit/rollback, immutable tables`)
  } finally {
    await db.close()
  }
}
