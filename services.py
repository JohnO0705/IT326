"""Application behavior between FastAPI routes and SQL persistence."""

from datetime import timedelta

from fastapi import HTTPException

from ITask import utc_now
from Task import Task
from TaskFilter import TaskFilter
from User import User
from backend.config import Settings
from backend.database import DATABASE_ERRORS, is_duplicate
from backend.repository import TaskBuddyRepository
from backend.schemas import CreateTaskRequest, LoginRequest, RegisterRequest, UpdateTaskRequest
from backend.security import DUMMY_HASH, hash_password, new_token, token_hash, verify_password


class AccountService:
    def __init__(self, repository: TaskBuddyRepository, settings: Settings):
        self.repository = repository
        self.settings = settings

    def register(self, details: RegisterRequest) -> dict:
        user = User.createAccount(details.username, details.email, hash_password(details.password))
        try:
            self.repository.create_user(user)
        except DATABASE_ERRORS as error:
            if is_duplicate(error):
                raise HTTPException(409, "That username is already in use.") from error
            raise
        return self._create_session(user)

    def login(self, details: LoginRequest) -> dict:
        user = self.repository.find_user_by_username(details.username)
        valid = user.login(details.password, verify_password) if user else verify_password(details.password, DUMMY_HASH)
        if not user or not valid:
            raise HTTPException(401, "The username or password is incorrect.")
        return self._create_session(user)

    def _create_session(self, user: User) -> dict:
        token = new_token()
        expires_at = utc_now() + timedelta(hours=self.settings.session_hours)
        self.repository.save_session(token_hash(token), user.userId, expires_at)
        return {"access_token": token, "token_type": "bearer",
                "expires_at": expires_at, "user": user.public_details()}

    def current_user(self, token: str) -> User:
        user = self.repository.find_session_user(token_hash(token))
        if user is None:
            raise HTTPException(401, "Your session has ended. Please log in again.",
                                headers={"WWW-Authenticate": "Bearer"})
        return user

    def logout(self, token: str) -> None:
        self.repository.delete_session(token_hash(token))


class TaskService:
    def __init__(self, repository: TaskBuddyRepository):
        self.repository = repository

    def list_tasks(self, user: User, view: str, search: str, sort: str, completion: str) -> list[dict]:
        self.repository.purge_expired_tasks(user.userId)
        tasks = self.repository.list_tasks(user.userId, view)
        task_filter = TaskFilter(
            filterCriteria=search,
            sortField="title" if sort.startswith("title") else "createdAt",
            sortOrder="ascending" if sort in {"oldest", "title_asc"} else "descending",
        )
        tasks = task_filter.sortTasks(task_filter.filterTasks(tasks, completion))
        return [task.public_details() for task in tasks]

    def get_task(self, user: User, task_id: int) -> Task:
        self.repository.purge_expired_tasks(user.userId)
        task = self.repository.find_task(user.userId, task_id)
        if task is None:
            raise HTTPException(404, "That task could not be found.")
        return task

    def create_task(self, user: User, details: CreateTaskRequest) -> dict:
        task = Task.makeTask(details.title, userId=user.userId, description=details.description)
        return self.repository.create_task(task).public_details()

    def update_task(self, user: User, task_id: int, details: UpdateTaskRequest) -> dict:
        task = self.get_task(user, task_id)
        if task.isDeleted:
            raise HTTPException(409, "Restore this task before editing it.")
        changes = details.model_dump(exclude_unset=True)
        if "title" in changes or "description" in changes:
            task.editTask(changes.get("title", task.title), changes.get("description", task.description))
        if "is_pinned" in changes:
            task.pinTask(changes["is_pinned"])
        if "is_hidden" in changes:
            task.hideTask() if changes["is_hidden"] else task.unhideTask()
        if "is_completed" in changes:
            task.completeTask(changes["is_completed"])
        return self.repository.save_task(task).public_details()

    def delete_task(self, user: User, task_id: int) -> None:
        task = self.get_task(user, task_id)
        if task.isDeleted:
            raise HTTPException(409, "This task is already in Recently Deleted.")
        task.deleteTask()
        self.repository.save_task(task)

    def restore_task(self, user: User, task_id: int) -> dict:
        task = self.get_task(user, task_id)
        if not task.isDeleted:
            raise HTTPException(409, "This task is already in your task list.")
        task.restoreTask()
        return self.repository.save_task(task).public_details()

    def empty_deleted(self, user: User) -> dict:
        return {"deleted_count": self.repository.empty_deleted(user.userId)}
