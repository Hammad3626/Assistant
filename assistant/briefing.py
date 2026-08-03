"""Read-only local daily briefing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from assistant.memory import MemoryError, MemoryStore
from assistant.notes import NotesError, NotesStore
from assistant.tasks import TasksError, TasksStore


class BriefingError(RuntimeError):
    """Raised when the local briefing cannot read assistant data."""


@dataclass(frozen=True)
class Briefing:
    now_text: str
    memory_count: int
    open_tasks: list[str]
    overdue_tasks: list[str]
    due_soon_tasks: list[str]
    recent_notes: list[str]

    def summary(self) -> str:
        lines = [
            "Local briefing",
            f"Now: {self.now_text}",
            f"Saved memories: {self.memory_count}",
        ]

        if self.open_tasks:
            lines.append("Open tasks:")
            for index, task in enumerate(self.open_tasks, start=1):
                lines.append(f"{index}. {task}")
        else:
            lines.append("Open tasks: none")

        if self.overdue_tasks:
            lines.append("Overdue tasks:")
            for index, task in enumerate(self.overdue_tasks, start=1):
                lines.append(f"{index}. {task}")
        else:
            lines.append("Overdue tasks: none")

        if self.due_soon_tasks:
            lines.append("Due soon tasks:")
            for index, task in enumerate(self.due_soon_tasks, start=1):
                lines.append(f"{index}. {task}")
        else:
            lines.append("Due soon tasks: none")

        if self.recent_notes:
            lines.append("Recent notes:")
            for index, note in enumerate(self.recent_notes, start=1):
                lines.append(f"{index}. {note}")
        else:
            lines.append("Recent notes: none")

        return "\n".join(lines)


def build_briefing(
    memory_store: MemoryStore,
    notes_store: NotesStore,
    tasks_store: TasksStore,
    now: datetime | None = None,
    notes_limit: int = 3,
) -> Briefing:
    current = now or datetime.now()
    now_text = current.strftime("%A, %B %d, %Y at %I:%M %p").replace(" 0", " ")

    try:
        memory_count = len(memory_store.list_memories())
        open_tasks = [task.display_text() for task in tasks_store.open_tasks()]
        current_date = current.date()
        overdue_tasks = [
            task.display_text() for task in tasks_store.overdue(today=current_date)
        ]
        due_soon_tasks = [
            task.display_text() for task in tasks_store.due_soon(today=current_date)
        ]
        recent_notes = [note.text for note in notes_store.list_notes()[-notes_limit:]]
    except (MemoryError, NotesError, TasksError) as exc:
        raise BriefingError(str(exc)) from exc

    return Briefing(
        now_text=now_text,
        memory_count=memory_count,
        open_tasks=open_tasks,
        overdue_tasks=overdue_tasks,
        due_soon_tasks=due_soon_tasks,
        recent_notes=recent_notes,
    )
