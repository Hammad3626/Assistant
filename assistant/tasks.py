"""Local JSON task list for the assistant."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_TASKS_PATH = Path("data/tasks.json")


class TasksError(RuntimeError):
    """Raised when local tasks cannot be read or written."""


@dataclass(frozen=True)
class TaskItem:
    text: str
    created_at: str
    due_date: str | None = None
    completed_at: str | None = None

    @property
    def completed(self) -> bool:
        return self.completed_at is not None

    def display_text(self) -> str:
        if self.due_date:
            return f"{self.text} (due {self.due_date})"
        return self.text


@dataclass(frozen=True)
class DeletedTaskItem:
    text: str
    created_at: str
    deleted_at: str
    due_date: str | None = None
    completed_at: str | None = None

    def display_text(self) -> str:
        if self.due_date:
            return f"{self.text} (due {self.due_date})"
        return self.text


class TasksStore:
    """Simple local task list backed by one JSON file."""

    def __init__(self, path: str | Path = DEFAULT_TASKS_PATH) -> None:
        self.path = Path(path)

    def add(self, text: str, due_date: str | None = None) -> TaskItem:
        clean_text, parsed_due_date = parse_task_text(text)
        if due_date is not None:
            parsed_due_date = validate_due_date(due_date)
        if not clean_text:
            raise TasksError("Cannot add an empty task.")

        task = TaskItem(
            text=clean_text,
            created_at=_utc_now_iso(),
            due_date=parsed_due_date,
        )
        tasks = self.list_tasks()
        tasks.append(task)
        self._write_tasks(tasks)
        return task

    def complete(self, task_number: int) -> TaskItem:
        tasks = self.list_tasks()
        target_index = self._open_task_index(tasks, task_number)
        task = tasks[target_index]
        completed = TaskItem(
            text=task.text,
            created_at=task.created_at,
            due_date=task.due_date,
            completed_at=_utc_now_iso(),
        )
        tasks[target_index] = completed
        self._write_tasks(tasks)
        return completed

    def delete_open(self, task_number: int) -> TaskItem:
        raw = self._read_raw()
        tasks = self._tasks_from_raw(raw)
        target_index = self._open_task_index(tasks, task_number)
        removed = tasks.pop(target_index)
        deleted_tasks = self._deleted_tasks_from_raw(raw)
        deleted_tasks.append(
            DeletedTaskItem(
                text=removed.text,
                created_at=removed.created_at,
                due_date=removed.due_date,
                completed_at=removed.completed_at,
                deleted_at=_utc_now_iso(),
            )
        )
        self._write_all(tasks, deleted_tasks)
        return removed

    def list_deleted_tasks(self) -> list[DeletedTaskItem]:
        return self._deleted_tasks_from_raw(self._read_raw())

    def deleted_summary(self) -> str:
        deleted_tasks = self.list_deleted_tasks()
        if not deleted_tasks:
            return "Task trash is empty."

        lines = ["Task trash:"]
        for index, task in enumerate(deleted_tasks, start=1):
            lines.append(f"{index}. {task.display_text()} (deleted {task.deleted_at})")
        return "\n".join(lines)

    def restore_deleted(self, task_number: int) -> TaskItem:
        raw = self._read_raw()
        tasks = self._tasks_from_raw(raw)
        deleted_tasks = self._deleted_tasks_from_raw(raw)
        if task_number < 1 or task_number > len(deleted_tasks):
            raise TasksError(f"Deleted task number must be between 1 and {len(deleted_tasks)}.")

        deleted = deleted_tasks.pop(task_number - 1)
        restored = TaskItem(
            text=deleted.text,
            created_at=deleted.created_at,
            due_date=deleted.due_date,
            completed_at=None,
        )
        tasks.append(restored)
        self._write_all(tasks, deleted_tasks)
        return restored

    def restore_completed(self, task_number: int) -> TaskItem:
        tasks = self.list_tasks()
        target_index = self._completed_task_index(tasks, task_number)
        task = tasks[target_index]
        restored = TaskItem(
            text=task.text,
            created_at=task.created_at,
            due_date=task.due_date,
            completed_at=None,
        )
        tasks[target_index] = restored
        self._write_tasks(tasks)
        return restored

    def rename(self, task_number: int, new_text: str) -> TaskItem:
        clean_text = " ".join(new_text.strip().split())
        if not clean_text:
            raise TasksError("Task text cannot be empty.")

        tasks = self.list_tasks()
        target_index = self._open_task_index(tasks, task_number)
        task = tasks[target_index]
        updated = TaskItem(
            text=clean_text,
            created_at=task.created_at,
            due_date=task.due_date,
            completed_at=task.completed_at,
        )
        tasks[target_index] = updated
        self._write_tasks(tasks)
        return updated

    def set_due_date(self, task_number: int, due_date: str | None) -> TaskItem:
        parsed_due_date = validate_due_date(due_date) if due_date is not None else None
        tasks = self.list_tasks()
        target_index = self._open_task_index(tasks, task_number)
        task = tasks[target_index]
        updated = TaskItem(
            text=task.text,
            created_at=task.created_at,
            due_date=parsed_due_date,
            completed_at=task.completed_at,
        )
        tasks[target_index] = updated
        self._write_tasks(tasks)
        return updated

    def list_tasks(self) -> list[TaskItem]:
        return self._tasks_from_raw(self._read_raw())

    def _tasks_from_raw(self, raw: dict[str, Any]) -> list[TaskItem]:
        items = raw.get("tasks", [])
        if not isinstance(items, list):
            raise TasksError("Tasks file has invalid 'tasks' value.")

        tasks: list[TaskItem] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            created_at = item.get("created_at")
            due_date = item.get("due_date")
            completed_at = item.get("completed_at")
            if isinstance(text, str) and isinstance(created_at, str):
                tasks.append(
                    TaskItem(
                        text=text,
                        created_at=created_at,
                        due_date=due_date if isinstance(due_date, str) else None,
                        completed_at=completed_at if isinstance(completed_at, str) else None,
                    )
                )
        return tasks

    def _deleted_tasks_from_raw(self, raw: dict[str, Any]) -> list[DeletedTaskItem]:
        items = raw.get("deleted_tasks", [])
        if not isinstance(items, list):
            raise TasksError("Tasks file has invalid 'deleted_tasks' value.")

        deleted_tasks: list[DeletedTaskItem] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            created_at = item.get("created_at")
            deleted_at = item.get("deleted_at")
            due_date = item.get("due_date")
            completed_at = item.get("completed_at")
            if isinstance(text, str) and isinstance(created_at, str) and isinstance(deleted_at, str):
                deleted_tasks.append(
                    DeletedTaskItem(
                        text=text,
                        created_at=created_at,
                        deleted_at=deleted_at,
                        due_date=due_date if isinstance(due_date, str) else None,
                        completed_at=completed_at if isinstance(completed_at, str) else None,
                    )
                )
        return deleted_tasks

    def open_tasks(self) -> list[TaskItem]:
        return [task for task in self.list_tasks() if not task.completed]

    def completed_tasks(self) -> list[TaskItem]:
        return [task for task in self.list_tasks() if task.completed]

    def due_today(self, today: date | None = None) -> list[TaskItem]:
        current = today or date.today()
        return [
            task
            for task in self.open_tasks()
            if task.due_date is not None and date.fromisoformat(task.due_date) == current
        ]

    def overdue(self, today: date | None = None) -> list[TaskItem]:
        current = today or date.today()
        return [
            task
            for task in self.open_tasks()
            if task.due_date is not None and date.fromisoformat(task.due_date) < current
        ]

    def upcoming(self, today: date | None = None) -> list[TaskItem]:
        current = today or date.today()
        return [
            task
            for task in self.open_tasks()
            if task.due_date is not None and date.fromisoformat(task.due_date) >= current
        ]

    def due_soon(self, today: date | None = None, days: int = 7) -> list[TaskItem]:
        if days < 0:
            raise TasksError("Due soon day count cannot be negative.")
        current = today or date.today()
        end_date = current + timedelta(days=days)
        return [
            task
            for task in self.open_tasks()
            if task.due_date is not None
            and current <= date.fromisoformat(task.due_date) <= end_date
        ]

    def summary(self) -> str:
        open_tasks = self.open_tasks()
        if not open_tasks:
            return "No open tasks."

        lines = ["Open tasks:"]
        for index, task in enumerate(open_tasks, start=1):
            lines.append(f"{index}. {task.display_text()}")
        return "\n".join(lines)

    def completed_summary(self) -> str:
        completed_tasks = self.completed_tasks()
        if not completed_tasks:
            return "No completed tasks."

        lines = ["Completed tasks:"]
        for index, task in enumerate(completed_tasks, start=1):
            lines.append(f"{index}. {task.display_text()}")
        return "\n".join(lines)

    def all_summary(self) -> str:
        tasks = self.list_tasks()
        if not tasks:
            return "No saved tasks."

        lines = ["All tasks:"]
        for index, task in enumerate(tasks, start=1):
            status = "done" if task.completed else "open"
            lines.append(f"{index}. [{status}] {task.display_text()}")
        return "\n".join(lines)

    def due_summary(self, label: str, tasks: list[TaskItem]) -> str:
        if not tasks:
            return f"No {label.lower()} tasks."

        lines = [f"{label} tasks:"]
        for index, task in enumerate(tasks, start=1):
            lines.append(f"{index}. {task.display_text()}")
        return "\n".join(lines)

    def stats_summary(self) -> str:
        tasks = self.list_tasks()
        open_tasks = [task for task in tasks if not task.completed]
        completed_tasks = [task for task in tasks if task.completed]
        with_due_dates = [task for task in open_tasks if task.due_date is not None]
        without_due_dates = [task for task in open_tasks if task.due_date is None]
        return (
            "Task stats\n"
            f"Total tasks: {len(tasks)}\n"
            f"Open tasks: {len(open_tasks)}\n"
            f"Completed tasks: {len(completed_tasks)}\n"
            f"Open with due dates: {len(with_due_dates)}\n"
            f"Open without due dates: {len(without_due_dates)}"
        )

    @staticmethod
    def _open_task_index(tasks: list[TaskItem], task_number: int) -> int:
        open_indexes = [index for index, task in enumerate(tasks) if not task.completed]
        if task_number < 1 or task_number > len(open_indexes):
            raise TasksError(f"Open task number must be between 1 and {len(open_indexes)}.")
        return open_indexes[task_number - 1]

    @staticmethod
    def _completed_task_index(tasks: list[TaskItem], task_number: int) -> int:
        completed_indexes = [index for index, task in enumerate(tasks) if task.completed]
        if task_number < 1 or task_number > len(completed_indexes):
            raise TasksError(
                f"Completed task number must be between 1 and {len(completed_indexes)}."
            )
        return completed_indexes[task_number - 1]

    def _read_raw(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"tasks": []}

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise TasksError(f"Invalid tasks JSON: {self.path}") from exc
        except OSError as exc:
            raise TasksError(f"Could not read tasks file: {self.path}") from exc

        if not isinstance(raw, dict):
            raise TasksError("Tasks file must contain a JSON object.")
        return raw

    def _write_tasks(self, tasks: list[TaskItem]) -> None:
        deleted_tasks = self.list_deleted_tasks()
        self._write_all(tasks, deleted_tasks)

    def _write_all(self, tasks: list[TaskItem], deleted_tasks: list[DeletedTaskItem]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "tasks": [_task_to_raw(task) for task in tasks],
            "deleted_tasks": [_deleted_task_to_raw(task) for task in deleted_tasks],
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _task_to_raw(task: TaskItem) -> dict[str, str | None]:
    return {
        "text": task.text,
        "created_at": task.created_at,
        "due_date": task.due_date,
        "completed_at": task.completed_at,
    }


def _deleted_task_to_raw(task: DeletedTaskItem) -> dict[str, str | None]:
    return {
        "text": task.text,
        "created_at": task.created_at,
        "due_date": task.due_date,
        "completed_at": task.completed_at,
        "deleted_at": task.deleted_at,
    }


def parse_task_text(text: str) -> tuple[str, str | None]:
    clean_text = " ".join(text.strip().split())
    marker = " due "
    if marker not in clean_text:
        return clean_text, None

    task_text, due_date_text = clean_text.rsplit(marker, 1)
    if not task_text.strip():
        raise TasksError("Task text cannot be empty before due date.")
    return task_text.strip(), validate_due_date(due_date_text)


def validate_due_date(value: str) -> str:
    clean_value = value.strip()
    try:
        date.fromisoformat(clean_value)
    except ValueError as exc:
        raise TasksError("Due date must use YYYY-MM-DD format.") from exc
    return clean_value
