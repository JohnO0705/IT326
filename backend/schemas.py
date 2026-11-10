"""Validate API input and explicitly select public response fields."""

from datetime import datetime
import re
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
from ITask import utc_now


def valid_email(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) or len(value) > 254:
        raise ValueError("Enter a valid email address.")
    return value


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(RequestModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    security_question: str = Field(min_length=3, max_length=200)
    security_answer: str = Field(min_length=3, max_length=200)

    @field_validator("username", "email", "security_question", "security_answer", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return valid_email(value)


class LoginRequest(RequestModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class EditAccountRequest(RequestModel):
    username: str | None = Field(default=None, min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str | None = Field(default=None, min_length=3, max_length=254)
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str | None = Field(default=None, min_length=8, max_length=128)
    security_question: str | None = Field(default=None, min_length=3, max_length=200)
    security_answer: str | None = Field(default=None, min_length=3, max_length=200)

    @field_validator("username", "email", "security_question", "security_answer", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return valid_email(value) if value is not None else None

    @model_validator(mode="after")
    def check_changes(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("An updated field cannot be null.")
        if ("security_question" in self.model_fields_set) != ("security_answer" in self.model_fields_set):
            raise ValueError("Provide both a recovery question and its answer.")
        return self


class DeleteAccountRequest(RequestModel):
    password: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(RequestModel):
    username: str = Field(min_length=1, max_length=40)
    security_answer: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)


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
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("An updated field cannot be null.")
        return self


class CreateSubtaskRequest(CreateTaskRequest):
    order_position: int | None = Field(default=None, ge=0, le=10000)


class UpdateSubtaskRequest(RequestModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    order_position: int | None = Field(default=None, ge=0, le=10000)
    is_completed: bool | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def no_null_updates(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("An updated field cannot be null.")
        return self


class ReminderRequest(RequestModel):
    reminder_date: AwareDatetime
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return valid_email(value)

    @field_validator("reminder_date")
    @classmethod
    def check_schedule(cls, value):
        if value <= utc_now():
            raise ValueError("Choose a future date and time.")
        return value


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


class ReminderResponse(BaseModel):
    reminder_id: int
    target_id: int
    target_type: Literal["task", "subtask"]
    reminder_date: datetime
    email: str
    sent_at: datetime | None


class SubtaskResponse(BaseModel):
    subtask_id: int
    task_id: int
    user_id: int
    title: str
    description: str
    order_position: int
    is_completed: bool
    reminder: ReminderResponse | None


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
    subtasks: list[SubtaskResponse]
    reminder: ReminderResponse | None
