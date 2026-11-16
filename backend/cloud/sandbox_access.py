"""Opt-in sandbox capacity. No real merchant or payment-provider authority."""
from datetime import timezone, timedelta
from zoneinfo import ZoneInfo
import hashlib, hmac, uuid
from psycopg import sql
from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require, identifier, revision
from ticks.contracts import tag
from infrastructure.database import connect
from execution.postgres import pack, unpack

TIMEZONES=('UTC','Asia/Jakarta')

class SandboxAccess:
    def __init__(self,dsn,reset_timezone,*,event_secret=None,billing=False):
        require(reset_timezone in TIMEZONES,'resetTimezone','ACCESS_UNCONFIGURED')
        require(event_secret is None or type(event_secret) is str and len(event_secret)>=64,'eventSecret')
        require(type(billing) is bool,'billing')
        self.billing=billing
        self.dsn,self.timezone,self.secret=dsn,reset_timezone,event_secret
    def lock(self,db,actor):
        db.execute('INSERT INTO btl.v2_access_accounts VALUES (%s,%s) ON CONFLICT DO NOTHING',(actor,self.timezone))
        row=db.execute('SELECT reset_timezone FROM btl.v2_access_accounts WHERE actor_id=%s FOR UPDATE',(actor,)).fetchone()
        require(row[0]==self.timezone,'resetTimezone','ACCESS_POLICY_DRIFT')
    def now(self,db):return db.execute('SELECT clock_timestamp()').fetchone()[0]
    def status(self,db,actor):
        now=self.now(db);day=now.astimezone(ZoneInfo(self.timezone)).date()
        row=db.execute('SELECT payload,content_hash,event_id,sequence FROM btl.sandbox_access_events WHERE actor_id=%s ORDER BY sequence DESC LIMIT 1',(actor,)).fetchone()
        tier='FREE'
        if row:
            event=checked_event(unpack(*row[:2]))
            require(event['accountId']==str(actor) and event['id']==row[2] and event['sequence']==row[3],'event','CORRUPT_RECORD')
            if event['tier']=='PRO' and int(event['expiresAt'])>int(now.timestamp()):tier='PRO'
        if self.billing:
            paid=db.execute("SELECT 1 FROM btl.sandbox_billing_orders WHERE actor_id=%s AND phase='PAID' AND paid_at<=%s AND expires_at>%s LIMIT 1",(actor,int(now.timestamp()),int(now.timestamp()))).fetchone()
            if paid:tier='PRO'
        saved=db.execute('SELECT count(*) FROM btl.v2_access_sessions WHERE actor_id=%s AND trashed_at IS NULL',(actor,)).fetchone()[0]
        used=db.execute('SELECT 1 FROM btl.v2_access_windows WHERE actor_id=%s AND free_day=%s',(actor,day)).fetchone() is not None
        return dict(schemaVersion=1,artifact='BTL-SANDBOX-ACCESS-1',mode='SANDBOX',fundsCollected=False,tier=tier,resetTimezone=self.timezone,
                    observedAt=now.astimezone(timezone.utc).isoformat(),entitlementDay=day.isoformat(),savedScope='V2_SANDBOX_ONLY',freeActivationAvailable=not used,savedSessions=saved,savedLimit=5 if tier=='FREE' else 128)
    def owner(self,db,actor,workspace,sid,*,active=True):
        identifier(sid,'sessionId')
        row=db.execute('SELECT actor_id,trashed_at FROM btl.v2_access_sessions WHERE workspace_id=%s AND session_id=%s',(str(workspace),sid)).fetchone()
        require(row is not None and str(row[0])==str(actor),'session','RESOURCE_UNAVAILABLE')
        require(not active or row[1] is None,'session','SESSION_TRASHED')
        return row
    def admit_session(self,db,actor,workspace,meta):
        status=self.status(db,actor)
        require(status['savedSessions']<status['savedLimit'],'sessions','SAVED_SESSION_LIMIT')
        db.execute('INSERT INTO btl.v2_access_sessions(workspace_id,session_id,actor_id) VALUES (%s,%s,%s)',(str(workspace),meta['id'],actor))
    def saved_state(self,db,actor,workspace,sid,trash):
        require(type(trash) is bool,'trash');row=self.owner(db,actor,workspace,sid,active=False)
        now=self.now(db)
        if trash:
            if row[1] is None:db.execute('UPDATE btl.v2_access_sessions SET trashed_at=%s WHERE workspace_id=%s AND session_id=%s',(now,str(workspace),sid))
        elif row[1] is not None:
            require(now<row[1]+timedelta(days=30),'restore','TRASH_EXPIRED')
            status=self.status(db,actor);require(status['savedSessions']<status['savedLimit'],'sessions','SAVED_SESSION_LIMIT')
            db.execute('UPDATE btl.v2_access_sessions SET trashed_at=NULL WHERE workspace_id=%s AND session_id=%s',(str(workspace),sid))
        return dict(schemaVersion=1,artifact='BTL-SANDBOX-SAVED-1',sessionId=sid,trashed=trash)
    def activate(self,db,actor,workspace,meta):
        sid=meta['id'];self.owner(db,actor,workspace,sid)
        # Only the server-pinned currently supported short demo calendar segment.
        require(meta['startPeriod']=='2020-01','period','WINDOW_SOURCE_UNAVAILABLE')
        prior=db.execute('SELECT payload,content_hash FROM btl.v2_access_windows WHERE actor_id=%s AND workspace_id=%s AND session_id=%s AND period=%s',(actor,str(workspace),sid,meta['startPeriod'])).fetchone()
        if prior:return self.window(db,actor,workspace,sid,meta)
        status=self.status(db,actor)
        require(status['tier']=='PRO' or status['freeActivationAvailable'],'window','DAILY_WINDOW_LIMIT')
        value=dict(schemaVersion=1,artifact='BTL-SANDBOX-WINDOW-1',sessionId=sid,workspaceId=str(workspace),period=meta['startPeriod'],
                   datasetId=meta['datasetId'],datasetVersion=meta['datasetVersion'],profileHash=meta['profileHash'],
                   startNs='1577836800000000000',endNs='1580515200000000000',activatedAt=status['observedAt'],entitlementDay=status['entitlementDay'],resetTimezone=self.timezone,model='SHORT_SYNTHETIC_ONLY')
        blob,sha=pack(value)
        db.execute('INSERT INTO btl.v2_access_windows VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',(actor,status['entitlementDay'],status['entitlementDay'] if status['tier']=='FREE' else None,str(workspace),sid,value['period'],blob,sha))
        return value
    def window(self,db,actor,workspace,sid,state):
        self.owner(db,actor,workspace,sid)
        row=db.execute('SELECT payload,content_hash FROM btl.v2_access_windows WHERE actor_id=%s AND workspace_id=%s AND session_id=%s',(actor,str(workspace),sid)).fetchone()
        require(row is not None,'window','WINDOW_ACTIVATION_REQUIRED')
        value=unpack(*row);tag(value,'BTL-SANDBOX-WINDOW-1','sessionId workspaceId period datasetId datasetVersion profileHash startNs endNs activatedAt entitlementDay resetTimezone model')
        require(value['sessionId']==sid and value['workspaceId']==str(workspace) and value['resetTimezone']==self.timezone
                and value['period']=='2020-01' and value['startNs']=='1577836800000000000' and value['endNs']=='1580515200000000000'
                and value['model']=='SHORT_SYNTHETIC_ONLY' and all(value[k]==state[k] for k in ('datasetId','datasetVersion','profileHash')),'window','CORRUPT_RECORD')
        return value
    def event(self,raw,signature):
        require(self.secret is not None,'event','SANDBOX_EVENTS_DISABLED')
        checked_event(raw)
        require(type(signature) is str and len(signature)==64 and hmac.compare_digest(signature,hmac.new(self.secret.encode(),canonical_bytes(raw),hashlib.sha256).hexdigest()),'signature','INVALID_SANDBOX_SIGNATURE')
        with connect(self.dsn) as db:
            self.lock(db,raw['accountId'])
            prior=db.execute('SELECT payload,content_hash FROM btl.sandbox_access_events WHERE event_id=%s',(raw['id'],)).fetchone()
            if prior:
                require(prior[1]==content_hash(raw),'event','REFUSED_IDEMPOTENCY_CONFLICT');return unpack(*prior)
            last=db.execute('SELECT max(sequence) FROM btl.sandbox_access_events WHERE actor_id=%s',(raw['accountId'],)).fetchone()[0]
            require(raw['sequence']>(last or 0),'sequence','STALE_BILLING_EVENT')
            now=int(self.now(db).timestamp())
            require(now<int(raw['expiresAt'])<=now+31*86400,'expiry','INVALID_SANDBOX_EXPIRY')
            blob,sha=pack(raw);db.execute('INSERT INTO btl.sandbox_access_events VALUES (%s,%s,%s,%s,%s)',(raw['id'],raw['accountId'],raw['sequence'],blob,sha))
        return raw

