"""PostgreSQL implementations of mature FastAPI Users database protocols."""
import uuid
from datetime import datetime
from hashlib import sha256
from contextlib import asynccontextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg import sql
from pydantic import BaseModel
from fastapi_users import exceptions
from fastapi_users.db import BaseUserDatabase


class User(BaseModel):
    id: uuid.UUID
    email: str
    hashed_password: str
    is_active: bool
    is_superuser: bool
    is_verified: bool


class Token(BaseModel):
    token: str
    user_id: uuid.UUID
    created_at: datetime


class CredentialChanged(ValueError):
    pass


@asynccontextmanager
async def connection(dsn):
    db = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row, connect_timeout=5,
                                              options="-c statement_timeout=15000 -c lock_timeout=10000")
    async with db:
        yield db


async def audit(db, code, user_id=None):
    await db.execute("INSERT INTO btl.security_events(user_id,code) VALUES (%s,%s)", (user_id, code))


class UserStore(BaseUserDatabase[User, uuid.UUID]):
    def __init__(self, dsn):
        self.dsn = dsn

    async def get(self, id):
        async with connection(self.dsn) as db:
            row = await (await db.execute("SELECT * FROM btl.users WHERE id=%s", (id,))).fetchone()
            return User(**row) if row else None

    async def get_by_email(self, email):
        async with connection(self.dsn) as db:
            row = await (await db.execute("SELECT * FROM btl.users WHERE email=%s", (email.lower(),))).fetchone()
            return User(**row) if row else None

    async def create(self, create_dict):
        try:
            async with connection(self.dsn) as db:
                row = await (await db.execute("INSERT INTO btl.users VALUES (%s,%s,%s,true,false,false) RETURNING *",
                    (uuid.uuid4(), create_dict["email"].lower(), create_dict["hashed_password"]))).fetchone()
                await audit(db, "USER_REGISTERED", row["id"])
                return User(**row)
        except psycopg.errors.UniqueViolation:
            raise exceptions.UserAlreadyExists()

    async def update(self, user, update_dict):
        allowed = {"email", "hashed_password", "is_active", "is_superuser", "is_verified"}
        if not update_dict or not set(update_dict).issubset(allowed):
            raise ValueError("Unsupported identity update")
        values = dict(update_dict)
        if "email" in values:
            values["email"] = values["email"].lower()
        assignments = sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(key)) for key in values)
        async with connection(self.dsn) as db:
            # Reset token is bound by the library to the previous password hash.
            # CAS prevents concurrent reuse; revoke all sessions in same transaction.
            row = await (await db.execute(sql.SQL("UPDATE btl.users SET {} WHERE id=%s AND hashed_password=%s RETURNING *").format(assignments),
                    (*values.values(), user.id, user.hashed_password))).fetchone()
            if row is None:
                if "hashed_password" in values:
                    raise exceptions.InvalidResetPasswordToken()
                raise exceptions.UserNotExists()
            if "hashed_password" in values or values.get("is_active") is False:
                await db.execute("DELETE FROM btl.auth_sessions WHERE user_id=%s", (user.id,))
            await audit(db, "IDENTITY_UPDATED", user.id)
            return User(**row)


class TokenStore:
    def __init__(self, dsn):
        self.dsn = dsn

    @staticmethod
    def key(token):
        return sha256(token.encode("utf-8")).hexdigest()

    async def get_by_token(self, token, max_age=None):
        if type(token) is not str or not 16 <= len(token) <= 256:
            return None
        async with connection(self.dsn) as db:
            row = await (await db.execute("SELECT user_id,created_at FROM btl.auth_sessions WHERE token_hash=%s AND (%s::timestamptz IS NULL OR created_at >= %s)",
                            (self.key(token), max_age, max_age))).fetchone()
            return Token(token=token, **row) if row else None

    async def create(self, create_dict):
        async with connection(self.dsn) as db:
            user = await (await db.execute("SELECT hashed_password,is_active,is_verified FROM btl.users WHERE id=%s FOR UPDATE",
                                          (create_dict["user_id"],))).fetchone()
            if user is None or not user["is_active"] or not user["is_verified"] or user["hashed_password"] != create_dict.get("expected_hash"):
                raise CredentialChanged("Identity changed before session publication")
            row = await (await db.execute("INSERT INTO btl.auth_sessions(token_hash,user_id) VALUES (%s,%s) RETURNING user_id,created_at",
                            (self.key(create_dict["token"]), create_dict["user_id"]))).fetchone()
            await audit(db, "SESSION_CREATED", row["user_id"])
            return Token(token=create_dict["token"], **row)

    async def delete(self, token):
        async with connection(self.dsn) as db:
            await db.execute("DELETE FROM btl.auth_sessions WHERE token_hash=%s", (self.key(token.token),))
            await audit(db, "SESSION_REVOKED", token.user_id)

    async def revoke_all(self, user_id):
        async with connection(self.dsn) as db:
            await db.execute("SELECT id FROM btl.users WHERE id=%s FOR UPDATE", (user_id,))
            await db.execute("DELETE FROM btl.auth_sessions WHERE user_id=%s", (user_id,))
            await audit(db, "ALL_SESSIONS_REVOKED", user_id)
