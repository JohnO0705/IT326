"""Use cases work with domain objects and repositories, independent of HTTP."""

from datetime import timedelta
import json
import logging
import smtplib

from ITask import utc_now
from LoginSession import LoginSession
from Reminder import Reminder
from Subtask import Subtask
from Task import Task
from TaskFilter import TaskFilter
from User import User
from backend.config import Settings
from backend.email_sender import EmailSender
from backend.errors import ServiceError
from backend.public_data import task_data
from backend.repository import TaskBuddyRepository
from backend.security import DUMMY_HASH, hash_password, new_token, token_hash, verify_password

LOGGER = logging.getLogger("taskbuddy")


def normalize_answer(answer: str) -> str:
    return " ".join(answer.split()).casefold()


class AccountService:
    def __init__(self, repository: TaskBuddyRepository, settings: Settings):
        self.repository = repository
        self.settings = settings

    def register(self, details: dict) -> dict:
        user = User(
            details["username"], details["email"], hash_password(details["password"]),
            details["security_question"], hash_password(normalize_answer(details["security_answer"])),
        )
        self.repository.add(user)
        return self._create_session(user)

    def login(self, username: str, password: str) -> dict:
        user = self.repository.user_by_username(username)
        valid = verify_password(password, user.passwordHash if user else DUMMY_HASH)
        if not user or not valid:
            raise ServiceError("unauthorized", "The username or password is incorrect.")
        return self._create_session(user)

    def _create_session(self, user: User) -> dict:
        token = new_token()
        expiry = utc_now() + timedelta(hours=self.settings.session_hours)
        self.repository.delete_expired_sessions()
        self.repository.add(LoginSession(token_hash(token), user.id, expiry))
        return {"access_token": token, "token_type": "bearer", "expires_at": expiry, "user": user}

    def current_user(self, token: str) -> User:
        user = self.repository.user_for_session(token_hash(token))
        if user is None:
            raise ServiceError("unauthorized", "Your session has ended. Please log in again.")
        return user

    def logout(self, token: str) -> None:
        self.repository.delete_session(token_hash(token))

    def edit_account(self, user: User, changes: dict, current_token: str) -> User:
        if not verify_password(changes["current_password"], user.passwordHash):
            raise ServiceError("invalid", "The current password is incorrect.")
        if "username" in changes:
            user.changeUsername(changes["username"])
        if "email" in changes:
            user.changeEmail(changes["email"])
        if "new_password" in changes:
            user.changePasswordHash(hash_password(changes["new_password"]))
        if "security_question" in changes:
            user.setRecoveryQuestion(changes["security_question"], hash_password(normalize_answer(changes["security_answer"])))
        self.repository.save(user)
        if "new_password" in changes:
            self.repository.delete_user_sessions(user.id, keep_hash=token_hash(current_token))
        return user

    def delete_account(self, user: User, password: str) -> None:
        if not verify_password(password, user.passwordHash):
            raise ServiceError("invalid", "The password is incorrect. Your account was not deleted.")
        self.repository.delete(user)

    def recovery_question(self, username: str) -> str:
        user = self.repository.user_by_username(username)
        if user is None or not user.securityQuestion or not user.securityAnswerHash:
            raise ServiceError("not_found", "Recovery is not available for that username. For an older account, sign in and set a recovery question in Account settings first.")
        return user.securityQuestion

    def reset_password(self, details: dict) -> None:
        user = self.repository.user_by_username(details["username"])
        stored = user.securityAnswerHash if user and user.securityAnswerHash else DUMMY_HASH
        valid = verify_password(normalize_answer(details["security_answer"]), stored)
        if user is None or not user.securityAnswerHash or not valid:
            raise ServiceError("invalid", "The username or recovery answer is incorrect.")
        user.changePasswordHash(hash_password(details["new_password"]))
        self.repository.delete_user_sessions(user.id)
        self.repository.save(user)


