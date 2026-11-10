"""Public data conversion shared by controllers and the JSON export format."""


def user_data(user):
    return {"user_id": user.id, "username": user.username,
            "email": user.email, "created_at": user.createdAt}


def reminder_data(reminder):
    if reminder is None:
        return None
    item = reminder.task
    return {
        "reminder_id": reminder.id, "target_id": item.id, "target_type": item.kind,
        "reminder_date": reminder.reminderDate, "email": reminder.email,
        "sent_at": reminder.sentAt,
    }


def subtask_data(item):
    return {
        "subtask_id": item.id, "task_id": item.parentTask.id, "user_id": item.userId,
        "title": item.title, "description": item.description or "",
        "order_position": item.orderPosition, "is_completed": item.isCompleted,
        "reminder": reminder_data(item.reminder),
    }


def task_data(item):
    return {
        "task_id": item.id, "user_id": item.userId, "title": item.title,
        "description": item.description or "", "is_pinned": item.isPinned,
        "is_hidden": item.isHidden, "is_deleted": item.isDeleted,
        "is_completed": item.isCompleted, "deleted_at": item.deletedAt,
        "expires_at": item.expiresAt, "created_at": item.createdAt,
        "updated_at": item.updatedAt,
        "subtasks": [subtask_data(child) for child in sorted(item.subtasks, key=lambda s: (s.orderPosition, s.id))],
        "reminder": reminder_data(item.reminder),
    }
