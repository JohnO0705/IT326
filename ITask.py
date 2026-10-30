"""The interface shared by Task and Subtask in the class diagram."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from Reminder import Reminder


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ITask(ABC):
    @classmethod
    @abstractmethod
    def makeTask(cls, title: str, **kwargs):
        """Create a task-like object."""

    @abstractmethod
    def editTask(self, title: str, description: str = "") -> None:
        """Change its editable details."""

    @abstractmethod
    def deleteTask(self) -> None:
        """Delete the task-like object."""

    @abstractmethod
    def setReminder(self, reminder: "Reminder") -> None:
        """Attach one reminder."""

    @abstractmethod
    def editReminder(self, reminder_date: datetime, email: str) -> None:
        """Change an attached reminder."""

    @abstractmethod
    def deleteReminder(self) -> None:
        """Remove an attached reminder."""


def check_title(title: str) -> str:
    title = title.strip()
    if not title or len(title) > 200:
        raise ValueError("A title must contain between 1 and 200 characters.")
    return title
