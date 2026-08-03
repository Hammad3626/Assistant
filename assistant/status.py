"""Read-only local status collection for the assistant."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from assistant.actions import load_allowed_apps, load_allowed_folders
from assistant.audit import ActionAuditStore
from assistant.data_tools import build_report, build_report_from_stores
from assistant.history import HistoryStore
from assistant.memory import MemoryStore
from assistant.notes import NotesStore
from assistant.outbox import OutboxStore
from assistant.settings import AssistantSettings
from assistant.tasks import TasksStore


@dataclass(frozen=True)
class LocalStatus:
    assistant_name: str
    model: str
    use_llm: bool
    ollama_reachable: bool
    ollama_models: list[str]
    app_count: int
    folder_count: int
    memory_count: int
    notes_count: int
    open_tasks_count: int
    deleted_tasks_count: int
    outbox_count: int
    history_count: int
    action_audit_count: int

    def summary(self) -> str:
        ollama_text = "reachable" if self.ollama_reachable else "not reachable"
        model_text = ", ".join(self.ollama_models) if self.ollama_models else "none"
        return (
            "Local assistant status\n"
            f"Assistant: {self.assistant_name}\n"
            f"Configured model: {self.model}\n"
            f"LLM enabled: {self.use_llm}\n"
            f"Ollama: {ollama_text}\n"
            f"Installed Ollama models: {model_text}\n"
            f"Allowed apps: {self.app_count}\n"
            f"Allowed folders: {self.folder_count}\n"
            f"Memories: {self.memory_count}\n"
            f"Notes: {self.notes_count}\n"
            f"Open tasks: {self.open_tasks_count}\n"
            f"Task trash entries: {self.deleted_tasks_count}\n"
            f"Outbox drafts: {self.outbox_count}\n"
            f"History entries: {self.history_count}\n"
            f"Action audit entries: {self.action_audit_count}"
        )


def collect_status(
    settings: AssistantSettings,
    ollama_host: str = "http://127.0.0.1:11434",
) -> LocalStatus:
    report = build_report(settings)
    ollama_reachable, ollama_models = _ollama_status(ollama_host)
    return LocalStatus(
        assistant_name=settings.assistant_name,
        model=settings.model,
        use_llm=settings.use_llm,
        ollama_reachable=ollama_reachable,
        ollama_models=ollama_models,
        app_count=len(load_allowed_apps()),
        folder_count=len(load_allowed_folders()),
        memory_count=report.memory_count,
        notes_count=report.notes_count,
        open_tasks_count=report.open_tasks_count,
        deleted_tasks_count=report.deleted_tasks_count,
        outbox_count=report.outbox_count,
        history_count=report.history_count,
        action_audit_count=report.action_audit_count,
    )


def collect_status_from_stores(
    assistant_name: str,
    model: str,
    use_llm: bool,
    memory_store: MemoryStore,
    notes_store: NotesStore,
    tasks_store: TasksStore,
    outbox_store: OutboxStore,
    history_store: HistoryStore,
    action_audit_store: ActionAuditStore,
    ollama_host: str = "http://127.0.0.1:11434",
) -> LocalStatus:
    report = build_report_from_stores(
        memory_store,
        notes_store,
        tasks_store,
        outbox_store,
        history_store,
        action_audit_store,
    )
    ollama_reachable, ollama_models = _ollama_status(ollama_host)
    return LocalStatus(
        assistant_name=assistant_name,
        model=model,
        use_llm=use_llm,
        ollama_reachable=ollama_reachable,
        ollama_models=ollama_models,
        app_count=len(load_allowed_apps()),
        folder_count=len(load_allowed_folders()),
        memory_count=report.memory_count,
        notes_count=report.notes_count,
        open_tasks_count=report.open_tasks_count,
        deleted_tasks_count=report.deleted_tasks_count,
        outbox_count=report.outbox_count,
        history_count=report.history_count,
        action_audit_count=report.action_audit_count,
    )


def _ollama_status(host: str) -> tuple[bool, list[str]]:
    request = urllib.request.Request(f"{host}/api/tags", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return False, []

    models = [item["name"] for item in data.get("models", []) if "name" in item]
    return True, models
