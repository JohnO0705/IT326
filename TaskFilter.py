"""Filtering and sorting logic shared by the task-list API."""

from dataclasses import dataclass

from Task import Task


@dataclass
class TaskFilter:
    filterCriteria: str = ""
    sortField: str = "createdAt"
    sortOrder: str = "descending"

    def filterTasks(self, tasks: list[Task], completion: str = "all") -> list[Task]:
        query = self.filterCriteria.strip().casefold()
        return [
            task for task in tasks
            if (not query or query in task.title.casefold() or query in task.description.casefold())
            and (completion != "open" or not task.isCompleted)
            and (completion != "completed" or task.isCompleted)
        ]

    def sortTasks(self, tasks: list[Task]) -> list[Task]:
        key = (lambda task: task.title.casefold()) if self.sortField == "title" else (lambda task: (task.createdAt, task.taskId))
        ordered = sorted(tasks, key=key, reverse=self.sortOrder == "descending")
        # Stable sorting preserves the selected order within each pin group.
        return sorted(ordered, key=lambda task: not task.isPinned)
