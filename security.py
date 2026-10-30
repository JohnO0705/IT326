"""Argon2 passwords and random, revocable server-side sessions."""

import hashlib
import secrets

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

PASSWORD_HASH = PasswordHash.recommended()
DUMMY_HASH = PASSWORD_HASH.hash("unused-account-lookup-timing-value")


def hash_password(password: str) -> str:
    return PASSWORD_HASH.hash(password)


def verify_password(password: str, saved_hash: str) -> bool:
    try:
        return PASSWORD_HASH.verify(password, saved_hash)
    except (ValueError, UnknownHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
