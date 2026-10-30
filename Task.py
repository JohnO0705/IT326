"""Task state and task operations from the TaskBuddy class model."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from ITask import ITask, check_title, utc_now
from Reminder import Reminder

if TYPE_CHECKING:
    from Subtask import Subtask


@dataclass
class Task(ITask):
    taskId: int
    title: str
    userId: int
    description: str = ""
    isPinned: bool = False
    isHidden: bool = False
    isDeleted: bool = False
    isCompleted: bool = False
    deletedAt: datetime | None = None
    expiresAt: datetime | None = None
    createdAt: datetime = field(default_factory=utc_now)
    updatedAt: datetime = field(default_factory=utc_now)
    reminder: Reminder | None = field(default=None, repr=False)
    subtasks: list["Subtask"] = field(default_factory=list, repr=False)

    @classmethod
    def makeTask(cls, title: str, **kwargs) -> "Task":
        return cls(taskId=0, title=check_title(title), **kwargs)

    def editTask(self, title: str, description: str = "") -> None:
        self.title = check_title(title)
        self.description = description
        self.updatedAt = utc_now()

    def deleteTask(self) -> None:
        self.isDeleted = True
        self.deletedAt = utc_now()
        self.expiresAt = self.deletedAt + timedelta(days=7)
        self.updatedAt = self.deletedAt

    def restoreTask(self) -> None:
        if not self.isDeleted:
            raise ValueError("This task is already in your task list.")
        if self.expiresAt and self.expiresAt <= utc_now():
            raise ValueError("This task's seven-day recovery period has ended.")
        self.isDeleted = False
        self.isHidden = False
        self.deletedAt = self.expiresAt = None
        self.updatedAt = utc_now()

    def pinTask(self, pinned: bool) -> None:
        self.isPinned = pinned
        self.updatedAt = utc_now()

    def hideTask(self) -> None:
        self.isHidden = True
        self.updatedAt = utc_now()

    def unhideTask(self) -> None:
        self.isHidden = False
        self.updatedAt = utc_now()

    def completeTask(self, completed: bool) -> None:
        self.isCompleted = completed
        self.updatedAt = utc_now()

    def setReminder(self, reminder: Reminder) -> None:
        reminder.task = self
        self.reminder = reminder

    def editReminder(self, reminder_date: datetime, email: str) -> None:
        if self.reminder is None:
            raise ValueError("There is no reminder to edit.")
        self.reminder.reminderDate = reminder_date
        self.reminder.email = email

    def deleteReminder(self) -> None:
        self.reminder = None

    def public_details(self) -> dict:
        return {
            "task_id": self.taskId,
            "user_id": self.userId,
            "title": self.title,
            "description": self.description,
            "is_pinned": self.isPinned,
            "is_hidden": self.isHidden,
            "is_deleted": self.isDeleted,
            "is_completed": self.isCompleted,
            "deleted_at": self.deletedAt,
            "expires_at": self.expiresAt,
            "created_at": self.createdAt,
            "updated_at": self.updatedAt,
        }
