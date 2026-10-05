"""Opt-in versioned auth factory. No trading route or default principal."""
import os
import uuid

from fastapi import FastAPI, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, ConfigDict
from fastapi_users import FastAPIUsers, schemas
from fastapi_users.authentication import AuthenticationBackend, BearerTransport
from fastapi_users.authentication.strategy.db import DatabaseStrategy

from identity.store import UserStore, TokenStore, User, CredentialChanged
from identity.manager import UserManager
from identity.boundary import IdentityBoundary
from identity.delivery import SmtpDelivery


class UserRead(schemas.BaseUser[uuid.UUID]):
    pass


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str

    def create_update_dict(self):
        return self.model_dump()

    def create_update_dict_superuser(self):
        return self.model_dump()


class GuardedDatabaseStrategy(DatabaseStrategy):
    async def write_token(self, user):
        # Reuse the mature strategy's opaque token generation; add a transactional
        # credential-snapshot guard, never a second cryptographic/token format.
        values = {**self._create_access_token_dict(user), "expected_hash": user.hashed_password}
        try:
            return (await self.database.create(values)).token
        except CredentialChanged:
            raise HTTPException(status_code=400, detail="LOGIN_BAD_CREDENTIALS")


def create_app(dsn, secret, delivery, *, rate_limit=30, session_seconds=1800):
    if not dsn or type(secret) is not str or len(secret) < 64 or delivery is None:
        raise ValueError("Database, high-entropy auth secret and delivery required")
    if type(session_seconds) is not int or not 60 <= session_seconds <= 86400:
        raise ValueError("Bounded session lifetime required")
    user_store, token_store = UserStore(dsn), TokenStore(dsn)
    async def manager():
        return UserManager(user_store, secret, delivery)
    def strategy():
        return GuardedDatabaseStrategy(token_store, lifetime_seconds=session_seconds)
    backend = AuthenticationBackend(name="database", transport=BearerTransport(tokenUrl="api/v1/auth/login"), get_strategy=strategy)
    users = FastAPIUsers[User, uuid.UUID](manager, [backend])
    app = FastAPI(title="Backtest Lab identity API", version="1", docs_url=None, redoc_url=None, debug=False)
    app.add_middleware(IdentityBoundary, dsn=dsn, limit=rate_limit)
    app.include_router(users.get_register_router(UserRead, UserCreate), prefix="/api/v1/auth")
    app.include_router(users.get_auth_router(backend, requires_verification=True), prefix="/api/v1/auth")
    app.include_router(users.get_verify_router(UserRead), prefix="/api/v1/auth")
    app.include_router(users.get_reset_password_router(), prefix="/api/v1/auth")
    current = users.current_user(active=True, verified=True)
    @app.get("/api/v1/auth/me", response_model=UserRead)
    async def me(user: User = Depends(current)):
        return user
    @app.post("/api/v1/auth/logout-all", status_code=204)
    async def logout_all(user: User = Depends(current)):
        await token_store.revoke_all(user.id)
    @app.exception_handler(RequestValidationError)
    async def invalid(request, error):
        # Pydantic's default error input can contain a password/token.
        return JSONResponse({"detail": "INVALID_REQUEST"}, status_code=422)
    app.state.current_user = current
    app.state.dsn = dsn
    return app


def from_environment():
    delivery = SmtpDelivery(os.environ["BTL_SMTP_HOST"], os.environ["BTL_SMTP_USER"],
                            os.environ["BTL_SMTP_PASSWORD"], os.environ["BTL_SMTP_SENDER"])
    return create_app(os.environ["BTL_DATABASE_URL"], os.environ["BTL_AUTH_SECRET"], delivery)
