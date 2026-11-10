"""FastAPI routing and request-scoped controllers."""

import asyncio
from collections import deque
from contextlib import asynccontextmanager
import logging
from threading import Lock
from time import monotonic
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from User import User
from backend.config import Settings
from backend.controllers import AccountController, TaskController
from backend.database import DATABASE_ERRORS, Database
from backend.email_sender import EmailSender
from backend.errors import ServiceError
from backend.reminder_worker import run_reminder_worker
from backend.repository import TaskBuddyRepository
from backend.schemas import (
    CreateSubtaskRequest, CreateTaskRequest, DeleteAccountRequest, EditAccountRequest,
    LoginRequest, PasswordResetRequest, RegisterRequest, ReminderRequest, ReminderResponse,
    SessionResponse, SubtaskResponse, TaskResponse, UpdateSubtaskRequest, UpdateTaskRequest,
    UserResponse,
)
from backend.services import AccountService, ReminderService, TaskService

LOGGER = logging.getLogger("taskbuddy")
VERSION = "0.2.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    database = Database(settings)
    sender = EmailSender(settings)

    @asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()
        worker = None
        try:
            database.open()
            if settings.email_configured:
                worker = asyncio.create_task(run_reminder_worker(database, sender, settings, stop))
            yield
        finally:
            stop.set()
            if worker is not None:
                await worker
            database.close()

    app = FastAPI(title="TaskBuddy API", version=VERSION, lifespan=lifespan,
                  description="TaskBuddy desktop accounts, tasks, subtasks, reminders and JSON export.")
    app.state.database = database
    app.state.settings = settings
    bearer = HTTPBearer(auto_error=False)

    def get_repository():
        with database.session() as session:
            yield TaskBuddyRepository(session)

    RepositoryDep = Annotated[TaskBuddyRepository, Depends(get_repository, scope="function")]

    def account_controller(repository: RepositoryDep):
        return AccountController(AccountService(repository, settings))

    def task_controller(repository: RepositoryDep):
        return TaskController(TaskService(repository), ReminderService(repository, sender))

    AccountDep = Annotated[AccountController, Depends(account_controller)]
    TaskDep = Annotated[TaskController, Depends(task_controller)]

    def token(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> str:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(401, "Please log in to continue.", headers={"WWW-Authenticate": "Bearer"})
        return credentials.credentials

    TokenDep = Annotated[str, Depends(token)]

    def current_user(access_token: TokenDep, repository: RepositoryDep) -> User:
        return AccountService(repository, settings).current_user(access_token)

    UserDep = Annotated[User, Depends(current_user)]

    attempts = {}
    attempt_lock = Lock()

    def limit_auth(request: Request, action: str, username: str):
        now = monotonic()
        peer = request.client.host if request.client else "local"
        with attempt_lock:
            for key in list(attempts):
                while attempts[key] and attempts[key][0] < now - 60:
                    attempts[key].popleft()
                if not attempts[key]:
                    del attempts[key]
            keys = [("peer", peer), (action, peer, username.strip().casefold())]
            for key, limit in zip(keys, (60, 10)):
                if len(attempts.get(key, ())) >= limit:
                    raise HTTPException(429, "Too many attempts. Wait a minute and try again.",
                                        headers={"Retry-After": "60"})
            if len(attempts) > 4096:
                attempts.clear()
            for key in keys:
                attempts.setdefault(key, deque()).append(now)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        details = [{"loc": list(item["loc"]), "msg": item["msg"]} for item in error.errors()]
        return JSONResponse(status_code=422, content={"detail": details})

    @app.exception_handler(ServiceError)
    async def service_error(request, error):
        status = {"unauthorized": 401, "not_found": 404, "conflict": 409, "invalid": 400}[error.kind]
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
        return JSONResponse(status_code=status, content={"detail": str(error)}, headers=headers)

    @app.exception_handler(ValueError)
    async def invalid_value(request, error):
        return JSONResponse(status_code=400, content={"detail": str(error)})

    async def database_error(request, error):
        LOGGER.error("Database operation failed", exc_info=(type(error), error, error.__traceback__))
        return JSONResponse(status_code=503, content={"detail": "The database is temporarily unavailable. Please try again."})

    for error_type in DATABASE_ERRORS:
        app.add_exception_handler(error_type, database_error)

    @app.get("/health", tags=["Status"])
    def health():
        database.ping()
        return {"status": "ok", "database": settings.database_backend,
                "version": VERSION, "email_reminders": settings.email_configured}

    @app.post("/auth/register", response_model=SessionResponse, status_code=201, tags=["Accounts"])
    def register(details: RegisterRequest, request: Request, controller: AccountDep):
        limit_auth(request, "register", details.username)
        return controller.register(details)

    @app.post("/auth/login", response_model=SessionResponse, tags=["Accounts"])
    def login(details: LoginRequest, request: Request, controller: AccountDep):
        limit_auth(request, "login", details.username)
        return controller.login(details)

    @app.post("/auth/logout", status_code=204, tags=["Accounts"])
    def logout(access_token: TokenDep, user: UserDep, controller: AccountDep):
        controller.logout(access_token)
        return Response(status_code=204)

    @app.get("/auth/recovery-question", tags=["Accounts"])
    def recovery_question(request: Request, controller: AccountDep,
                          username: str = Query(min_length=1, max_length=40)):
        limit_auth(request, "question", username)
        return controller.recovery_question(username)

    @app.post("/auth/reset-password", status_code=204, tags=["Accounts"])
    def reset_password(details: PasswordResetRequest, request: Request, controller: AccountDep):
        limit_auth(request, "reset", details.username)
        controller.reset_password(details)
        return Response(status_code=204)

    @app.get("/users/me", response_model=UserResponse, tags=["Accounts"])
    def me(access_token: TokenDep, controller: AccountDep):
        return controller.me(access_token)

    @app.patch("/users/me", response_model=UserResponse, tags=["Accounts"])
    def edit_account(details: EditAccountRequest, user: UserDep, access_token: TokenDep, controller: AccountDep):
        return controller.edit_account(user, details, access_token)

    @app.delete("/users/me", status_code=204, tags=["Accounts"])
    def delete_account(details: DeleteAccountRequest, user: UserDep, controller: AccountDep):
        controller.delete_account(user, details)
        return Response(status_code=204)

    @app.get("/tasks", response_model=list[TaskResponse], tags=["Tasks"])
    def list_tasks(user: UserDep, controller: TaskDep,
                   view: Literal["active", "hidden", "deleted"] = "active",
                   search: str = Query(default="", max_length=200),
                   sort: Literal["newest", "oldest", "title_asc", "title_desc"] = "newest",
                   completion: Literal["all", "open", "completed"] = "all"):
        return controller.list_tasks(user, view, search, sort, completion)

    @app.post("/tasks", response_model=TaskResponse, status_code=201, tags=["Tasks"])
    def create_task(details: CreateTaskRequest, user: UserDep, controller: TaskDep):
        return controller.create_task(user, details)

    @app.get("/tasks/export", tags=["Tasks"])
    def export_tasks(user: UserDep, controller: TaskDep):
        return Response(
            content=controller.export_tasks(user), media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="taskbuddy-tasks.json"'},
        )

    @app.delete("/tasks/deleted", tags=["Tasks"])
    def empty_deleted(user: UserDep, controller: TaskDep):
        return controller.empty_deleted(user)

    @app.get("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
    def get_task(task_id: int, user: UserDep, controller: TaskDep):
        return controller.get_task(user, task_id)

    @app.patch("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
    def update_task(task_id: int, details: UpdateTaskRequest, user: UserDep, controller: TaskDep):
        return controller.update_task(user, task_id, details)

    @app.delete("/tasks/{task_id}", status_code=204, tags=["Tasks"])
    def delete_task(task_id: int, user: UserDep, controller: TaskDep):
        controller.delete_task(user, task_id)
        return Response(status_code=204)

    @app.post("/tasks/{task_id}/restore", response_model=TaskResponse, tags=["Tasks"])
    def restore_task(task_id: int, user: UserDep, controller: TaskDep):
        return controller.restore_task(user, task_id)

    @app.get("/tasks/{task_id}/subtasks", response_model=list[SubtaskResponse], tags=["Subtasks"])
    def list_subtasks(task_id: int, user: UserDep, controller: TaskDep):
        return controller.list_subtasks(user, task_id)

    @app.post("/tasks/{task_id}/subtasks", response_model=SubtaskResponse, status_code=201, tags=["Subtasks"])
    def add_subtask(task_id: int, details: CreateSubtaskRequest, user: UserDep, controller: TaskDep):
        return controller.add_subtask(user, task_id, details)

    @app.get("/subtasks/{subtask_id}", response_model=SubtaskResponse, tags=["Subtasks"])
    def get_subtask(subtask_id: int, user: UserDep, controller: TaskDep):
        return controller.get_subtask(user, subtask_id)

    @app.patch("/subtasks/{subtask_id}", response_model=SubtaskResponse, tags=["Subtasks"])
    def edit_subtask(subtask_id: int, details: UpdateSubtaskRequest, user: UserDep, controller: TaskDep):
        return controller.edit_subtask(user, subtask_id, details)

    @app.delete("/subtasks/{subtask_id}", status_code=204, tags=["Subtasks"])
    def delete_subtask(subtask_id: int, user: UserDep, controller: TaskDep):
        controller.delete_subtask(user, subtask_id)
        return Response(status_code=204)

    @app.post("/tasks/{task_id}/reminder", response_model=ReminderResponse, status_code=201, tags=["Reminders"])
    def set_task_reminder(task_id: int, details: ReminderRequest, user: UserDep, controller: TaskDep):
        return controller.set_reminder(user, task_id, "task", details)

    @app.post("/subtasks/{subtask_id}/reminder", response_model=ReminderResponse, status_code=201, tags=["Reminders"])
    def set_subtask_reminder(subtask_id: int, details: ReminderRequest, user: UserDep, controller: TaskDep):
        return controller.set_reminder(user, subtask_id, "subtask", details)

    @app.patch("/reminders/{reminder_id}", response_model=ReminderResponse, tags=["Reminders"])
    def edit_reminder(reminder_id: int, details: ReminderRequest, user: UserDep, controller: TaskDep):
        return controller.edit_reminder(user, reminder_id, details)

    @app.delete("/reminders/{reminder_id}", status_code=204, tags=["Reminders"])
    def delete_reminder(reminder_id: int, user: UserDep, controller: TaskDep):
        controller.delete_reminder(user, reminder_id)
        return Response(status_code=204)

    return app
