"""Startup dashboard text for the local Tkinter GUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from assistant.settings import AssistantSettings


@dataclass(frozen=True)
class StartupHealthRow:
    label: str
    value: str
    ok: bool


def build_startup_dashboard(
    settings: AssistantSettings,
    assistant: object,
    model_label: str,
    num_gpu: int,
) -> str:
    """Return a fast, read-only GUI startup summary."""
    voice_model_path = Path(settings.voice_model_path)
    lines = [
        "Startup dashboard",
        f"Assistant: {settings.assistant_name}",
        f"Model: {model_label}",
        f"GPU offload layers: {num_gpu}",
        f"Voice model: {settings.voice_model_path} ({'found' if voice_model_path.exists() else 'missing'})",
        "Local data:",
        f"- Memories: {_safe_count(lambda: assistant.memory_store.list_memories())}",
        f"- Notes: {_safe_count(lambda: assistant.notes_store.list_notes())}",
        f"- Open tasks: {_safe_count(lambda: assistant.tasks_store.open_tasks())}",
        f"- Task trash: {_safe_count(lambda: assistant.tasks_store.list_deleted_tasks())}",
        f"- Outbox drafts: {_safe_count(lambda: assistant.outbox_store.list_drafts())}",
        f"- Recent history entries: {_safe_count(lambda: assistant.history_store.recent(limit=1000))}",
        f"- Recent action audit entries: {_safe_count(lambda: assistant.action_audit_store.recent(limit=1000))}",
        f"- Recent voice audit entries: {_safe_count(lambda: assistant.voice_action_audit_store.recent(limit=1000))}",
        "Useful commands: briefing, status, safety, roadmap, command reference.",
    ]
    return "\n".join(lines)


def build_startup_health_rows(
    settings: AssistantSettings,
    assistant: object,
    model_label: str,
    num_gpu: int,
) -> list[StartupHealthRow]:
    """Return compact health rows for the GUI startup dashboard panel."""
    voice_model_path = Path(settings.voice_model_path)
    memory_count = _safe_count(lambda: assistant.memory_store.list_memories())
    notes_count = _safe_count(lambda: assistant.notes_store.list_notes())
    open_tasks_count = _safe_count(lambda: assistant.tasks_store.open_tasks())
    deleted_tasks_count = _safe_count(lambda: assistant.tasks_store.list_deleted_tasks())
    outbox_count = _safe_count(lambda: assistant.outbox_store.list_drafts())
    history_count = _safe_count(lambda: assistant.history_store.recent(limit=1000))
    audit_count = _safe_count(lambda: assistant.action_audit_store.recent(limit=1000))
    voice_audit_count = _safe_count(lambda: assistant.voice_action_audit_store.recent(limit=1000))

    return [
        StartupHealthRow("Assistant", settings.assistant_name, bool(settings.assistant_name)),
        StartupHealthRow("Model", model_label, bool(model_label)),
        StartupHealthRow("GPU layers", str(num_gpu), num_gpu >= 0),
        StartupHealthRow(
            "Voice model",
            "found" if voice_model_path.exists() else "missing",
            voice_model_path.exists(),
        ),
        StartupHealthRow("Memories", memory_count, not memory_count.startswith("error:")),
        StartupHealthRow("Notes", notes_count, not notes_count.startswith("error:")),
        StartupHealthRow("Open tasks", open_tasks_count, not open_tasks_count.startswith("error:")),
        StartupHealthRow("Task trash", deleted_tasks_count, not deleted_tasks_count.startswith("error:")),
        StartupHealthRow("Outbox", outbox_count, not outbox_count.startswith("error:")),
        StartupHealthRow("History", history_count, not history_count.startswith("error:")),
        StartupHealthRow("Action audit", audit_count, not audit_count.startswith("error:")),
        StartupHealthRow("Voice audit", voice_audit_count, not voice_audit_count.startswith("error:")),
    ]


def _safe_count(loader: Callable[[], list[object]]) -> str:
    try:
        return str(len(loader()))
    except Exception as exc:
        return f"error: {exc}"
