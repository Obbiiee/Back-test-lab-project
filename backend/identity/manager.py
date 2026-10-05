"""Library policy hooks; cryptography/token verification stays in FastAPI Users."""
import uuid
from fastapi_users import BaseUserManager, UUIDIDMixin, exceptions
from .store import User


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    def __init__(self, store, secret, delivery):
        super().__init__(store)
        self.reset_password_token_secret = secret
        self.verification_token_secret = secret
        self.reset_password_token_lifetime_seconds = 1800
        self.verification_token_lifetime_seconds = 3600
        self.delivery = delivery

    async def validate_password(self, password, user):
        if not 15 <= len(password) <= 128 or any(0xD800 <= ord(char) <= 0xDFFF for char in password) or password.isspace():
            raise exceptions.InvalidPasswordException(reason="Use 15–128 characters")

    async def on_after_register(self, user, request=None):
        await self.request_verify(user, request)

    async def on_after_request_verify(self, user, token, request=None):
        await self.delivery.send(user.email, "verification", token)

    async def on_after_forgot_password(self, user, token, request=None):
        await self.delivery.send(user.email, "recovery", token)
