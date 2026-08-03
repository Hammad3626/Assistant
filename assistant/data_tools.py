"""Local assistant data reporting, export, and clearing helpers."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from assistant.audit import ActionAuditStore
from assistant.history import HistoryStore
from assistant.memory import MemoryStore
from assistant.notes import NotesStore
from assistant.outbox import OutboxStore
from assistant.settings import AssistantSettings
from assistant.tasks import TasksStore


@dataclass(frozen=True)
class BackupEntry:
    name: str
    path: str


@dataclass(frozen=True)
class DataReport:
    memory_path: str
    memory_count: int
    notes_path: str
    notes_count: int
    tasks_path: str
    open_tasks_count: int
    deleted_tasks_count: int
    outbox_path: str
    outbox_count: int
    history_path: str
    history_count: int
    action_audit_path: str
    action_audit_count: int

    def summary(self) -> str:
        return (
            "Local assistant data report\n"
            f"Memory: {self.memory_count} item(s) at {self.memory_path}\n"
            f"Notes: {self.notes_count} item(s) at {self.notes_path}\n"
            f"Open tasks: {self.open_tasks_count} item(s) at {self.tasks_path}\n"
            f"Task trash: {self.deleted_tasks_count} item(s) at {self.tasks_path}\n"
            f"Outbox drafts: {self.outbox_count} item(s) at {self.outbox_path}\n"
            f"History: {self.history_count} entr(y/ies) at {self.history_path}\n"
            f"Action audit: {self.action_audit_count} entr(y/ies) at {self.action_audit_path}"
        )


def list_backups(output_dir: str | Path = "exports", limit: int = 10) -> list[BackupEntry]:
    export_root = Path(output_dir)
    if not export_root.exists():
        return []

    backups = [
        path
        for path in export_root.iterdir()
        if path.is_dir() and path.name.startswith("assistant-data-")
    ]
    backups.sort(key=lambda path: path.name, reverse=True)
    return [BackupEntry(name=path.name, path=str(path)) for path in backups[:limit]]


def backups_summary(output_dir: str | Path = "exports", limit: int = 10) -> str:
    backups = list_backups(output_dir, limit=limit)
    if not backups:
        return f"No local backups found at: {Path(output_dir)}"

    lines = ["Local backups:"]
    for index, backup in enumerate(backups, start=1):
        lines.append(f"{index}. {backup.name} at {backup.path}")
    return "\n".join(lines)


def build_report(settings: AssistantSettings) -> DataReport:
    memory_store = MemoryStore(settings.memory_path)
    notes_store = NotesStore(settings.notes_path)
    tasks_store = TasksStore(settings.tasks_path)
    outbox_store = OutboxStore(settings.outbox_path)
    history_store = HistoryStore(settings.history_path)
    action_audit_store = ActionAuditStore(settings.action_audit_path)
    return build_report_from_stores(
        memory_store,
        notes_store,
        tasks_store,
        outbox_store,
        history_store,
        action_audit_store,
    )


def build_report_from_stores(
    memory_store: MemoryStore,
    notes_store: NotesStore,
    tasks_store: TasksStore,
    outbox_store: OutboxStore,
    history_store: HistoryStore,
    action_audit_store: ActionAuditStore,
) -> DataReport:
    return DataReport(
        memory_path=str(memory_store.path),
        memory_count=len(memory_store.list_memories()),
        notes_path=str(notes_store.path),
        notes_count=len(notes_store.list_notes()),
        tasks_path=str(tasks_store.path),
        open_tasks_count=len(tasks_store.open_tasks()),
        deleted_tasks_count=len(tasks_store.list_deleted_tasks()),
        outbox_path=str(outbox_store.path),
        outbox_count=len(outbox_store.list_drafts()),
        history_path=str(history_store.path),
        history_count=len(history_store.recent(limit=1_000_000)),
        action_audit_path=str(action_audit_store.path),
        action_audit_count=len(action_audit_store.recent(limit=1_000_000)),
    )


def export_data(settings: AssistantSettings, output_dir: str | Path = "exports") -> Path:
    memory_store = MemoryStore(settings.memory_path)
    notes_store = NotesStore(settings.notes_path)
    tasks_store = TasksStore(settings.tasks_path)
    outbox_store = OutboxStore(settings.outbox_path)
    history_store = HistoryStore(settings.history_path)
    action_audit_store = ActionAuditStore(settings.action_audit_path)
    return export_data_from_stores(
        memory_store,
        notes_store,
        tasks_store,
        outbox_store,
        history_store,
        action_audit_store,
        output_dir=output_dir,
    )


def export_data_from_stores(
    memory_store: MemoryStore,
    notes_store: NotesStore,
    tasks_store: TasksStore,
    outbox_store: OutboxStore,
    history_store: HistoryStore,
    action_audit_store: ActionAuditStore,
    output_dir: str | Path = "exports",
) -> Path:
    export_root = Path(output_dir)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    export_dir = export_root / f"assistant-data-{timestamp}"
    export_dir.mkdir(parents=True, exist_ok=False)

    report = build_report_from_stores(
        memory_store,
        notes_store,
        tasks_store,
        outbox_store,
        history_store,
        action_audit_store,
    )
    (export_dir / "report.json").write_text(
        json.dumps(asdict(report), indent=2) + "\n",
        encoding="utf-8",
    )

    for source, name in (
        (memory_store.path, "memory.json"),
        (notes_store.path, "notes.md"),
        (tasks_store.path, "tasks.json"),
        (outbox_store.path, "outbox.json"),
        (history_store.path, "history.jsonl"),
        (action_audit_store.path, "action_audit.jsonl"),
    ):
        if source.exists():
            shutil.copy2(source, export_dir / name)

    return export_dir


def clear_data(
    settings: AssistantSettings,
    clear_memory: bool,
    clear_history: bool,
    clear_action_audit: bool = False,
) -> DataReport:
    if clear_memory:
        MemoryStore(settings.memory_path).clear()
    if clear_history:
        HistoryStore(settings.history_path).clear()
    if clear_action_audit:
        ActionAuditStore(settings.action_audit_path).clear()
    return build_report(settings)
