"""Request validation and public response shapes."""

from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(RequestModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username", "email", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address.")
        return value.lower()


class LoginRequest(RequestModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    user_id: int
    username: str
    email: str
    created_at: datetime


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserResponse


class CreateTaskRequest(RequestModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class UpdateTaskRequest(RequestModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    is_pinned: bool | None = None
    is_hidden: bool | None = None
    is_completed: bool | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def no_null_updates(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("An updated field cannot be null.")
        return self


class TaskResponse(BaseModel):
    task_id: int
    user_id: int
    title: str
    description: str
    is_pinned: bool
    is_hidden: bool
    is_deleted: bool
    is_completed: bool
    deleted_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