class TaskService:
    def __init__(self, repository: TaskBuddyRepository):
        self.repository = repository

    def list_tasks(self, user: User, view="active", search="", sort="newest", completion="all") -> list[Task]:
        self.repository.purge_expired_tasks(user.id, utc_now())
        tasks = self.repository.tasks_for_user(user.id, view)
        task_filter = TaskFilter(
            filterCriteria=search, sortField="title" if sort.startswith("title") else "createdAt",
            sortOrder="ascending" if sort in {"oldest", "title_asc"} else "descending",
        )
        return task_filter.sortTasks(task_filter.filterTasks(tasks, completion))

    def ensure_owner(self, user: User, item) -> None:
        if item.userId != user.id:
            raise ServiceError("not_found", "That item could not be found.")

    def get_task(self, user: User, item_id: int) -> Task:
        self.repository.purge_expired_tasks(user.id, utc_now())
        item = self.repository.task_for_user(user.id, item_id)
        if item is None:
            raise ServiceError("not_found", "That task could not be found.")
        self.ensure_owner(user, item)
        return item

    def _active_task(self, user: User, item_id: int) -> Task:
        task = self.get_task(user, item_id)
        if task.isDeleted:
            raise ServiceError("conflict", "Restore this task before changing it.")
        return task

    def get_subtask(self, user: User, item_id: int) -> Subtask:
        self.repository.purge_expired_tasks(user.id, utc_now())
        child = self.repository.subtask_for_user(user.id, item_id)
        if child is None:
            raise ServiceError("not_found", "That subtask could not be found.")
        self.ensure_owner(user, child)
        self._active_task(user, child.parentTask.id)
        return child

    def create_task(self, user: User, data: dict) -> Task:
        task = Task(data["title"], user.id, data.get("description", ""))
        self.repository.add(task)
        return task

    def update_task(self, user: User, item_id: int, data: dict) -> Task:
        task = self._active_task(user, item_id)
        if data.get("is_completed") and any(not child.isCompleted for child in task.subtasks):
            raise ServiceError("conflict", "Complete this task's subtasks first.")
        if "title" in data:
            task.changeTitle(data["title"])
        if "description" in data:
            task.changeDescription(data["description"])
        for field, method in [("is_pinned", task.setPinned), ("is_hidden", task.setHidden), ("is_completed", task.setCompleted)]:
            if field in data:
                method(data[field])
        self.repository.save(task)
        return task

    def delete_task(self, user: User, item_id: int) -> None:
        task = self._active_task(user, item_id)
        task.markDeleted(utc_now())
        self.repository.save(task)

    def restore_task(self, user: User, item_id: int) -> Task:
        task = self.get_task(user, item_id)
        if not task.isDeleted:
            raise ServiceError("conflict", "This task is already in your task list.")
        task.restore(utc_now())
        self.repository.save(task)
        return task

    def empty_deleted(self, user: User) -> int:
        return self.repository.empty_deleted(user.id)

    @staticmethod
    def _order_children(parent: Task, child: Subtask, position: int) -> None:
        children = sorted((s for s in parent.subtasks if s is not child), key=lambda s: (s.orderPosition, s.id or 0))
        children.insert(min(position, len(children)), child)
        for index, item in enumerate(children):
            if item.orderPosition != index:
                item.changeOrder(index)
        parent.updatedAt = utc_now()

    def add_subtask(self, user: User, task_id: int, data: dict) -> Subtask:
        parent = self._active_task(user, task_id)
        position = data.get("order_position")
        if position is None:
            position = len(parent.subtasks)
        child = Subtask(data["title"], parent, data.get("description", ""), position)
        parent.attachSubtask(child)
        self._order_children(parent, child, position)
        self.repository.add(child)
        return child

    def edit_subtask(self, user: User, item_id: int, data: dict) -> Subtask:
        child = self.get_subtask(user, item_id)
        if "title" in data:
            child.changeTitle(data["title"])
        if "description" in data:
            child.changeDescription(data["description"])
        if "order_position" in data:
            self._order_children(child.parentTask, child, data["order_position"])
        if "is_completed" in data:
            child.setCompleted(data["is_completed"])
            if not child.isCompleted:
                child.parentTask.setCompleted(False)
        child.parentTask.updatedAt = utc_now()
        self.repository.save(child)
        return child

    def delete_subtask(self, user: User, item_id: int) -> None:
        child = self.get_subtask(user, item_id)
        parent = child.parentTask
        parent.detachSubtask(child)
        for index, item in enumerate(sorted(parent.subtasks, key=lambda s: (s.orderPosition, s.id))):
            item.changeOrder(index)
        self.repository.save(parent)

    def export_tasks(self, user: User) -> str:
        self.repository.purge_expired_tasks(user.id, utc_now())
        tasks = self.repository.tasks_for_user(user.id, "all")
        return json.dumps(
            {"exported_at": utc_now(), "tasks": [task_data(t) for t in sorted(tasks, key=lambda t: t.id)]},
            default=lambda value: value.isoformat(), ensure_ascii=False, indent=2,
        )


class ReminderService:
    def __init__(self, repository: TaskBuddyRepository, sender: EmailSender):
        self.repository = repository
        self.sender = sender

    def ensure_owner(self, user: User, item) -> None:
        if item.userId != user.id:
            raise ServiceError("not_found", "That reminder could not be found.")

    def set_reminder(self, user: User, item, data: dict) -> Reminder:
        self.ensure_owner(user, item)
        if item.reminder is not None:
            raise ServiceError("conflict", "This item already has a reminder. Edit it instead.")
        reminder = Reminder(item, data["reminder_date"], data["email"])
        item.setReminder(reminder)
        self.repository.add(reminder)
        return reminder

    def _get_reminder(self, user: User, item_id: int) -> Reminder:
        reminder = self.repository.reminder_for_user(user.id, item_id)
        if reminder is None:
            raise ServiceError("not_found", "That reminder could not be found.")
        self.ensure_owner(user, reminder.task)
        parent = reminder.task if reminder.task.kind == "task" else reminder.task.parentTask
        if parent.isDeleted:
            raise ServiceError("conflict", "Restore the parent task before changing its reminder.")
        return reminder

    def edit_reminder(self, user: User, item_id: int, data: dict) -> Reminder:
        reminder = self._get_reminder(user, item_id)
        reminder.reschedule(data["reminder_date"])
        reminder.changeRecipient(data["email"])
        self.repository.save(reminder)
        return reminder

    def delete_reminder(self, user: User, item_id: int) -> None:
        reminder = self._get_reminder(user, item_id)
        reminder.task.removeReminder()
        self.repository.delete(reminder)

    def send_due_reminders(self, now) -> int:
        sent = 0
        for reminder in self.repository.due_reminders(now):
            item = reminder.task
            try:
                self.sender.send(
                    reminder.email, f"TaskBuddy reminder: {item.title}",
                    f"Reminder for your {item.kind}: {item.title}\n\n"
                    f"{item.description or ''}\n\nScheduled for {reminder.reminderDate.isoformat()} (UTC).",
                )
            except (OSError, smtplib.SMTPException):
                LOGGER.warning("A reminder could not be emailed; it will be retried.")
                continue
            reminder.markSent(now)
            self.repository.save(reminder)
            sent += 1
        return sent
