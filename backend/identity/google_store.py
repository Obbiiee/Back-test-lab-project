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
    def begin(self,state,browser,nonce,verifier):
        with connect(self.dsn) as db:
            db.execute('SELECT pg_advisory_xact_lock(2020,12)')
            db.execute('DELETE FROM btl.google_login_states WHERE state_hash IN (SELECT state_hash FROM btl.google_login_states WHERE expires_at<=clock_timestamp() ORDER BY expires_at LIMIT 1000)')
            require(db.execute('SELECT count(*) FROM btl.google_login_states WHERE expires_at>clock_timestamp()').fetchone()[0]<1024,'google','GOOGLE_BUSY')
            db.execute("INSERT INTO btl.google_login_states(state_hash,browser_hash,config_hash,nonce,verifier,phase) VALUES (%s,%s,%s,%s,%s,'NEW')",(key(state),key(browser),self.config_hash,nonce,verifier))
    def claim(self,state,browser):
        with connect(self.dsn) as db:
            row=db.execute("UPDATE btl.google_login_states SET phase='CLAIMED' WHERE state_hash=%s AND browser_hash=%s AND config_hash=%s AND phase='NEW' AND expires_at>clock_timestamp() RETURNING nonce,verifier",(key(state),key(browser),self.config_hash)).fetchone()
            require(row is not None,'google','GOOGLE_STATE_REFUSED');return row
    def ready(self,state,subject,email,handoff):
        # Password work precedes every DB lock and never creates a usable password.
        unusable=PasswordHelper().hash(secrets.token_urlsafe(48))
        try:
            with connect(self.dsn) as db:
                db.row_factory=dict_row
                db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,12012))',(subject,))
                row=db.execute('SELECT u.* FROM btl.google_identities g JOIN btl.users u ON u.id=g.user_id WHERE g.subject=%s FOR SHARE OF u',(subject,)).fetchone()
                if row is None:
                    require(db.execute('SELECT id FROM btl.users WHERE email=%s',(email,)).fetchone() is None,'google','GOOGLE_ACCOUNT_CONFLICT')
                    user_id=uuid.uuid4()
                    row=db.execute('INSERT INTO btl.users(id,email,hashed_password,is_active,is_superuser,is_verified,password_enabled) VALUES (%s,%s,%s,true,false,true,false) RETURNING *',(user_id,email,unusable)).fetchone()
                    db.execute('INSERT INTO btl.google_identities(subject,user_id,initial_email) VALUES (%s,%s,%s)',(subject,user_id,email))
                    db.execute("INSERT INTO btl.security_events(user_id,code) VALUES (%s,'GOOGLE_USER_CREATED')",(user_id,))
                require(row['is_active'] and row['is_verified'] and row['password_enabled'] is False,'google','GOOGLE_ACCOUNT_UNAVAILABLE')
                claimed=db.execute("UPDATE btl.google_login_states SET phase='READY',user_id=%s,handoff_hash=%s WHERE state_hash=%s AND config_hash=%s AND phase='CLAIMED' AND expires_at>clock_timestamp() RETURNING state_hash",(row['id'],key(handoff),key(state),self.config_hash)).fetchone()
                require(claimed is not None,'google','GOOGLE_STATE_REFUSED')
                db.execute("INSERT INTO btl.security_events(user_id,code) VALUES (%s,'GOOGLE_IDENTITY_VERIFIED')",(row['id'],))
                return row['id']
        except psycopg.errors.UniqueViolation as error:
            raise ContractError('GOOGLE_ACCOUNT_CONFLICT','google') from error
    def exchange(self,handoff,browser):
        with connect(self.dsn) as db:
            row=db.execute("UPDATE btl.google_login_states SET phase='EXCHANGED' WHERE handoff_hash=%s AND browser_hash=%s AND config_hash=%s AND phase='READY' AND expires_at>clock_timestamp() RETURNING user_id",(key(handoff),key(browser),self.config_hash)).fetchone()
            require(row is not None,'google','GOOGLE_STATE_REFUSED');return row[0]


def grant_google_runtime(dsn,role):
    from infrastructure.database import grant_identity_runtime
    grant_identity_runtime(dsn,role)
    with connect(dsn) as db:
        db.execute(sql.SQL('GRANT SELECT,INSERT ON btl.google_identities TO {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON btl.google_login_states TO {}').format(sql.Identifier(role)))
