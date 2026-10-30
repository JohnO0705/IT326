"""Reminder domain object; email delivery is a later milestone."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ITask import ITask


@dataclass
class Reminder:
    reminderId: int
    task: "ITask" = field(repr=False)
    reminderDate: datetime
    email: str
