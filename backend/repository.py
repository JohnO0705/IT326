"""SQL persistence. Every task query includes the signed-in user's ID."""

from Task import Task
from User import User
from ITask import utc_now
from backend.database import Database, read_datetime


def user_from_row(row: dict | None) -> User | None:
    if row is None:
        return None
    return User(
        userId=int(row["user_id"]),
        username=row["username"],
        email=row["email"],
        passwordHash=row["password_hash"],
        createdAt=read_datetime(row["created_at"]),
    )


def task_from_row(row: dict) -> Task:
    return Task(
        taskId=int(row["task_id"]),
        userId=int(row["user_id"]),
        title=row["title"],
        description=row["description"] or "",
        isPinned=bool(row["is_pinned"]),
        isHidden=bool(row["is_hidden"]),
        isDeleted=bool(row["is_deleted"]),
        isCompleted=bool(row["is_completed"]),
        deletedAt=read_datetime(row["deleted_at"]),
        expiresAt=read_datetime(row["expires_at"]),
        createdAt=read_datetime(row["created_at"]),
        updatedAt=read_datetime(row["updated_at"]),
    )


class TaskBuddyRepository:
    def __init__(self, database: Database):
        self.database = database

    def find_user_by_username(self, username: str) -> User | None:
        return user_from_row(self.database.fetch_one(
            "SELECT * FROM tb_users WHERE username_key = :username_key",
            {"username_key": username.strip().casefold()},
        ))

    def create_user(self, user: User) -> User:
        user.userId = self.database.insert_id(
            """INSERT INTO tb_users (username, username_key, email, password_hash, created_at)
               VALUES (:username, :username_key, :email, :password_hash, :created_at)""",
            {
                "username": user.username,
                "username_key": user.username.casefold(),
                "email": user.email,
                "password_hash": user.passwordHash,
                "created_at": self.database.bind_datetime(user.createdAt),
            },
            "user_id",
        )
        return user

    def save_session(self, token_hash: str, user_id: int, expires_at) -> None:
        self.database.execute(
            "DELETE FROM tb_sessions WHERE expires_at <= :now",
            {"now": self.database.bind_datetime(utc_now())},
        )
        self.database.execute(
            """INSERT INTO tb_sessions (token_hash, user_id, expires_at)
               VALUES (:token_hash, :user_id, :expires_at)""",
            {"token_hash": token_hash, "user_id": user_id,
             "expires_at": self.database.bind_datetime(expires_at)},
        )

    def find_session_user(self, token_hash: str) -> User | None:
        return user_from_row(self.database.fetch_one(
            """SELECT u.* FROM tb_users u JOIN tb_sessions s ON u.user_id = s.user_id
               WHERE s.token_hash = :token_hash AND s.expires_at > :now""",
            {"token_hash": token_hash, "now": self.database.bind_datetime(utc_now())},
        ))

    def delete_session(self, token_hash: str) -> None:
        self.database.execute(
            "DELETE FROM tb_sessions WHERE token_hash = :token_hash",
            {"token_hash": token_hash},
        )

    def purge_expired_tasks(self, user_id: int) -> None:
        self.database.execute(
            """DELETE FROM tb_tasks
               WHERE user_id = :user_id AND is_deleted = 1 AND expires_at <= :now""",
            {"user_id": user_id, "now": self.database.bind_datetime(utc_now())},
        )

    def list_tasks(self, user_id: int, view: str) -> list[Task]:
        conditions = {
            "active": "is_deleted = 0 AND is_hidden = 0",
            "hidden": "is_deleted = 0 AND is_hidden = 1",
            "deleted": "is_deleted = 1",
        }
        # view is selected from these constants, never interpolated user SQL.
        condition = conditions[view]
        return [task_from_row(row) for row in self.database.fetch_all(
            "SELECT * FROM tb_tasks WHERE user_id = :user_id AND " + condition,
            {"user_id": user_id},
        )]

    def find_task(self, user_id: int, task_id: int) -> Task | None:
        row = self.database.fetch_one(
            "SELECT * FROM tb_tasks WHERE task_id = :task_id AND user_id = :user_id",
            {"task_id": task_id, "user_id": user_id},
        )
        return task_from_row(row) if row else None

    def _task_parameters(self, task: Task) -> dict:
        return {
            "user_id": task.userId,
            "title": task.title,
            "description": task.description,
            "is_pinned": int(task.isPinned),
            "is_hidden": int(task.isHidden),
            "is_deleted": int(task.isDeleted),
            "is_completed": int(task.isCompleted),
            "deleted_at": self.database.bind_datetime(task.deletedAt),
            "expires_at": self.database.bind_datetime(task.expiresAt),
            "created_at": self.database.bind_datetime(task.createdAt),
            "updated_at": self.database.bind_datetime(task.updatedAt),
        }

    def create_task(self, task: Task) -> Task:
        task.taskId = self.database.insert_id(
            """INSERT INTO tb_tasks (
                user_id, title, description, is_pinned, is_hidden, is_deleted,
                is_completed, deleted_at, expires_at, created_at, updated_at
            ) VALUES (
                :user_id, :title, :description, :is_pinned, :is_hidden, :is_deleted,
                :is_completed, :deleted_at, :expires_at, :created_at, :updated_at
            )""",
            self._task_parameters(task),
            "task_id",
        )
        return task

    def save_task(self, task: Task) -> Task:
        parameters = self._task_parameters(task)
        parameters.pop("created_at")
        parameters["task_id"] = task.taskId
        self.database.execute(
            """UPDATE tb_tasks SET
                title = :title, description = :description, is_pinned = :is_pinned,
                is_hidden = :is_hidden, is_deleted = :is_deleted,
                is_completed = :is_completed, deleted_at = :deleted_at,
                expires_at = :expires_at, updated_at = :updated_at
               WHERE task_id = :task_id AND user_id = :user_id""",
            parameters,
        )
        return task

    def empty_deleted(self, user_id: int) -> int:
        return self.database.execute(
            "DELETE FROM tb_tasks WHERE user_id = :user_id AND is_deleted = 1",
            {"user_id": user_id},
        )
