"""The Subtask implementation of ITask for the next development milestone."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from ITask import ITask, check_title
from Reminder import Reminder

if TYPE_CHECKING:
    from Task import Task


@dataclass
class Subtask(ITask):
    subtaskId: int
    title: str
    task: "Task" = field(repr=False)
    orderPosition: int = 0
    isCompleted: bool = False
    reminder: Reminder | None = field(default=None, repr=False)

    @classmethod
    def makeTask(cls, title: str, **kwargs) -> "Subtask":
        return cls(subtaskId=0, title=check_title(title), **kwargs)

    def editTask(self, title: str, description: str = "") -> None:
        self.title = check_title(title)

    def deleteTask(self) -> None:
        self.task.subtasks[:] = [item for item in self.task.subtasks if item is not self]
        self.deleteReminder()

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
