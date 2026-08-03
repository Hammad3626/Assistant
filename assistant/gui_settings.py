"""Small helpers for the GUI settings editor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from assistant.settings import AssistantSettings, update_setting


@dataclass(frozen=True)
class GuiSettingField:
    key: str
    label: str
    kind: str


GUI_SETTING_FIELDS = (
    GuiSettingField("assistant_name", "Assistant name", "text"),
    GuiSettingField("history_enabled", "Save local history", "bool"),
    GuiSettingField("action_audit_enabled", "Save action audit", "bool"),
    GuiSettingField("voice_action_audit_enabled", "Save voice action audit", "bool"),
)

GUI_MODEL_FIELDS = (
    GuiSettingField("model", "Local model", "text"),
    GuiSettingField("use_llm", "Use local LLM", "bool"),
    GuiSettingField("num_gpu", "GPU offload layers", "int"),
)

GUI_VOICE_FIELDS = (
    GuiSettingField("voice_enabled", "Voice input", "bool"),
    GuiSettingField("voice_model_path", "Voice model path", "text"),
    GuiSettingField("voice_timeout", "Voice timeout seconds", "int"),
    GuiSettingField("speak_enabled", "Voice output", "bool"),
    GuiSettingField("speech_rate", "Speech rate", "int"),
    GuiSettingField("speech_volume", "Speech volume", "int"),
    GuiSettingField("voice_action_audit_path", "Voice action audit path", "text"),
)

GUI_MEMORY_FIELDS = (
    GuiSettingField("memory_path", "Memory path", "text"),
)

GUI_TASK_FIELDS = (
    GuiSettingField("tasks_path", "Tasks path", "text"),
)

GUI_PANEL_NAMES = ("General", "Apps", "Folders", "Models", "Voice", "Memory", "Tasks")


def apply_gui_settings(
    settings: AssistantSettings,
    values: Mapping[str, str | int | bool],
) -> AssistantSettings:
    """Validate and apply editable GUI setting values."""
    updated = settings
    editable_keys = {
        field.key
        for fields in (
            GUI_SETTING_FIELDS,
            GUI_MODEL_FIELDS,
            GUI_VOICE_FIELDS,
            GUI_MEMORY_FIELDS,
            GUI_TASK_FIELDS,
        )
        for field in fields
    }
    for key, value in values.items():
        if key not in editable_keys:
            continue
        updated = update_setting(updated, key, str(value))
    return updated


def settings_saved_text(settings_path: str) -> str:
    return (
        f"Settings saved to {settings_path}. "
        "Restart the assistant to apply model, voice, or storage changes."
    )
