"""Private expiring Google state and immutable subject ownership; no token crypto."""
from hashlib import sha256
import secrets,uuid
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from fastapi_users.password import PasswordHelper
from contracts.primitives import require,ContractError
from infrastructure.database import connect


def key(value):return sha256(value.encode('ascii')).hexdigest()

class GoogleStateStore:
    def __init__(self,dsn,config_hash):self.dsn,self.config_hash=dsn,config_hash
    def begin(self,state,browser,nonce,verifier,*,purpose='LOGIN',target_user_id=None):
        require(purpose in ('LOGIN','LINK') and ((purpose=='LOGIN' and target_user_id is None) or
                (purpose=='LINK' and target_user_id is not None)),'googlePurpose')
        with connect(self.dsn) as db:
            db.execute('SELECT pg_advisory_xact_lock(2020,12)')
            db.execute('DELETE FROM btl.google_login_states WHERE state_hash IN (SELECT state_hash FROM btl.google_login_states WHERE expires_at<=clock_timestamp() ORDER BY expires_at LIMIT 1000)')
            require(db.execute('SELECT count(*) FROM btl.google_login_states WHERE expires_at>clock_timestamp()').fetchone()[0]<1024,'google','GOOGLE_BUSY')
            db.execute("INSERT INTO btl.google_login_states(state_hash,browser_hash,config_hash,nonce,verifier,phase,purpose,target_user_id) VALUES (%s,%s,%s,%s,%s,'NEW',%s,%s)",(key(state),key(browser),self.config_hash,nonce,verifier,purpose,target_user_id))
    def claim(self,state,browser):
        with connect(self.dsn) as db:
            db.row_factory=dict_row
            row=db.execute("UPDATE btl.google_login_states SET phase='CLAIMED' WHERE state_hash=%s AND browser_hash=%s AND config_hash=%s AND phase='NEW' AND expires_at>clock_timestamp() RETURNING nonce,verifier,purpose,target_user_id",(key(state),key(browser),self.config_hash)).fetchone()
            require(row is not None,'google','GOOGLE_STATE_REFUSED');return row
    def ready(self,state,subject,email,handoff,*,purpose='LOGIN',target_user_id=None):
        # Password work precedes every DB lock and never creates a usable password.
        unusable=PasswordHelper().hash(secrets.token_urlsafe(48))
        try:
            with connect(self.dsn) as db:
                db.row_factory=dict_row
                db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,12012))',(subject,))
                state_row=db.execute("SELECT purpose,target_user_id FROM btl.google_login_states WHERE state_hash=%s AND config_hash=%s AND phase='CLAIMED' FOR UPDATE",(key(state),self.config_hash)).fetchone()
                require(state_row is not None and (state_row['purpose'],state_row['target_user_id'])==(purpose,target_user_id),'google','GOOGLE_STATE_REFUSED')
                if purpose=='LINK':
                    require(target_user_id is not None,'google','GOOGLE_STATE_REFUSED')
                    row=db.execute('SELECT * FROM btl.users WHERE id=%s FOR UPDATE',(target_user_id,)).fetchone()
                    require(row is not None and row['is_active'] and row['is_verified'] and row['password_enabled'],'google','GOOGLE_ACCOUNT_UNAVAILABLE')
                    linked=db.execute("SELECT user_id FROM btl.account_identities WHERE provider='GOOGLE' AND provider_subject=%s",(subject,)).fetchone()
                    require(linked is None or linked['user_id']==target_user_id,'google','GOOGLE_ACCOUNT_CONFLICT')
                    legacy=db.execute('SELECT user_id FROM btl.google_identities WHERE subject=%s',(subject,)).fetchone()
                    require(legacy is None or legacy['user_id']==target_user_id,'google','GOOGLE_ACCOUNT_CONFLICT')
                    existing_google=db.execute("SELECT provider_subject FROM btl.account_identities WHERE provider='GOOGLE' AND user_id=%s",(target_user_id,)).fetchone()
                    require(existing_google is None or existing_google['provider_subject']==subject,'google','GOOGLE_ACCOUNT_CONFLICT')
                    db.execute("INSERT INTO btl.account_identities(provider,provider_subject,user_id,linked_by) VALUES ('GOOGLE',%s,%s,'GOOGLE_LINK') ON CONFLICT (provider,provider_subject) DO NOTHING",(subject,target_user_id))
                    if legacy is None:
                        db.execute('INSERT INTO btl.google_identities(subject,user_id,initial_email) VALUES (%s,%s,%s)',(subject,target_user_id,email))
                    db.execute("INSERT INTO btl.security_events(user_id,code) VALUES (%s,'GOOGLE_ACCOUNT_LINKED')",(target_user_id,))
                else:
                    identity=db.execute("SELECT user_id FROM btl.account_identities WHERE provider='GOOGLE' AND provider_subject=%s",(subject,)).fetchone()
                    if identity is None:
                        require(db.execute('SELECT id FROM btl.users WHERE email=%s',(email,)).fetchone() is None,'google','GOOGLE_ACCOUNT_CONFLICT')
                        user_id=uuid.uuid4()
                        row=db.execute('INSERT INTO btl.users(id,email,hashed_password,is_active,is_superuser,is_verified,password_enabled) VALUES (%s,%s,%s,true,false,true,false) RETURNING *',(user_id,email,unusable)).fetchone()
                        db.execute('INSERT INTO btl.google_identities(subject,user_id,initial_email) VALUES (%s,%s,%s)',(subject,user_id,email))
                        db.execute("INSERT INTO btl.account_identities(provider,provider_subject,user_id,linked_by) VALUES ('GOOGLE',%s,%s,'GOOGLE_SIGNUP')",(subject,user_id))
                        db.execute("INSERT INTO btl.security_events(user_id,code) VALUES (%s,'GOOGLE_USER_CREATED')",(user_id,))
                    else:
                        row=db.execute('SELECT * FROM btl.users WHERE id=%s FOR SHARE',(identity['user_id'],)).fetchone()
                        require(row is not None,'google','GOOGLE_ACCOUNT_UNAVAILABLE')
                        legacy=db.execute('SELECT user_id FROM btl.google_identities WHERE subject=%s',(subject,)).fetchone()
                        require(legacy is not None and legacy['user_id']==identity['user_id'],'google','GOOGLE_ACCOUNT_CONFLICT')
                require(row['is_active'] and row['is_verified'],'google','GOOGLE_ACCOUNT_UNAVAILABLE')
                claimed=db.execute("UPDATE btl.google_login_states SET phase='READY',user_id=%s,handoff_hash=%s WHERE state_hash=%s AND config_hash=%s AND phase='CLAIMED' AND expires_at>clock_timestamp() RETURNING state_hash",(row['id'],key(handoff),key(state),self.config_hash)).fetchone()
                require(claimed is not None,'google','GOOGLE_STATE_REFUSED')
                if purpose=='LOGIN':db.execute("INSERT INTO btl.security_events(user_id,code) VALUES (%s,'GOOGLE_IDENTITY_VERIFIED')",(row['id'],))
                return row['id']
        except psycopg.errors.UniqueViolation as error:
            raise ContractError('GOOGLE_ACCOUNT_CONFLICT','google') from error
    def exchange(self,handoff,browser):
        with connect(self.dsn) as db:
            db.row_factory=dict_row
            row=db.execute("UPDATE btl.google_login_states SET phase='EXCHANGED' WHERE handoff_hash=%s AND browser_hash=%s AND config_hash=%s AND phase='READY' AND expires_at>clock_timestamp() RETURNING user_id,purpose",(key(handoff),key(browser),self.config_hash)).fetchone()
            require(row is not None,'google','GOOGLE_STATE_REFUSED');return row


def grant_google_runtime(dsn,role):
    from infrastructure.database import grant_identity_runtime
    grant_identity_runtime(dsn,role)
    with connect(dsn) as db:
        db.execute(sql.SQL('GRANT SELECT,INSERT ON btl.google_identities TO {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON btl.google_login_states TO {}').format(sql.Identifier(role)))
