"""Actual QA PostgreSQL relation/TOAST/index/fork allocation accounting."""
import re


def measure(db,data):
    tables=db.execute("SELECT c.oid,n.nspname,c.relname,c.reltoastrelid,pg_table_size(c.oid),pg_indexes_size(c.oid),pg_total_relation_size(c.oid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE (n.nspname='btl' AND c.relname IN ('tick_sessions','tick_checkpoints','tick_commands','tick_events')) OR (n.nspname='public' AND c.relname IN ('qa6_objects','qa6_format')) ORDER BY c.relname").fetchall()
    result=[]
    for oid,schema,name,toast,heap,index,total in tables:
        parents=[oid]+([toast] if toast else [])
        indexes=[r[0] for r in db.execute('SELECT indexrelid FROM pg_index WHERE indrelid=ANY(%s)',(parents,))]
        paths=[r[0] for r in db.execute('SELECT pg_relation_filepath(x) FROM unnest(%s::oid[]) x',(parents+indexes,))]
        files=[]
        for relative in paths:
            path=data/relative;pattern=re.compile(re.escape(path.name)+r'(?:_(?:fsm|vm|init))?(?:\.\d+)?$')
            for p in path.parent.iterdir():
                if pattern.fullmatch(p.name):files.append(dict(path=str(p.relative_to(data)),size=p.stat().st_size,allocated=p.stat().st_blocks*512))
        if sum(f['size'] for f in files)!=total:raise ValueError('PHYSICAL_ACCOUNTING')
        column='body' if name=='qa6_objects' else 'version' if name=='qa6_format' else 'payload'
        stats=db.execute(f'SELECT count(*),coalesce(sum(octet_length({column})),0),coalesce(sum(pg_column_size({column})),0),coalesce(sum(pg_column_size(t)),0) FROM {schema}.{name} t').fetchone()
        mvcc=db.execute('SELECT n_tup_upd,n_dead_tup,last_autovacuum::text FROM pg_stat_all_tables WHERE relid=%s',(oid,)).fetchone()
        result.append(dict(table=name,rows=stats[0],payloadLengthBytes=stats[1],storedColumnBytes=stats[2],currentTupleBytes=stats[3],heapToastFileBytes=heap,indexFileBytes=index,
                           filesystemAllocatedBytes=sum(f['allocated'] for f in files),postgresReportedBytes=total,files=files,mvccStatsEstimate=list(mvcc) if mvcc else None))
    return dict(tables=result,filesystemAllocatedBytes=sum(r['filesystemAllocatedBytes'] for r in result),databaseBytes=db.execute('SELECT pg_database_size(current_database())').fetchone()[0])
