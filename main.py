"""FastAPI routes. Run from the project root with python run_server.py."""

from contextlib import asynccontextmanager
import logging
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from User import User
from backend.config import Settings
from backend.database import DATABASE_ERRORS, Database
from backend.repository import TaskBuddyRepository
from backend.schemas import (
    CreateTaskRequest, LoginRequest, RegisterRequest, SessionResponse,
    TaskResponse, UpdateTaskRequest, UserResponse,
)
from backend.services import AccountService, TaskService

LOGGER = logging.getLogger("taskbuddy")
VERSION = "0.1.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    database = Database(settings)
    repository = TaskBuddyRepository(database)
    accounts = AccountService(repository, settings)
    tasks = TaskService(repository)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            database.open()
            yield
        finally:
            database.close()

    app = FastAPI(title="TaskBuddy API", version=VERSION, lifespan=lifespan,
                  description="Accounts and task management for the TaskBuddy desktop application.")
    app.state.database = database
    app.state.settings = settings
    bearer = HTTPBearer(auto_error=False)

    def token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(401, "Please log in to continue.",
                                headers={"WWW-Authenticate": "Bearer"})
        return credentials.credentials

    def current_user(access_token: str = Depends(token)) -> User:
        return accounts.current_user(access_token)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Do not echo passwords or other request values in validation responses.
        details = [{"loc": list(item["loc"]), "msg": item["msg"]} for item in error.errors()]
        return JSONResponse(status_code=422, content={"detail": details})

    async def database_error(request, error):
        LOGGER.error("Database operation failed", exc_info=(type(error), error, error.__traceback__))
        return JSONResponse(status_code=503, content={
            "detail": "The database is temporarily unavailable. Check the backend connection and try again."
        })

    for error_type in DATABASE_ERRORS:
        app.add_exception_handler(error_type, database_error)

    @app.get("/health", tags=["Status"])
    def health():
        database.ping()
        return {"status": "ok", "database": settings.database_backend, "version": VERSION}

    @app.post("/auth/register", response_model=SessionResponse, status_code=201, tags=["Accounts"])
    def register(details: RegisterRequest):
        return accounts.register(details)

    @app.post("/auth/login", response_model=SessionResponse, tags=["Accounts"])
    def login(details: LoginRequest):
        return accounts.login(details)

    @app.post("/auth/logout", status_code=204, tags=["Accounts"])
    def logout(access_token: str = Depends(token), user: User = Depends(current_user)):
        accounts.logout(access_token)
        return Response(status_code=204)

    @app.get("/users/me", response_model=UserResponse, tags=["Accounts"])
    def me(user: User = Depends(current_user)):
        return user.public_details()

    @app.get("/tasks", response_model=list[TaskResponse], tags=["Tasks"])
    def list_tasks(
        view: Literal["active", "hidden", "deleted"] = "active",
        search: str = Query(default="", max_length=200),
        sort: Literal["newest", "oldest", "title_asc", "title_desc"] = "newest",
        completion: Literal["all", "open", "completed"] = "all",
        user: User = Depends(current_user),
    ):
        return tasks.list_tasks(user, view, search, sort, completion)

    @app.post("/tasks", response_model=TaskResponse, status_code=201, tags=["Tasks"])
    def create_task(details: CreateTaskRequest, user: User = Depends(current_user)):
        return tasks.create_task(user, details)

    @app.delete("/tasks/deleted", tags=["Tasks"])
    def empty_deleted(user: User = Depends(current_user)):
        return tasks.empty_deleted(user)

    @app.get("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
    def get_task(task_id: int, user: User = Depends(current_user)):
        return tasks.get_task(user, task_id).public_details()

    @app.patch("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
    def update_task(task_id: int, details: UpdateTaskRequest, user: User = Depends(current_user)):
        return tasks.update_task(user, task_id, details)

    @app.delete("/tasks/{task_id}", status_code=204, tags=["Tasks"])
    def delete_task(task_id: int, user: User = Depends(current_user)):
        tasks.delete_task(user, task_id)
        return Response(status_code=204)

    @app.post("/tasks/{task_id}/restore", response_model=TaskResponse, tags=["Tasks"])
    def restore_task(task_id: int, user: User = Depends(current_user)):
        return tasks.restore_task(user, task_id)

    return app
