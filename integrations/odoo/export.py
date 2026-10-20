"""Explicit offline business export. No app imports or Odoo network writes."""
import argparse,importlib.util,json,os
from datetime import timezone
from pathlib import Path
from psycopg import sql
from infrastructure.database import connect
PATH=Path(__file__).with_name('addons')/'btl_business'/'contract.py'
spec=importlib.util.spec_from_file_location('btl_business_contract',PATH);contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)

def snapshot(dsn,source):
    contract.uid(source)
    with connect(dsn) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        return _snapshot(db,source)

def _snapshot(db,source):
    users=db.execute('SELECT id,email FROM btl.users ORDER BY id LIMIT 1001').fetchall()
    orders=db.execute('SELECT order_id,actor_id,plan_version,amount_idr,phase,revision,expires_at FROM btl.sandbox_billing_orders ORDER BY order_id LIMIT 1001').fetchall()
    if len(users)>1000 or len(orders)>1000:raise ValueError('BUSINESS_EXPORT_LIMIT')
    value=dict(schemaVersion=1,artifact='BTL-BUSINESS-EXPORT-1',source=source,mode='SANDBOX',
               customers=[dict(id=str(uid),email=email) for uid,email in users],
               orders=[dict(id=row[0],account=str(row[1]),plan=row[2],amountIdr=str(row[3]),phase=row[4],revision=row[5],expiresAt=None if row[6] is None else str(row[6])) for row in orders])
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
    contract.decode(raw);return raw


def grant_export_reader(dsn,role):
    with connect(dsn) as db:
        db.execute(sql.SQL('GRANT SELECT(id,actor_id,title,message,created_at) ON btl.support_requests TO {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('GRANT USAGE ON SCHEMA btl TO {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('GRANT SELECT(id,email) ON btl.users TO {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('GRANT SELECT(order_id,actor_id,plan_version,amount_idr,phase,revision,expires_at) ON btl.sandbox_billing_orders TO {}').format(sql.Identifier(role)))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    raw=snapshot(os.environ['BTL_BUSINESS_EXPORT_DSN'],args.source)
    with Path(args.output).open('xb') as stream:stream.write(raw)
    print('SANDBOX_BUSINESS_EXPORT_WRITTEN_NO_REAL_REVENUE')
if __name__=='__main__':main()


def bundle(dsn,source):
    contract.uid(source)
    with connect(dsn) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        observed=str(db.execute('SELECT floor(extract(epoch FROM transaction_timestamp())*1000000)::bigint').fetchone()[0])
        value=json.loads(_snapshot(db,source))
        rows=db.execute('SELECT id,actor_id,title,message,created_at FROM btl.support_requests ORDER BY id LIMIT 1001').fetchall()
        if len(rows)>1000:raise ValueError('BUSINESS_EXPORT_LIMIT')
        value=dict(schemaVersion=1,artifact='BTL-BUSINESS-SYNC-1',source=source,observedAtUs=observed,snapshot=value,
                   tickets=[dict(id=str(r[0]),account=str(r[1]),title=r[2],message=r[3],createdAt=r[4].astimezone(timezone.utc).isoformat()) for r in rows])
        raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
        if len(raw)>8388608:raise ValueError('BUSINESS_EXPORT_LIMIT')
        return raw
