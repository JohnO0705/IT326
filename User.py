"""TaskBuddy account data. Password hashes never belong in API responses."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from ITask import utc_now


@dataclass
class User:
    userId: int
    username: str
    email: str
    passwordHash: str = field(repr=False)
    createdAt: datetime = field(default_factory=utc_now)

    @classmethod
    def createAccount(cls, username: str, email: str, password_hash: str) -> "User":
        return cls(0, username.strip(), email.strip().lower(), password_hash)

    def login(self, password: str, verify: Callable[[str, str], bool]) -> bool:
        return verify(password, self.passwordHash)

    def editAccount(self, username: str, email: str) -> None:
        self.username = username.strip()
        self.email = email.strip().lower()

    def public_details(self) -> dict:
        return {
            "user_id": self.userId,
            "username": self.username,
            "email": self.email,
            "created_at": self.createdAt,
        }