def checked_event(raw):
    tag(raw,'BTL-SANDBOX-ACCESS-EVENT-1','id accountId sequence tier expiresAt mode')
    identifier(raw['id'],'eventId');revision(raw['sequence']);require(raw['sequence']>0,'sequence')
    require(type(raw['accountId']) is str,'account')
    try:account=uuid.UUID(raw['accountId'])
    except ValueError:require(False,'account')
    require(str(account)==raw['accountId'],'account')
    require(raw['mode']=='SANDBOX' and raw['tier'] in ('FREE','PRO'),'event')
    require(type(raw['expiresAt']) is str and raw['expiresAt'].isascii() and raw['expiresAt'].isdigit() and len(raw['expiresAt'])<=12,'expiry')
    require(len(canonical_bytes(raw))<=4096,'event');return raw

def grant_sandbox_access_runtime(dsn,role):
    from execution.research_v2 import grant_research_v2_runtime
    grant_research_v2_runtime(dsn,role)
    with connect(dsn) as db:
        db.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON btl.v2_access_accounts,btl.v2_access_sessions TO {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('GRANT SELECT,INSERT ON btl.v2_access_windows TO {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('GRANT SELECT ON btl.sandbox_access_events TO {}').format(sql.Identifier(role)))


def grant_sandbox_event_runtime(dsn,role):
    """Separate operator test-event role; financial API never needs event INSERT."""
    with connect(dsn) as db:
        db.execute(sql.SQL('GRANT USAGE ON SCHEMA btl TO {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON btl.v2_access_accounts TO {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('GRANT SELECT,INSERT ON btl.sandbox_access_events TO {}').format(sql.Identifier(role)))
