#!/bin/bash
# W6: backup/restore drill on the VPS PostgreSQL 17 (QA cluster, port 54329). Physical base backup + WAL archive + point-in-time restore, and pg_dump/pg_restore for comparison.
PGB=$HOME/tools/pg17/bin; PGDATA=$HOME/tools/pgdata; P="-h 127.0.0.1 -p 54329 -U postgres"; BK=$HOME/data/backup; RS=$HOME/data/restore_pitr
t() { date +%s.%N; }
el() { python3 -c "print(round($2-$1,1))"; }
rm -rf $BK/base/* $BK/wal/* $RS; mkdir -p $BK/wal $BK/base
echo "== enable WAL archiving (archive_mode needs a restart)"
$PGB/psql $P -qc "ALTER SYSTEM SET archive_mode=on" -c "ALTER SYSTEM SET archive_command='test ! -f $BK/wal/%f && cp %p $BK/wal/%f'" -c "ALTER SYSTEM SET archive_timeout='60s'"
$PGB/pg_ctl -D $PGDATA restart -w -t 60 -l /tmp/pg54329.log >/dev/null 2>&1; $PGB/psql $P -Atc "select 'archive_mode='||current_setting('archive_mode')"
echo "== create drill database with about 1 GB of data"
$PGB/psql $P -qc "DROP DATABASE IF EXISTS drill" -c "CREATE DATABASE drill"
a=$(t); $PGB/psql $P -d drill -q -c "CREATE TABLE t(id int primary key, tag text, payload text)" -c "INSERT INTO t SELECT g,'BASE',repeat(md5(random()::text),30) FROM generate_series(1,700000) g"; b=$(t)
echo "load seconds: $(el $a $b); drill db size: $($PGB/psql $P -Atc "select pg_size_pretty(pg_database_size('drill'))")"
echo "== physical base backup (tar+gzip, WAL streamed)"
a=$(t); $PGB/pg_basebackup $P -D $BK/base/b1 -Ft -z -X stream -c fast; b=$(t)
echo "base backup seconds: $(el $a $b); size: $(du -sh $BK/base/b1 | cut -f1)"
echo "== writes after the backup: batch A (kept by PITR), then target time T1, then batch B (must be gone)"
$PGB/psql $P -d drill -qc "INSERT INTO t SELECT 1000000+g,'A','x' FROM generate_series(1,1000) g"
sleep 2; T1=$($PGB/psql $P -d drill -Atc "select to_char(clock_timestamp(),'YYYY-MM-DD HH24:MI:SS.US')"); sleep 2
$PGB/psql $P -d drill -qc "INSERT INTO t SELECT 2000000+g,'B','x' FROM generate_series(1,1000) g"
$PGB/psql $P -Atc "select pg_switch_wal()" >/dev/null; sleep 4
echo "T1=$T1 ; archived WAL files: $(ls $BK/wal | wc -l)"
echo "== logical backup (pg_dump custom) for comparison"
a=$(t); $PGB/pg_dump $P -Fc -d drill -f $BK/base/drill.dump; b=$(t); echo "pg_dump seconds: $(el $a $b); size: $(du -sh $BK/base/drill.dump | cut -f1)"
echo "== PITR restore from base backup + archived WAL to T1"
a=$(t); mkdir -p $RS && chmod 700 $RS && tar -xzf $BK/base/b1/base.tar.gz -C $RS && mkdir -p $RS/pg_wal && tar -xzf $BK/base/b1/pg_wal.tar.gz -C $RS/pg_wal
cat >> $RS/postgresql.auto.conf <<CONF
restore_command='cp $BK/wal/%f %p'
recovery_target_time='$T1'
recovery_target_action='promote'
archive_mode=off
port=54330
CONF
touch $RS/recovery.signal
$PGB/pg_ctl -D $RS -o "-k /tmp -c listen_addresses=127.0.0.1" -l /tmp/pg54330.log start -w -t 300 >/dev/null 2>&1
for i in $(seq 1 120); do r=$($PGB/psql -h 127.0.0.1 -p 54330 -U postgres -d drill -Atc "select pg_is_in_recovery()" 2>/dev/null); [ "$r" = "f" ] && break; sleep 1; done; b=$(t)
echo "restore+recovery seconds (RTO for this size): $(el $a $b)"
$PGB/psql -h 127.0.0.1 -p 54330 -U postgres -d drill -Atc "select tag||'='||count(*) from t group by tag order by tag" | tr '\n' ' '; echo "<- expected BASE=700000 A=1000, no B"
$PGB/pg_ctl -D $RS stop -m fast >/dev/null 2>&1
echo "== logical restore (pg_restore -j 4) into a new database"
$PGB/psql $P -qc "DROP DATABASE IF EXISTS drill_restored" -c "CREATE DATABASE drill_restored"
a=$(t); $PGB/pg_restore $P -j 4 -d drill_restored $BK/base/drill.dump; b=$(t); echo "pg_restore seconds: $(el $a $b); rows: $($PGB/psql $P -d drill_restored -Atc 'select count(*) from t')"
echo "== verify backup manifest"
$PGB/pg_verifybackup -n $BK/base/b1 2>&1 | tail -1 || true
echo "DRILL_DONE"
