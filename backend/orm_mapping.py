"""Map plain domain classes to tables, outside their methods."""

from datetime import datetime, timezone
from threading import Lock

from sqlalchemy import (
    Boolean, CheckConstraint, Column, ForeignKey, Identity, Index, Integer,
    MetaData, String, Table, Text,
)
from sqlalchemy.dialects.oracle import TIMESTAMP
from sqlalchemy.orm import registry, relationship
from sqlalchemy.types import TypeDecorator

from ITask import ITask
from LoginSession import LoginSession
from Reminder import Reminder
from Subtask import Subtask
from Task import Task
from User import User


class UTCDateTime(TypeDecorator):
    """Read legacy SQLite timestamps and store the same UTC values in Oracle."""
    impl = String(40)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "oracle":
            return dialect.type_descriptor(TIMESTAMP())
        return dialect.type_descriptor(String(40))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value if dialect.name == "oracle" else value.isoformat(timespec="microseconds")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime):
            value = datetime.fromisoformat(str(value))
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


metadata = MetaData()
mapper_registry = registry(metadata=metadata)
_mapping_lock = Lock()
_configured = False


def flag(name):
    return Column(name, Boolean(create_constraint=True), nullable=False, server_default="0")


users = Table(
    "tb_users", metadata,
    Column("user_id", Integer, Identity(), primary_key=True),
    Column("username", String(40), nullable=False),
    Column("username_key", String(40), nullable=False, unique=True),
    Column("email", String(254), nullable=False),
    Column("password_hash", String(512), nullable=False),
    Column("created_at", UTCDateTime(), nullable=False),
    Column("security_question", String(200)),
    Column("security_answer_hash", String(512)),
    sqlite_autoincrement=True,
)


def task_columns():
    return [
        Column("user_id", Integer, ForeignKey("tb_users.user_id", ondelete="CASCADE"), nullable=False),
        Column("title", String(200), nullable=False),
        Column("description", Text),
        flag("is_pinned"), flag("is_hidden"), flag("is_deleted"), flag("is_completed"),
        Column("deleted_at", UTCDateTime()),
        Column("expires_at", UTCDateTime()),
        Column("created_at", UTCDateTime(), nullable=False),
        Column("updated_at", UTCDateTime(), nullable=False),
    ]


tasks = Table(
    "tb_tasks", metadata,
    Column("task_id", Integer, Identity(), primary_key=True),
    *task_columns(),
    sqlite_autoincrement=True,
)
Index("tb_tasks_user_idx", tasks.c.user_id, tasks.c.is_deleted, tasks.c.is_hidden)
subtasks = Table(
    "tb_subtasks", metadata,
    Column("subtask_id", Integer, Identity(), primary_key=True),
    Column("task_id", Integer, ForeignKey("tb_tasks.task_id", ondelete="CASCADE"), nullable=False),
    Column("order_position", Integer, nullable=False, server_default="0"),
    *task_columns(),
    sqlite_autoincrement=True,
)
Index("tb_subtasks_task_idx", subtasks.c.task_id, subtasks.c.order_position)
sessions = Table(
    "tb_sessions", metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("user_id", Integer, ForeignKey("tb_users.user_id", ondelete="CASCADE"), nullable=False),
    Column("expires_at", UTCDateTime(), nullable=False),
)
Index("tb_sessions_user_idx", sessions.c.user_id)
reminders = Table(
    "tb_reminders", metadata,
    Column("reminder_id", Integer, Identity(), primary_key=True),
    Column("task_id", Integer, ForeignKey("tb_tasks.task_id", ondelete="CASCADE"), unique=True),
    Column("subtask_id", Integer, ForeignKey("tb_subtasks.subtask_id", ondelete="CASCADE"), unique=True),
    Column("reminder_date", UTCDateTime(), nullable=False),
    Column("email", String(254), nullable=False),
    flag("is_sent"),
    Column("sent_at", UTCDateTime()),
    CheckConstraint(
        "(task_id IS NOT NULL AND subtask_id IS NULL) OR "
        "(task_id IS NULL AND subtask_id IS NOT NULL)",
        name="tb_reminder_parent_ck",
    ),
    sqlite_autoincrement=True,
)


def common_properties(table, key):
    return {
        "id": table.c[key], "userId": table.c.user_id,
        "isPinned": table.c.is_pinned, "isHidden": table.c.is_hidden,
        "isDeleted": table.c.is_deleted, "isCompleted": table.c.is_completed,
        "createdAt": table.c.created_at, "updatedAt": table.c.updated_at,
        "deletedAt": table.c.deleted_at, "expiresAt": table.c.expires_at,
    }


def configure_models() -> None:
    global _configured
    with _mapping_lock:
        if _configured:
            return
        mapper_registry.map_imperatively(User, users, properties={
            "id": users.c.user_id, "_usernameKey": users.c.username_key,
            "passwordHash": users.c.password_hash, "createdAt": users.c.created_at,
            "securityQuestion": users.c.security_question,
            "securityAnswerHash": users.c.security_answer_hash,
        })
        mapper_registry.map_imperatively(LoginSession, sessions, properties={
            "tokenHash": sessions.c.token_hash, "userId": sessions.c.user_id,
            "expiresAt": sessions.c.expires_at,
        })
        # ITask is an unmapped abstract base. Its inherited attributes are
        # mapped for both concrete classes, preserving the existing two tables.
        mapper_registry.map_imperatively(Task, tasks, properties={
            **common_properties(tasks, "task_id"),
            "subtasks": relationship(
                Subtask, back_populates="parentTask", cascade="all, delete-orphan",
                lazy="selectin", order_by=lambda: (Subtask.orderPosition, Subtask.id),
                foreign_keys=[subtasks.c.task_id],
            ),
            "reminder": relationship(
                Reminder, back_populates="_task", uselist=False,
                cascade="all, delete-orphan", single_parent=True, lazy="selectin",
                foreign_keys=[reminders.c.task_id],
            ),
        })
        mapper_registry.map_imperatively(Subtask, subtasks, properties={
            **common_properties(subtasks, "subtask_id"),
            "orderPosition": subtasks.c.order_position,
            "parentTask": relationship(
                Task, back_populates="subtasks", foreign_keys=[subtasks.c.task_id],
            ),
            "reminder": relationship(
                Reminder, back_populates="_subtask", uselist=False,
                cascade="all, delete-orphan", single_parent=True, lazy="selectin",
                foreign_keys=[reminders.c.subtask_id],
            ),
        })
        mapper_registry.map_imperatively(Reminder, reminders, properties={
            "id": reminders.c.reminder_id, "reminderDate": reminders.c.reminder_date,
            "sentAt": reminders.c.sent_at, "_isSent": reminders.c.is_sent,
            "_task": relationship(Task, back_populates="reminder", foreign_keys=[reminders.c.task_id]),
            "_subtask": relationship(Subtask, back_populates="reminder", foreign_keys=[reminders.c.subtask_id]),
        })
        mapper_registry.configure()
        _configured = True
