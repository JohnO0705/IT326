"""Controllers translate API models to service inputs and public responses."""

from backend.public_data import reminder_data, subtask_data, task_data, user_data
from backend.schemas import ReminderResponse, SessionResponse, SubtaskResponse, TaskResponse, UserResponse


class AccountController:
    def __init__(self, service):
        self.service = service

    @staticmethod
    def _session(result):
        return SessionResponse(**{**result, "user": user_data(result["user"])})

    def register(self, data):
        return self._session(self.service.register(data.model_dump()))

    def login(self, data):
        return self._session(self.service.login(data.username, data.password))

    def logout(self, token):
        self.service.logout(token)

    def me(self, token):
        return UserResponse(**user_data(self.service.current_user(token)))

    def edit_account(self, user, data, token):
        result = self.service.edit_account(user, data.model_dump(exclude_unset=True), token)
        return UserResponse(**user_data(result))

    def delete_account(self, user, data):
        self.service.delete_account(user, data.password)

    def recovery_question(self, username):
        return {"security_question": self.service.recovery_question(username)}

    def reset_password(self, data):
        self.service.reset_password(data.model_dump())


class TaskController:
    def __init__(self, tasks, reminders):
        self.tasks = tasks
        self.reminders = reminders

    def list_tasks(self, user, view, search, sort, completion):
        return [TaskResponse(**task_data(t)) for t in self.tasks.list_tasks(user, view, search, sort, completion)]

    def get_task(self, user, item_id):
        return TaskResponse(**task_data(self.tasks.get_task(user, item_id)))

    def create_task(self, user, data):
        return TaskResponse(**task_data(self.tasks.create_task(user, data.model_dump())))

    def update_task(self, user, item_id, data):
        return TaskResponse(**task_data(self.tasks.update_task(user, item_id, data.model_dump(exclude_unset=True))))

    def delete_task(self, user, item_id):
        self.tasks.delete_task(user, item_id)

    def restore_task(self, user, item_id):
        return TaskResponse(**task_data(self.tasks.restore_task(user, item_id)))

    def empty_deleted(self, user):
        return {"deleted_count": self.tasks.empty_deleted(user)}

    def list_subtasks(self, user, task_id):
        task = self.tasks._active_task(user, task_id)
        return [SubtaskResponse(**subtask_data(s)) for s in sorted(task.subtasks, key=lambda s: (s.orderPosition, s.id))]

    def get_subtask(self, user, item_id):
        return SubtaskResponse(**subtask_data(self.tasks.get_subtask(user, item_id)))

    def add_subtask(self, user, task_id, data):
        return SubtaskResponse(**subtask_data(self.tasks.add_subtask(user, task_id, data.model_dump())))

    def edit_subtask(self, user, item_id, data):
        return SubtaskResponse(**subtask_data(self.tasks.edit_subtask(user, item_id, data.model_dump(exclude_unset=True))))

    def delete_subtask(self, user, item_id):
        self.tasks.delete_subtask(user, item_id)

    def set_reminder(self, user, item_id, item_type, data):
        item = self.tasks._active_task(user, item_id) if item_type == "task" else self.tasks.get_subtask(user, item_id)
        return ReminderResponse(**reminder_data(self.reminders.set_reminder(user, item, data.model_dump())))

    def edit_reminder(self, user, item_id, data):
        return ReminderResponse(**reminder_data(self.reminders.edit_reminder(user, item_id, data.model_dump())))

    def delete_reminder(self, user, item_id):
        self.reminders.delete_reminder(user, item_id)

    def export_tasks(self, user):
        return self.tasks.export_tasks(user)
