"""Tkinter GUI for the local PC assistant."""

from __future__ import annotations

import argparse
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk

from assistant.actions import (
    ActionError,
    PendingAction,
    add_allowed_app,
    add_allowed_folder,
    load_allowed_apps,
    load_allowed_folders,
)
from assistant.audit import ActionAuditStore
from assistant.core import LocalAssistant
from assistant.gui_dashboard import StartupHealthRow, build_startup_dashboard, build_startup_health_rows
from assistant.gui_settings import (
    GUI_MEMORY_FIELDS,
    GUI_MODEL_FIELDS,
    GUI_SETTING_FIELDS,
    GUI_TASK_FIELDS,
    GUI_VOICE_FIELDS,
    GuiSettingField,
    apply_gui_settings,
    settings_saved_text,
)
from assistant.file_tools import FileToolError
from assistant.history import HistoryStore
from assistant.memory import MemoryError, MemoryStore
from assistant.model_tools import ModelToolError, list_ollama_models
from assistant.notes import NotesStore
from assistant.ollama_client import OllamaClient
from assistant.outbox import OutboxStore
from assistant.persona import PersonaError, build_system_prompt, load_persona
from assistant.settings import SettingsError, load_settings, save_settings
from assistant.status import collect_status
from assistant.tasks import TasksError, TasksStore
from assistant.voice_audit import VoiceActionAuditStore


GUI_FILE_TOOL_BUTTONS = (
    "List",
    "Search",
    "Find Names",
    "Preview",
    "Verify Write",
    "Verify Restore",
    "Panel",
)
GUI_VOICE_CONTROL_BUTTONS = (
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
)
GUI_SAFETY_CONTROL_BUTTONS = (
    "Refresh",
    "Safety Snapshot",
    "Launch Snapshot",
    "Shell Snapshot",
    "Script Snapshot",
)
GUI_MEMORY_CONTROL_BUTTONS = (
    "Add Memory",
    "Rename Memory",
    "Delete Memory",
    "Memory Trash",
    "Restore Memory",
    "Refresh",
)
GUI_TASK_CONTROL_BUTTONS = (
    "Add Task",
    "Done",
    "Rename Task",
    "Set Due",
    "Clear Due",
    "Delete Task",
    "Task Trash",
    "Restore Deleted",
    "Refresh",
)


