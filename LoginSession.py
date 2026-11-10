"""Stored session data; the actual bearer token stays in the desktop."""

from datetime import datetime


class LoginSession:
    def __init__(self, tokenHash: str, userId: int, expiresAt: datetime):
        self.tokenHash = tokenHash
        self.userId = userId
        self.expiresAt = expiresAt

    def isExpired(self, now: datetime) -> bool:
        return self.expiresAt <= now
