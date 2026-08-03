"""Check that tkinter GUI dependencies are available."""

from __future__ import annotations

import tkinter

from assistant.gui import (
    GUI_FILE_TOOL_BUTTONS,
    GUI_MEMORY_CONTROL_BUTTONS,
    GUI_SAFETY_CONTROL_BUTTONS,
    GUI_TASK_CONTROL_BUTTONS,
    GUI_VOICE_CONTROL_BUTTONS,
)
from assistant.gui_settings import GUI_PANEL_NAMES


def main() -> int:
    print("GUI health check")
    print(f"tkinter: available, Tk version {tkinter.TkVersion}")
    required_panels = {"Apps", "Folders", "Models", "Voice", "Memory", "Tasks"}
    missing = required_panels.difference(GUI_PANEL_NAMES)
    if missing:
        print(f"ERROR: Missing GUI settings panels: {', '.join(sorted(missing))}")
        return 1
    required_file_buttons = {
        "List",
        "Search",
        "Find Names",
        "Preview",
        "Verify Write",
        "Verify Restore",
        "Panel",
    }
    missing_file_buttons = required_file_buttons.difference(GUI_FILE_TOOL_BUTTONS)
    if missing_file_buttons:
        print(f"ERROR: Missing GUI file tool buttons: {', '.join(sorted(missing_file_buttons))}")
        return 1
    required_voice_buttons = {
        "Voice Status",
        "Voice Audit",
        "Low Confidence Audit",
        "Action Preview Audit",
        "Export Voice Audit",
        "Retention Preview",
        "Prune Audit",
        "Voice Help",
        "Wake Help",
        "Action Review",
        "Launch Commands",
        "Copy Wake Cmd",
    }
    missing_voice_buttons = required_voice_buttons.difference(GUI_VOICE_CONTROL_BUTTONS)
    if missing_voice_buttons:
        print(f"ERROR: Missing GUI voice control buttons: {', '.join(sorted(missing_voice_buttons))}")
        return 1
    required_memory_buttons = {
        "Add Memory",
        "Rename Memory",
        "Delete Memory",
        "Memory Trash",
        "Restore Memory",
        "Refresh",
    }
    missing_memory_buttons = required_memory_buttons.difference(GUI_MEMORY_CONTROL_BUTTONS)
    if missing_memory_buttons:
        print(f"ERROR: Missing GUI memory control buttons: {', '.join(sorted(missing_memory_buttons))}")
        return 1
    required_task_buttons = {
        "Add Task",
        "Done",
        "Rename Task",
        "Set Due",
        "Clear Due",
        "Delete Task",
        "Task Trash",
        "Restore Deleted",
        "Refresh",
    }
    missing_task_buttons = required_task_buttons.difference(GUI_TASK_CONTROL_BUTTONS)
    if missing_task_buttons:
        print(f"ERROR: Missing GUI task control buttons: {', '.join(sorted(missing_task_buttons))}")
        return 1
    required_safety_buttons = {"Refresh", "Safety Snapshot", "Launch Snapshot", "Shell Snapshot"}
    missing_safety_buttons = required_safety_buttons.difference(GUI_SAFETY_CONTROL_BUTTONS)
    if missing_safety_buttons:
        print(f"ERROR: Missing GUI safety control buttons: {', '.join(sorted(missing_safety_buttons))}")
        return 1
    print(f"Settings panels: {', '.join(GUI_PANEL_NAMES)}")
    print(f"File tool buttons: {', '.join(GUI_FILE_TOOL_BUTTONS)}")
    print(f"Voice controls: {', '.join(GUI_VOICE_CONTROL_BUTTONS)}")
    print(f"Memory controls: {', '.join(GUI_MEMORY_CONTROL_BUTTONS)}")
    print(f"Task controls: {', '.join(GUI_TASK_CONTROL_BUTTONS)}")
    print(f"Safety controls: {', '.join(GUI_SAFETY_CONTROL_BUTTONS)}")
    print("OK: GUI dependencies are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