class AssistantGui:
    """Small local desktop chat UI."""

    def __init__(self, root: tk.Tk, settings_path: str, force_no_llm: bool = False) -> None:
        self.root = root
        self.settings_path = settings_path
        self.queue: queue.Queue[tuple[str, object | None]] = queue.Queue()
        self.pending_action: PendingAction | None = None
        self.pending_user_text: str | None = None

        settings = load_settings(settings_path)
        self.settings = settings
        system_prompt = build_system_prompt(load_persona(settings.persona_path))
        use_llm = settings.use_llm and not force_no_llm
        llm_client = None if not use_llm else OllamaClient(
            model=settings.model,
            num_gpu=settings.num_gpu,
            system_prompt=system_prompt,
        )
        self.assistant = LocalAssistant(
            name=settings.assistant_name,
            llm_client=llm_client,
            use_llm=use_llm,
            memory_store=MemoryStore(settings.memory_path),
            notes_store=NotesStore(settings.notes_path),
            tasks_store=TasksStore(settings.tasks_path),
            outbox_store=OutboxStore(settings.outbox_path),
            history_store=HistoryStore(settings.history_path, enabled=settings.history_enabled),
            action_audit_store=ActionAuditStore(
                settings.action_audit_path,
                enabled=settings.action_audit_enabled,
            ),
            voice_action_audit_store=VoiceActionAuditStore(
                settings.voice_action_audit_path,
                enabled=settings.voice_action_audit_enabled,
            ),
            aliases_path=settings.aliases_path,
            voice_model_path=settings.voice_model_path,
            settings_path=settings_path,
            persona_path=settings.persona_path,
        )
        self.model_label = "disabled" if not use_llm else settings.model
        self.num_gpu = 0 if not use_llm else settings.num_gpu
        self.health_value_labels: dict[str, ttk.Label] = {}
        self.file_folder_var = tk.StringVar(master=root)
        self.file_query_var = tk.StringVar(master=root)
        self.file_path_var = tk.StringVar(master=root)
        self.file_folder_box: ttk.Combobox | None = None

        self._build_ui()
        self._refresh_startup_health()
        self._refresh_file_toolbar_folders()
        self._append_assistant(build_startup_dashboard(settings, self.assistant, self.model_label, self.num_gpu))
        self.root.after(100, self._drain_queue)

    def _build_ui(self) -> None:
        self.root.title("Local PC Assistant")
        self.root.geometry("760x560")
        self.root.minsize(560, 420)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(4, weight=1)
        self._build_menu()

        header = ttk.Frame(self.root, padding=(10, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text="Local PC Assistant", font=("Segoe UI", 14, "bold"))
        title.grid(row=0, column=0, sticky="w")
        self.status_label = ttk.Label(header, text=f"Settings: {self.settings_path} | Model: {self.model_label}")
        self.status_label.grid(row=1, column=0, sticky="w")

        self.health_frame = ttk.LabelFrame(self.root, text="Startup Health", padding=(10, 6))
        self.health_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        self.health_frame.columnconfigure(1, weight=1)
        self.health_frame.columnconfigure(3, weight=1)
        self._build_health_dashboard()

        self._build_file_toolbar()
        self._build_voice_toolbar()

        self.transcript = scrolledtext.ScrolledText(
            self.root,
            wrap="word",
            state="disabled",
            font=("Segoe UI", 10),
        )
        self.transcript.grid(row=4, column=0, sticky="nsew", padx=10, pady=(0, 8))

        input_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        input_frame.grid(row=5, column=0, sticky="ew")
        input_frame.columnconfigure(0, weight=1)

        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(input_frame, textvariable=self.input_var)
        self.input_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.input_entry.bind("<Return>", lambda event: self._send())

        self.send_button = ttk.Button(input_frame, text="Send", command=self._send)
        self.send_button.grid(row=0, column=1, padx=(0, 8))
        self.confirm_button = ttk.Button(input_frame, text="Confirm", command=self._confirm_action, state="disabled")
        self.confirm_button.grid(row=0, column=2, padx=(0, 8))
        self.cancel_button = ttk.Button(input_frame, text="Cancel", command=self._cancel_action, state="disabled")
        self.cancel_button.grid(row=0, column=3)
        self.input_entry.focus_set()

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self.root)

        assistant_menu = tk.Menu(menu_bar, tearoff=False)
        assistant_menu.add_command(label="Briefing", command=lambda: self._run_builtin("briefing"))
        assistant_menu.add_command(label="Startup Health", command=self._show_startup_health)
        assistant_menu.add_command(label="Status", command=self._show_status)
        assistant_menu.add_command(label="Settings", command=lambda: self._run_builtin("settings"))
        assistant_menu.add_command(label="Settings Panels", command=self._show_settings_panel)
        assistant_menu.add_command(label="Edit Settings", command=self._show_settings_panel)
        assistant_menu.add_command(label="Models", command=lambda: self._run_builtin("models"))
        assistant_menu.add_command(label="Voice Status", command=lambda: self._run_builtin("voice status"))
        assistant_menu.add_command(label="Voice Audit", command=lambda: self._run_builtin("voice audit"))
        assistant_menu.add_command(label="Paths", command=lambda: self._run_builtin("paths"))
        assistant_menu.add_command(label="File Tools Panel", command=self._show_file_tools_panel)
        assistant_menu.add_command(label="Data Report", command=lambda: self._run_builtin("data report"))
        assistant_menu.add_command(label="Export Data", command=lambda: self._run_builtin("export data"))
        assistant_menu.add_command(label="Allowed Actions", command=lambda: self._run_builtin("actions"))
        assistant_menu.add_command(label="Shell Command Guide", command=lambda: self._run_builtin("shell command guide"))
        assistant_menu.add_separator()
        assistant_menu.add_command(label="About", command=lambda: self._run_builtin("about"))
        assistant_menu.add_command(label="Safety", command=lambda: self._run_builtin("safety"))
        assistant_menu.add_command(label="Permissions Dashboard", command=lambda: self._run_builtin("permissions dashboard"))
        assistant_menu.add_command(label="Safety Snapshot", command=self._show_safety_snapshot)
        assistant_menu.add_command(label="Launch Safety Snapshot", command=self._show_launch_safety_snapshot)
        assistant_menu.add_command(label="Shell Safety Snapshot", command=self._show_shell_safety_snapshot)
        assistant_menu.add_command(label="Script Safety Snapshot", command=self._show_script_safety_snapshot)
        assistant_menu.add_command(label="Roadmap", command=lambda: self._run_builtin("roadmap"))
        assistant_menu.add_command(label="Launch Commands", command=lambda: self._run_builtin("launch commands"))
        assistant_menu.add_command(label="Command Reference", command=lambda: self._run_builtin("command reference"))
        assistant_menu.add_separator()
        assistant_menu.add_command(label="Clear Transcript", command=self._clear_transcript)
        menu_bar.add_cascade(label="Assistant", menu=assistant_menu)

        data_menu = tk.Menu(menu_bar, tearoff=False)
        data_menu.add_command(label="Memories", command=lambda: self._run_builtin("memories"))
        data_menu.add_command(label="Notes", command=lambda: self._run_builtin("notes"))
        data_menu.add_command(label="Tasks", command=lambda: self._run_builtin("tasks"))
        data_menu.add_command(label="Outbox", command=lambda: self._run_builtin("outbox"))
        data_menu.add_command(label="History", command=lambda: self._run_builtin("history"))
        data_menu.add_command(label="Action Audit", command=lambda: self._run_builtin("action audit"))
        data_menu.add_command(label="Voice Audit", command=lambda: self._run_builtin("voice audit"))
        menu_bar.add_cascade(label="Local Data", menu=data_menu)

        self.root.configure(menu=menu_bar)

    @staticmethod
    def _menu_builtin_commands() -> tuple[str, ...]:
        """Return commands exposed through GUI menu shortcuts."""
        return (
            "briefing",
            "startup health",
            "settings",
            "settings panels",
            "edit settings",
            "models",
            "voice status",
            "voice audit",
            "paths",
            "file tools panel",
            "data report",
            "export data",
            "actions",
            "shell command guide",
            "about",
            "safety",
            "permissions dashboard",
            "safety snapshot",
            "safety snapshot launch",
            "safety snapshot shell",
            "safety snapshot scripts",
            "roadmap",
            "launch commands",
            "command reference",
            "memories",
            "notes",
            "tasks",
            "outbox",
            "history",
            "action audit",
            "voice audit",
        )

    def _build_health_dashboard(self) -> None:
        rows = (
            "Assistant",
            "Model",
            "GPU layers",
            "Voice model",
            "Memories",
            "Notes",
            "Open tasks",
            "Task trash",
            "Outbox",
            "History",
            "Action audit",
        )
        for index, label_text in enumerate(rows):
            row = index // 2
            column = (index % 2) * 2
            ttk.Label(self.health_frame, text=f"{label_text}:").grid(
                row=row,
                column=column,
                sticky="w",
                padx=(0, 4),
                pady=2,
            )
            value_label = ttk.Label(self.health_frame, text="checking")
            value_label.grid(row=row, column=column + 1, sticky="w", padx=(0, 16), pady=2)
            self.health_value_labels[label_text] = value_label

        refresh_button = ttk.Button(
            self.health_frame,
            text="Refresh",
            command=self._refresh_startup_health,
        )
        button_row = (len(rows) + 1) // 2
        refresh_button.grid(row=button_row, column=0, sticky="w", pady=(6, 0), padx=(0, 8))
        ttk.Button(
            self.health_frame,
            text="Safety Snapshot",
            command=self._show_safety_snapshot,
        ).grid(row=button_row, column=1, sticky="w", pady=(6, 0), padx=(0, 8))
        ttk.Button(
            self.health_frame,
            text="Launch Snapshot",
            command=self._show_launch_safety_snapshot,
        ).grid(row=button_row, column=2, sticky="e", pady=(6, 0), padx=(0, 8))
        ttk.Button(
            self.health_frame,
            text="Shell Snapshot",
            command=self._show_shell_safety_snapshot,
        ).grid(row=button_row, column=3, sticky="e", pady=(6, 0), padx=(0, 8))
        ttk.Button(
            self.health_frame,
            text="Script Snapshot",
            command=self._show_script_safety_snapshot,
        ).grid(row=button_row, column=4, sticky="e", pady=(6, 0))

    def _build_file_toolbar(self) -> None:
        frame = ttk.LabelFrame(self.root, text="Safe File Tools", padding=(10, 6))
        frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)
        frame.columnconfigure(5, weight=1)

        ttk.Label(frame, text="Folder:").grid(row=0, column=0, sticky="w", padx=(0, 4), pady=2)
        self.file_folder_box = ttk.Combobox(frame, textvariable=self.file_folder_var, state="readonly", width=18)
        self.file_folder_box.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=2)

        ttk.Label(frame, text="Search:").grid(row=0, column=2, sticky="w", padx=(0, 4), pady=2)
        ttk.Entry(frame, textvariable=self.file_query_var, width=20).grid(
            row=0,
            column=3,
            sticky="ew",
            padx=(0, 8),
            pady=2,
        )

        ttk.Label(frame, text="Path:").grid(row=0, column=4, sticky="w", padx=(0, 4), pady=2)
        ttk.Entry(frame, textvariable=self.file_path_var, width=24).grid(
            row=0,
            column=5,
            sticky="ew",
            padx=(0, 8),
            pady=2,
        )

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=1, column=0, columnspan=6, sticky="e", pady=(4, 0))
        ttk.Button(button_frame, text="List", command=self._toolbar_list_files).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_frame, text="Search", command=self._toolbar_search_files).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(button_frame, text="Find Names", command=self._toolbar_find_file_names).grid(
            row=0,
            column=2,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Preview", command=self._toolbar_preview_file).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(button_frame, text="Verify Write", command=self._toolbar_verify_bulk_write_checklist).grid(
            row=0,
            column=4,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Verify Restore", command=self._toolbar_verify_bulk_restore_checklist).grid(
            row=0,
            column=5,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Panel", command=self._show_file_tools_panel).grid(row=0, column=6)

    def _build_voice_toolbar(self) -> None:
        frame = ttk.LabelFrame(self.root, text="Voice Controls", padding=(10, 6))
        frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))
        frame.columnconfigure(0, weight=1)

        summary = (
            f"Input {'on' if self.settings.voice_enabled else 'off'} | "
            f"Output {'on' if self.settings.speak_enabled else 'off'} | "
            f"Timeout {self.settings.voice_timeout}s"
        )
        ttk.Label(frame, text=summary).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 4))

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=1, column=0, sticky="e", pady=(2, 0))
        ttk.Button(button_frame, text="Voice Status", command=lambda: self._run_builtin("voice status")).grid(
            row=0,
            column=0,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Voice Audit", command=lambda: self._run_builtin("voice audit")).grid(
            row=0,
            column=1,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Voice Help", command=self._show_voice_launch_help).grid(
            row=0,
            column=2,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Wake Help", command=lambda: self._run_builtin("wake status")).grid(
            row=0,
            column=3,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Action Review", command=self._show_voice_action_review).grid(
            row=0,
            column=4,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Launch Commands", command=lambda: self._run_builtin("launch commands")).grid(
            row=0,
            column=5,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Copy Wake Cmd", command=self._copy_wake_launch_command).grid(row=0, column=6)
        audit_frame = ttk.Frame(frame)
        audit_frame.grid(row=2, column=0, sticky="e", pady=(6, 0))
        self._build_voice_audit_buttons(audit_frame)

    def _build_voice_audit_buttons(self, frame: ttk.Frame) -> None:
        """Build read-only voice audit filter/export shortcuts."""
        buttons = (
            ("Low Confidence Audit", "voice audit confidence low"),
            ("Action Preview Audit", "voice audit event action_preview"),
            ("Export Voice Audit", "export voice audit"),
            ("Retention Preview", "voice audit retention keep 100"),
            ("Prune Audit", "prune voice audit keep 100"),
        )
        for column, (label, command) in enumerate(buttons):
            ttk.Button(frame, text=label, command=lambda command=command: self._run_builtin(command)).grid(
                row=0,
                column=column,
                padx=(0, 8) if column < len(buttons) - 1 else 0,
            )

    def _refresh_startup_health(self) -> None:
        for row in self._startup_health_rows():
            label = self.health_value_labels.get(row.label)
            if label is not None:
                prefix = "OK" if row.ok else "Check"
                label.configure(text=f"{prefix}: {row.value}")

    def _refresh_file_toolbar_folders(self) -> None:
        try:
            folders = self.assistant._file_tools().folder_names()
        except FileToolError as exc:
            self._append_assistant(f"File tools error: {exc}")
            return
        if self.file_folder_box is not None:
            self.file_folder_box.configure(values=folders)
        if folders and not self.file_folder_var.get():
            preferred = "project folder" if "project folder" in folders else folders[0]
            self.file_folder_var.set(preferred)

    def _selected_toolbar_folder(self) -> str | None:
        folder = self.file_folder_var.get().strip()
        if folder:
            return folder
        self._append_assistant("Choose an allowlisted folder first.")
        return None

    def _toolbar_list_files(self) -> None:
        folder = self._selected_toolbar_folder()
        if not folder:
            return
        try:
            text = self.assistant._file_tools().list_files_summary(folder)
        except FileToolError as exc:
            text = f"File tools error: {exc}"
        self._append_assistant(text)

    def _toolbar_search_files(self) -> None:
        folder = self._selected_toolbar_folder()
        if not folder:
            return
        try:
            text = self.assistant._file_tools().search_files_summary(folder, self.file_query_var.get())
        except FileToolError as exc:
            text = f"File tools error: {exc}"
        self._append_assistant(text)

    def _toolbar_find_file_names(self) -> None:
        folder = self._selected_toolbar_folder()
        if not folder:
            return
        try:
            text = self.assistant._file_tools().search_file_names_summary(folder, self.file_query_var.get())
        except FileToolError as exc:
            text = f"File tools error: {exc}"
        self._append_assistant(text)

    def _toolbar_preview_file(self) -> None:
        folder = self._selected_toolbar_folder()
        relative_path = self.file_path_var.get().strip()
        if not folder:
            return
        if not relative_path:
            self._append_assistant("Enter a relative file path to preview.")
            return
        try:
            text = self.assistant._file_tools().open_file_preview_summary(folder, relative_path)
        except FileToolError as exc:
            text = f"File tools error: {exc}"
        self._append_assistant(text)

    def _toolbar_verify_bulk_write_checklist(self) -> None:
        self._run_builtin("verify bulk write checklist")

    def _toolbar_verify_bulk_restore_checklist(self) -> None:
        self._run_builtin("verify bulk restore checklist")

    def _voice_launch_command(self, mode: str) -> str:
        base = ["python -m assistant.cli"]
        if self.model_label != "disabled":
            base.append(f"--model {self.settings.model}")
            base.append(f"--num-gpu {self.settings.num_gpu}")
        else:
            base.append("--no-llm")
        if mode == "voice":
            base.append(f"--voice --voice-timeout {self.settings.voice_timeout}")
        elif mode == "speak":
            base.append("--speak")
        elif mode == "voice_speak":
            base.append(f"--voice --speak --voice-timeout {self.settings.voice_timeout}")
        elif mode == "wake":
            base.append(f"--wake --speak --voice-timeout {self.settings.voice_timeout}")
        return " ".join(base)

    def _voice_launch_help_text(self) -> str:
        return "\n".join(
            [
                "GUI voice launch help",
                "The GUI does not start listening automatically.",
                "Use these terminal commands for the tested CLI voice paths:",
                f"- Voice input: {self._voice_launch_command('voice')}",
                f"- Voice output: {self._voice_launch_command('speak')}",
                f"- Voice input and output: {self._voice_launch_command('voice_speak')}",
                f"- Wake loop: {self._voice_launch_command('wake')}",
                "Wake mode is optional and existing confirmations still apply.",
            ]
        )

    def _show_voice_launch_help(self) -> None:
        self._append_assistant(self._voice_launch_help_text())

    def _voice_action_review_text(self) -> str:
        return "\n".join(
            [
                "GUI voice action review",
                "Voice action commands are previewed before they can run.",
                "The preview shows what was heard, the pending action, and the confirmation choices.",
                "CLI voice mode also prints a read-only confidence level when Vosk provides word scores.",
                "Low or unavailable confidence is a signal to correct or cancel before confirming.",
                "Low-confidence spoken action commands require 'yes' and then the extra phrase 'confirm action'.",
                "Use voice safety drill to practice the low-confidence flow without the microphone.",
                "Say 'yes' to confirm only after the preview.",
                "Say 'no' to cancel.",
                "Correction phrases:",
                "- correct <command>",
                "- change to <command>",
                "- actually <command>",
                "- instead <command>",
                "- no, <command>",
                "- cancel and <command>",
                "- replace with <command>",
                "- I meant <command>",
                "- I said <command>",
                "- make that <command>",
                "The GUI keeps typed Confirm and Cancel buttons; microphone listening still uses the tested CLI voice path.",
            ]
        )

    def _show_voice_action_review(self) -> None:
        self._append_assistant(self._voice_action_review_text())

    def _copy_wake_launch_command(self) -> None:
        command = self._voice_launch_command("wake")
        self.root.clipboard_clear()
        self.root.clipboard_append(command)
        self._append_assistant(f"Copied wake launch command:\n{command}")

    def _startup_health_rows(self) -> list[StartupHealthRow]:
        return build_startup_health_rows(
            self.settings,
            self.assistant,
            self.model_label,
            self.num_gpu,
        )

    def _show_startup_health(self) -> None:
        self._refresh_startup_health()
        lines = ["Startup health"]
        for row in self._startup_health_rows():
            prefix = "OK" if row.ok else "Check"
            lines.append(f"- {row.label}: {prefix}: {row.value}")
        self._append_assistant("\n".join(lines))

    def _show_status(self) -> None:
        status = collect_status(self.settings)
        self._append_assistant(status.summary())

    def _show_safety_snapshot(self) -> None:
        self._run_builtin("safety snapshot")

    def _show_launch_safety_snapshot(self) -> None:
        self._run_builtin("safety snapshot launch")

    def _show_shell_safety_snapshot(self) -> None:
        self._run_builtin("safety snapshot shell")

    def _show_script_safety_snapshot(self) -> None:
        self._run_builtin("safety snapshot scripts")

    def _show_file_tools_panel(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Safe File Tools")
        window.transient(self.root)
        window.geometry("760x520")
        window.minsize(620, 420)
        window.columnconfigure(1, weight=1)
        window.rowconfigure(4, weight=1)

        folder_var = tk.StringVar()
        query_var = tk.StringVar()
        path_var = tk.StringVar()

        ttk.Label(window, text="Allowlisted folder:").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))
        folder_box = ttk.Combobox(window, textvariable=folder_var, state="readonly")
        folder_box.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(10, 4))

        ttk.Label(window, text="Search text:").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        ttk.Entry(window, textvariable=query_var).grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=4)

        ttk.Label(window, text="Relative file path:").grid(row=2, column=0, sticky="w", padx=10, pady=4)
        ttk.Entry(window, textvariable=path_var).grid(row=2, column=1, sticky="ew", padx=(0, 10), pady=4)

        result_text = tk.Text(window, wrap="word", height=14)
        result_text.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=10, pady=(8, 10))

        def selected_folder() -> str | None:
            folder = folder_var.get().strip()
            if folder:
                return folder
            self._set_text(result_text, "Choose an allowlisted folder first.")
            return None

        def refresh_folders() -> None:
            try:
                folders = self.assistant._file_tools().folder_names()
            except FileToolError as exc:
                self._set_text(result_text, f"File tools error: {exc}")
                return
            folder_box.configure(values=folders)
            if folders and not folder_var.get():
                folder_var.set(folders[0])

        def list_files() -> None:
            folder = selected_folder()
            if not folder:
                return
            try:
                text = self.assistant._file_tools().list_files_summary(folder)
            except FileToolError as exc:
                text = f"File tools error: {exc}"
            self._set_text(result_text, text)

        def search_contents() -> None:
            folder = selected_folder()
            if not folder:
                return
            try:
                text = self.assistant._file_tools().search_files_summary(folder, query_var.get())
            except FileToolError as exc:
                text = f"File tools error: {exc}"
            self._set_text(result_text, text)

        def search_names() -> None:
            folder = selected_folder()
            if not folder:
                return
            try:
                text = self.assistant._file_tools().search_file_names_summary(folder, query_var.get())
            except FileToolError as exc:
                text = f"File tools error: {exc}"
            self._set_text(result_text, text)

        def preview_file() -> None:
            folder = selected_folder()
            relative_path = path_var.get().strip()
            if not folder:
                return
            if not relative_path:
                self._set_text(result_text, "Enter a relative file path to preview.")
                return
            try:
                text = self.assistant._file_tools().open_file_preview_summary(folder, relative_path)
            except FileToolError as exc:
                text = f"File tools error: {exc}"
            self._set_text(result_text, text)

        button_frame = ttk.Frame(window)
        button_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 0))
        ttk.Button(button_frame, text="Refresh Folders", command=refresh_folders).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_frame, text="List Files", command=list_files).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(button_frame, text="Search Contents", command=search_contents).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(button_frame, text="Search Names", command=search_names).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(button_frame, text="Preview File", command=preview_file).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(
            button_frame,
            text="Verify Write Checklist",
            command=lambda: self._set_text(result_text, self.assistant.respond("verify bulk write checklist").text),
        ).grid(row=0, column=5, padx=(0, 8))
        ttk.Button(
            button_frame,
            text="Verify Restore Checklist",
            command=lambda: self._set_text(result_text, self.assistant.respond("verify bulk restore checklist").text),
        ).grid(row=0, column=6)

        refresh_folders()
        self._set_text(
            result_text,
            "Safe file tools are limited to allowlisted folders. Preview does not launch files in Windows. Bulk checklist verification is read-only.",
        )

    def _show_settings_panel(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Assistant Settings Panels")
        window.transient(self.root)
        window.geometry("720x520")
        window.minsize(620, 420)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(window)
        notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self._build_general_settings_tab(notebook, window)
        self._build_apps_settings_tab(notebook)
        self._build_folders_settings_tab(notebook)
        self._build_models_settings_tab(notebook, window)
        self._build_voice_settings_tab(notebook, window)
        self._build_memory_settings_tab(notebook, window)
        self._build_tasks_settings_tab(notebook, window)

    def _build_general_settings_tab(self, notebook: ttk.Notebook, window: tk.Toplevel) -> None:
        frame = ttk.Frame(notebook, padding=10)
        frame.columnconfigure(1, weight=1)
        notebook.add(frame, text="General")

        variables = self._build_settings_fields(frame, GUI_SETTING_FIELDS)
        self._build_settings_buttons(frame, len(GUI_SETTING_FIELDS), window, variables)

    def _build_models_settings_tab(self, notebook: ttk.Notebook, window: tk.Toplevel) -> None:
        frame = ttk.Frame(notebook, padding=10)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)
        notebook.add(frame, text="Models")

        variables = self._build_settings_fields(frame, GUI_MODEL_FIELDS)
        self._build_settings_buttons(frame, len(GUI_MODEL_FIELDS), window, variables)

        ttk.Label(frame, text="Installed Ollama models:").grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(12, 4),
        )
        models_text = tk.Text(frame, height=8, wrap="word")
        models_text.grid(row=5, column=0, columnspan=2, sticky="nsew")

        def refresh_models() -> None:
            try:
                models = list_ollama_models()
                text = "\n".join(models) if models else "No installed models found."
            except ModelToolError as exc:
                text = f"Model error: {exc}"
            self._set_text(models_text, text)

        ttk.Button(frame, text="Refresh Models", command=refresh_models).grid(
            row=6,
            column=1,
            sticky="e",
            pady=(8, 0),
        )
        refresh_models()

    def _build_voice_settings_tab(self, notebook: ttk.Notebook, window: tk.Toplevel) -> None:
        frame = ttk.Frame(notebook, padding=10)
        frame.columnconfigure(1, weight=1)
        notebook.add(frame, text="Voice")

        variables = self._build_settings_fields(frame, GUI_VOICE_FIELDS)
        self._build_settings_buttons(frame, len(GUI_VOICE_FIELDS), window, variables)
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=len(GUI_VOICE_FIELDS) + 1, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(button_frame, text="Voice Status", command=lambda: self._run_builtin("voice status")).grid(
            row=0,
            column=0,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Voice Audit", command=lambda: self._run_builtin("voice audit")).grid(
            row=0,
            column=1,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Voice Help", command=self._show_voice_launch_help).grid(
            row=0,
            column=2,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Wake Help", command=lambda: self._run_builtin("wake status")).grid(
            row=0,
            column=3,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Action Review", command=self._show_voice_action_review).grid(
            row=0,
            column=4,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Copy Wake Cmd", command=self._copy_wake_launch_command).grid(row=0, column=5)
        audit_frame = ttk.Frame(frame)
        audit_frame.grid(row=len(GUI_VOICE_FIELDS) + 2, column=0, columnspan=2, sticky="e", pady=(6, 0))
        self._build_voice_audit_buttons(audit_frame)

    def _build_memory_settings_tab(self, notebook: ttk.Notebook, window: tk.Toplevel) -> None:
        frame = ttk.Frame(notebook, padding=10)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)
        notebook.add(frame, text="Memory")

        variables = self._build_settings_fields(frame, GUI_MEMORY_FIELDS)
        self._build_settings_buttons(frame, len(GUI_MEMORY_FIELDS), window, variables)

        ttk.Label(frame, text="Saved memories:").grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 4))
        memory_text = tk.Text(frame, height=10, wrap="word")
        memory_text.grid(row=3, column=0, columnspan=2, sticky="nsew")

        entry_var = tk.StringVar()
        memory_number_var = tk.StringVar(value="1")
        rename_var = tk.StringVar()
        ttk.Entry(frame, textvariable=entry_var).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        memory_action_frame = ttk.Frame(frame)
        memory_action_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        memory_action_frame.columnconfigure(3, weight=1)
        ttk.Label(memory_action_frame, text="Number:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Entry(memory_action_frame, textvariable=memory_number_var, width=8).grid(
            row=0,
            column=1,
            sticky="w",
            padx=(0, 8),
        )
        ttk.Label(memory_action_frame, text="New text:").grid(row=0, column=2, sticky="w", padx=(0, 4))
        ttk.Entry(memory_action_frame, textvariable=rename_var).grid(row=0, column=3, sticky="ew")

        def refresh_memory() -> None:
            try:
                text = self.assistant.memory_store.summary()
            except MemoryError as exc:
                text = f"Memory error: {exc}"
            self._set_text(memory_text, text)

        def add_memory() -> None:
            text = entry_var.get().strip()
            if not text:
                return
            try:
                self.assistant.memory_store.remember(text)
            except MemoryError as exc:
                self._append_assistant(f"Memory error: {exc}")
                return
            entry_var.set("")
            refresh_memory()
            self._refresh_startup_health()

        def memory_number() -> str:
            return memory_number_var.get().strip() or "1"

        def rename_memory() -> None:
            text = rename_var.get().strip()
            if not text:
                self._append_assistant("Enter new memory text first.")
                return
            self._run_builtin(f"rename memory {memory_number()} to {text}")
            refresh_memory()

        def delete_memory() -> None:
            self._run_builtin(f"delete memory {memory_number()}")

        def restore_memory() -> None:
            self._run_builtin(f"restore memory {memory_number()}")
            refresh_memory()

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=6, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(button_frame, text="Add Memory", command=add_memory).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_frame, text="Rename Memory", command=rename_memory).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(button_frame, text="Delete Memory", command=delete_memory).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(button_frame, text="Memory Trash", command=lambda: self._run_builtin("memory trash")).grid(
            row=0,
            column=3,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Restore Memory", command=restore_memory).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(button_frame, text="Refresh", command=refresh_memory).grid(row=0, column=5)
        refresh_memory()

    def _build_tasks_settings_tab(self, notebook: ttk.Notebook, window: tk.Toplevel) -> None:
        frame = ttk.Frame(notebook, padding=10)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)
        notebook.add(frame, text="Tasks")

        variables = self._build_settings_fields(frame, GUI_TASK_FIELDS)
        self._build_settings_buttons(frame, len(GUI_TASK_FIELDS), window, variables)

        ttk.Label(frame, text="Open tasks:").grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 4))
        tasks_text = tk.Text(frame, height=10, wrap="word")
        tasks_text.grid(row=3, column=0, columnspan=2, sticky="nsew")

        entry_var = tk.StringVar()
        task_number_var = tk.StringVar(value="1")
        task_text_var = tk.StringVar()
        due_date_var = tk.StringVar()
        ttk.Entry(frame, textvariable=entry_var).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        task_action_frame = ttk.Frame(frame)
        task_action_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        task_action_frame.columnconfigure(3, weight=1)
        task_action_frame.columnconfigure(5, weight=1)
        ttk.Label(task_action_frame, text="Number:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Entry(task_action_frame, textvariable=task_number_var, width=8).grid(
            row=0,
            column=1,
            sticky="w",
            padx=(0, 8),
        )
        ttk.Label(task_action_frame, text="Text:").grid(row=0, column=2, sticky="w", padx=(0, 4))
        ttk.Entry(task_action_frame, textvariable=task_text_var).grid(row=0, column=3, sticky="ew", padx=(0, 8))
        ttk.Label(task_action_frame, text="Due:").grid(row=0, column=4, sticky="w", padx=(0, 4))
        ttk.Entry(task_action_frame, textvariable=due_date_var, width=14).grid(row=0, column=5, sticky="ew")

        def refresh_tasks() -> None:
            try:
                text = self.assistant.tasks_store.summary()
            except TasksError as exc:
                text = f"Tasks error: {exc}"
            self._set_text(tasks_text, text)

        def add_task() -> None:
            text = entry_var.get().strip()
            if not text:
                return
            try:
                self.assistant.tasks_store.add(text)
            except TasksError as exc:
                self._append_assistant(f"Tasks error: {exc}")
                return
            entry_var.set("")
            refresh_tasks()
            self._refresh_startup_health()

        def task_number() -> str:
            return task_number_var.get().strip() or "1"

        def done_task() -> None:
            self._run_builtin(f"done {task_number()}")
            refresh_tasks()
            self._refresh_startup_health()

        def rename_task() -> None:
            text = task_text_var.get().strip()
            if not text:
                self._append_assistant("Enter new task text first.")
                return
            self._run_builtin(f"rename task {task_number()} to {text}")
            refresh_tasks()

        def set_due() -> None:
            due_date = due_date_var.get().strip()
            if not due_date:
                self._append_assistant("Enter a due date as YYYY-MM-DD first.")
                return
            self._run_builtin(f"due {task_number()} {due_date}")
            refresh_tasks()

        def clear_due() -> None:
            self._run_builtin(f"clear due {task_number()}")
            refresh_tasks()

        def delete_task() -> None:
            self._run_builtin(f"delete task {task_number()}")

        def restore_deleted_task() -> None:
            self._run_builtin(f"restore deleted task {task_number()}")
            refresh_tasks()

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=6, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(button_frame, text="Add Task", command=add_task).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_frame, text="Done", command=done_task).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(button_frame, text="Rename Task", command=rename_task).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(button_frame, text="Set Due", command=set_due).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(button_frame, text="Clear Due", command=clear_due).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(button_frame, text="Delete Task", command=delete_task).grid(row=0, column=5, padx=(0, 8))
        ttk.Button(button_frame, text="Task Trash", command=lambda: self._run_builtin("task trash")).grid(
            row=0,
            column=6,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Restore Deleted", command=restore_deleted_task).grid(
            row=0,
            column=7,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Refresh", command=refresh_tasks).grid(row=0, column=8)
        refresh_tasks()

    def _build_apps_settings_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=10)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)
        notebook.add(frame, text="Apps")

        tree = ttk.Treeview(frame, columns=("name", "target"), show="headings", height=10)
        tree.heading("name", text="Name")
        tree.heading("target", text="Executable")
        tree.column("name", width=160)
        tree.column("target", width=420)
        tree.grid(row=0, column=0, columnspan=4, sticky="nsew")

        name_var = tk.StringVar()
        target_var = tk.StringVar()
        ttk.Label(frame, text="Name:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=name_var).grid(row=1, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(frame, text="Executable:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(frame, textvariable=target_var).grid(row=2, column=1, columnspan=3, sticky="ew", pady=(4, 0))

        def refresh() -> None:
            self._refresh_allowlist_tree(tree, load_allowed_apps())

        def add_app() -> None:
            try:
                add_allowed_app(name_var.get(), target_var.get())
            except ActionError as exc:
                self._append_assistant(f"App allowlist error: {exc}")
                return
            name_var.set("")
            target_var.set("")
            refresh()
            self._refresh_startup_health()

        ttk.Button(frame, text="Add App", command=add_app).grid(row=3, column=2, sticky="e", pady=(8, 0), padx=(0, 8))
        ttk.Button(frame, text="Refresh", command=refresh).grid(row=3, column=3, sticky="e", pady=(8, 0))
        refresh()

    def _build_folders_settings_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=10)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)
        notebook.add(frame, text="Folders")

        tree = ttk.Treeview(frame, columns=("name", "target"), show="headings", height=10)
        tree.heading("name", text="Name")
        tree.heading("target", text="Folder")
        tree.column("name", width=160)
        tree.column("target", width=420)
        tree.grid(row=0, column=0, columnspan=4, sticky="nsew")

        name_var = tk.StringVar()
        target_var = tk.StringVar()
        ttk.Label(frame, text="Name:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=name_var).grid(row=1, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(frame, text="Folder path:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(frame, textvariable=target_var).grid(row=2, column=1, columnspan=3, sticky="ew", pady=(4, 0))

        def refresh() -> None:
            self._refresh_allowlist_tree(tree, load_allowed_folders())

        def add_folder() -> None:
            try:
                add_allowed_folder(name_var.get(), target_var.get())
            except ActionError as exc:
                self._append_assistant(f"Folder allowlist error: {exc}")
                return
            name_var.set("")
            target_var.set("")
            refresh()
            self._refresh_startup_health()

        ttk.Button(frame, text="Add Folder", command=add_folder).grid(row=3, column=2, sticky="e", pady=(8, 0), padx=(0, 8))
        ttk.Button(frame, text="Refresh", command=refresh).grid(row=3, column=3, sticky="e", pady=(8, 0))
        refresh()

    def _build_settings_fields(
        self,
        parent: ttk.Frame,
        fields: tuple[GuiSettingField, ...],
    ) -> dict[str, tk.Variable]:
        variables: dict[str, tk.Variable] = {}
        for row, field in enumerate(fields):
            ttk.Label(parent, text=f"{field.label}:").grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 8),
                pady=4,
            )
            current_value = getattr(self.settings, field.key)
            if field.kind == "bool":
                variable = tk.BooleanVar(value=bool(current_value))
                control = ttk.Checkbutton(parent, variable=variable)
            else:
                variable = tk.StringVar(value=str(current_value))
                control = ttk.Entry(parent, textvariable=variable, width=44)
            control.grid(row=row, column=1, sticky="ew", pady=4)
            variables[field.key] = variable
        return variables

    def _build_settings_buttons(
        self,
        parent: ttk.Frame,
        row: int,
        window: tk.Toplevel,
        variables: dict[str, tk.Variable],
    ) -> None:
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=row, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(
            button_frame,
            text="Save",
            command=lambda: self._save_settings_panel_values(window, variables),
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_frame, text="Close", command=window.destroy).grid(row=0, column=1)

    @staticmethod
    def _refresh_allowlist_tree(tree: ttk.Treeview, values: dict[str, str]) -> None:
        for item in tree.get_children():
            tree.delete(item)
        for name, target in sorted(values.items()):
            tree.insert("", "end", values=(name, target))

    @staticmethod
    def _set_text(widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.configure(state="disabled")

    def _save_settings_panel_values(
        self,
        window: tk.Toplevel,
        variables: dict[str, tk.Variable],
    ) -> None:
        values = {key: variable.get() for key, variable in variables.items()}
        try:
            updated = apply_gui_settings(self.settings, values)
            save_settings(updated, self.settings_path)
        except SettingsError as exc:
            self._append_assistant(f"Settings error: {exc}")
            return

        self.settings = updated
        model_label = getattr(self, "model_label", updated.model)
        self.status_label.configure(text=f"Settings: {self.settings_path} | Model: {model_label}")
        self._refresh_startup_health()
        window.destroy()
        self._append_assistant(settings_saved_text(self.settings_path))

    def _run_builtin(self, command: str) -> None:
        response = self.assistant.respond(command)
        self.pending_action = response.pending_action
        self._append_assistant(response.text)
        self._set_pending_buttons(self.pending_action is not None)

    def _clear_transcript(self) -> None:
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self._append_assistant("Transcript cleared.")

    def _send(self) -> None:
        user_text = self.input_var.get().strip()
        if not user_text:
            return

        self.input_var.set("")
        self._append_user(user_text)

        if self.pending_action:
            normalized = user_text.lower()
            if normalized in {"yes", "y", "confirm", "ok", "okay"}:
                self._confirm_action(user_text=user_text)
            else:
                self._cancel_action(user_text=user_text)
            return

        self._set_busy(True)
        thread = threading.Thread(target=self._respond_in_background, args=(user_text,), daemon=True)
        thread.start()

    def _respond_in_background(self, user_text: str) -> None:
        response = self.assistant.respond(user_text)
        self.queue.put(("assistant_response", (user_text, response)))

    def _confirm_action(self, user_text: str = "Confirm") -> None:
        if not self.pending_action:
            return

        action = self.pending_action
        self.pending_action = None
        self._set_pending_buttons(False)
        self._set_busy(True)
        thread = threading.Thread(
            target=self._execute_action_in_background,
            args=(user_text, action),
            daemon=True,
        )
        thread.start()

    def _execute_action_in_background(self, user_text: str, action: PendingAction) -> None:
        try:
            text = self.assistant.confirm_pending_action(action)
            self.assistant.action_audit_store.record(
                action,
                status="confirmed",
                requested_by=user_text,
                result=text,
            )
        except ActionError as exc:
            text = f"Action failed: {exc}"
            self.assistant.action_audit_store.record(
                action,
                status="failed",
                requested_by=user_text,
                result=text,
            )
        self.queue.put(("assistant_text", (user_text, text)))

    def _cancel_action(self, user_text: str = "Cancel") -> None:
        if not self.pending_action:
            return
        action = self.pending_action
        self.pending_action = None
        self._set_pending_buttons(False)
        text = "Cancelled."
        self._append_assistant(text)
        self.assistant.action_audit_store.record(
            action,
            status="cancelled",
            requested_by=user_text,
            result=text,
        )
        self.assistant.record_turn(user_text, text)

    def _drain_queue(self) -> None:
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                break

            if kind == "assistant_response":
                user_text, response = payload  # type: ignore[misc]
                self.pending_action = response.pending_action
                self._append_assistant(response.text)
                self.assistant.record_turn(user_text, response.text)
                self._set_pending_buttons(self.pending_action is not None)
                self._set_busy(False)
            elif kind == "assistant_text":
                user_text, text = payload  # type: ignore[misc]
                self._append_assistant(str(text))
                self.assistant.record_turn(str(user_text), str(text))
                self._set_busy(False)

        self.root.after(100, self._drain_queue)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.send_button.configure(state=state)
        self.input_entry.configure(state=state)
        if not busy:
            self.input_entry.focus_set()

    def _set_pending_buttons(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.confirm_button.configure(state=state)
        self.cancel_button.configure(state=state)

    def _append_user(self, text: str) -> None:
        self._append_line(f"You: {text}\n")

    def _append_assistant(self, text: str) -> None:
        self._append_line(f"Assistant: {text}\n\n")

    def _append_line(self, text: str) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", text)
        self.transcript.configure(state="disabled")
        self.transcript.see("end")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local PC assistant GUI.")
    parser.add_argument("--settings-path", default="config/settings.json")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    try:
        root = tk.Tk()
        AssistantGui(root, settings_path=args.settings_path, force_no_llm=args.no_llm)
    except (SettingsError, PersonaError) as exc:
        print(f"Startup error: {exc}")
        return 1

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
