"""SQL persistence. Every task query includes the signed-in user's ID."""

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from Task import Task
from User import User
from ITask import utc_now
from LoginSession import LoginSession
from Reminder import Reminder
from Subtask import Subtask
from backend.database import Database, read_datetime



class TaskBuddyRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, entity) -> None:
        self.session.add(entity)
        self.save(entity)

    def save(self, entity) -> None:
        try:
            self.session.flush()
        except IntegrityError as error:
            if isinstance(entity, User):
                raise ServiceError("conflict", "That username is already in use.") from error
            raise

    def delete(self, entity) -> None:
        self.session.delete(entity)
        self.session.flush()

    def user_by_username(self, name: str) -> User | None:
        return self.session.scalar(select(User).where(User._usernameKey == name.strip().casefold()))

    def user_for_session(self, hashed_token: str) -> User | None:
        return self.session.scalar(
            select(User).join(LoginSession, LoginSession.userId == User.id).where(
                LoginSession.tokenHash == hashed_token, LoginSession.expiresAt > utc_now(),
            )
        )

    def delete_session(self, hashed_token: str) -> None:
        self.session.execute(delete(LoginSession).where(LoginSession.tokenHash == hashed_token))

    def delete_user_sessions(self, user_id: int, keep_hash: str | None = None) -> None:
        statement = delete(LoginSession).where(LoginSession.userId == user_id)
        if keep_hash:
            statement = statement.where(LoginSession.tokenHash != keep_hash)
        self.session.execute(statement)

    def delete_expired_sessions(self) -> None:
        self.session.execute(delete(LoginSession).where(LoginSession.expiresAt <= utc_now()))

    def tasks_for_user(self, user_id: int, view: str = "active") -> list[Task]:
        statement = select(Task).where(Task.userId == user_id)
        if view == "deleted":
            statement = statement.where(Task.isDeleted == True)
        elif view == "all":
            statement = statement.where(Task.isDeleted == False)
        else:
            statement = statement.where(Task.isDeleted == False, Task.isHidden == (view == "hidden"))
        return list(self.session.scalars(statement))

    def task_for_user(self, user_id: int, item_id: int) -> Task | None:
        return self.session.scalar(select(Task).where(Task.id == item_id, Task.userId == user_id))

    def subtask_for_user(self, user_id: int, item_id: int) -> Subtask | None:
        return self.session.scalar(select(Subtask).join(Subtask.parentTask).where(
            Subtask.id == item_id, Subtask.userId == user_id, Task.userId == user_id,
        ))

    def reminder_for_user(self, user_id: int, item_id: int) -> Reminder | None:
        reminder = self.session.get(Reminder, item_id)
        if reminder is None or reminder.task.userId != user_id:
            return None
        return reminder

    def due_reminders(self, now) -> list[Reminder]:
        parent = aliased(Task)
        statement = (
            select(Reminder)
            .outerjoin(Task, Reminder._task)
            .outerjoin(Subtask, Reminder._subtask)
            .outerjoin(parent, Subtask.parentTask)
            .where(
                Reminder._isSent == False, Reminder.reminderDate <= now,
                or_(
                    (Task.id.is_not(None)) & (Task.isDeleted == False) & (Task.isCompleted == False),
                    (Subtask.id.is_not(None)) & (Subtask.isCompleted == False)
                    & (parent.isDeleted == False) & (parent.isCompleted == False),
                ),
            )
            .order_by(Reminder.reminderDate, Reminder.id).limit(100)
        )
        return list(self.session.scalars(statement))

    def purge_expired_tasks(self, user_id: int, now) -> int:
        expired = list(self.session.scalars(select(Task).where(
            Task.userId == user_id, Task.isDeleted == True, Task.expiresAt <= now,
        )))
        for task in expired:
            self.session.delete(task)
        self.session.flush()
        return len(expired)

    def empty_deleted(self, user_id: int) -> int:
        deleted = self.tasks_for_user(user_id, "deleted")
        for task in deleted:
            self.session.delete(task)
        self.session.flush()
        return len(deleted)
