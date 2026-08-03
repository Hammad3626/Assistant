import unittest
from unittest.mock import Mock, patch

from assistant.gui import (
    AssistantGui,
    GUI_FILE_TOOL_BUTTONS,
    GUI_MEMORY_CONTROL_BUTTONS,
    GUI_SAFETY_CONTROL_BUTTONS,
    GUI_TASK_CONTROL_BUTTONS,
    GUI_VOICE_CONTROL_BUTTONS,
)
from assistant.settings import AssistantSettings


class GuiTests(unittest.TestCase):
    @patch("assistant.gui.tk.Tk")
    def test_gui_module_imports_without_starting_mainloop(self, mock_tk) -> None:
        self.assertTrue(hasattr(AssistantGui, "_send"))

    def test_run_builtin_appends_response(self) -> None:
        gui = object.__new__(AssistantGui)
        gui.assistant = Mock()
        gui.assistant.respond.return_value.text = "Current settings"
        gui.assistant.respond.return_value.pending_action = None
        gui._append_assistant = Mock()
        gui._set_pending_buttons = Mock()

        gui._run_builtin("settings")

        gui.assistant.respond.assert_called_once_with("settings")
        gui._append_assistant.assert_called_once_with("Current settings")
        gui._set_pending_buttons.assert_called_once_with(False)

    def test_run_builtin_enables_confirmation_for_pending_actions(self) -> None:
        gui = object.__new__(AssistantGui)
        action = Mock()
        gui.assistant = Mock()
        gui.assistant.respond.return_value.text = "Please confirm."
        gui.assistant.respond.return_value.pending_action = action
        gui._append_assistant = Mock()
        gui._set_pending_buttons = Mock()

        gui._run_builtin("prune voice audit keep 100")

        self.assertIs(gui.pending_action, action)
        gui._set_pending_buttons.assert_called_once_with(True)

    def test_gui_menu_commands_are_declared(self) -> None:
        commands = AssistantGui._menu_builtin_commands()

        self.assertIn("models", commands)
        self.assertIn("startup health", commands)
        self.assertIn("voice status", commands)
        self.assertIn("voice audit", commands)
        self.assertIn("paths", commands)
        self.assertIn("file tools panel", commands)
        self.assertIn("safety", commands)
        self.assertIn("permissions dashboard", commands)
        self.assertIn("safety snapshot", commands)
        self.assertIn("safety snapshot launch", commands)
        self.assertIn("safety snapshot shell", commands)
        self.assertIn("safety snapshot scripts", commands)
        self.assertIn("shell command guide", commands)
        self.assertIn("roadmap", commands)
        self.assertIn("launch commands", commands)
        self.assertIn("command reference", commands)
        self.assertIn("outbox", commands)
        self.assertIn("settings panels", commands)
        self.assertIn("edit settings", commands)

    def test_gui_voice_controls_are_declared(self) -> None:
        self.assertIn("Voice Status", GUI_VOICE_CONTROL_BUTTONS)
        self.assertIn("Voice Audit", GUI_VOICE_CONTROL_BUTTONS)
        self.assertIn("Low Confidence Audit", GUI_VOICE_CONTROL_BUTTONS)
        self.assertIn("Action Preview Audit", GUI_VOICE_CONTROL_BUTTONS)
        self.assertIn("Export Voice Audit", GUI_VOICE_CONTROL_BUTTONS)
        self.assertIn("Retention Preview", GUI_VOICE_CONTROL_BUTTONS)
        self.assertIn("Prune Audit", GUI_VOICE_CONTROL_BUTTONS)
        self.assertIn("Wake Help", GUI_VOICE_CONTROL_BUTTONS)
        self.assertIn("Action Review", GUI_VOICE_CONTROL_BUTTONS)
        self.assertIn("Copy Wake Cmd", GUI_VOICE_CONTROL_BUTTONS)

    def test_gui_file_tool_controls_include_bulk_checklist_verification(self) -> None:
        self.assertIn("Verify Write", GUI_FILE_TOOL_BUTTONS)
        self.assertIn("Verify Restore", GUI_FILE_TOOL_BUTTONS)

    def test_gui_memory_controls_are_declared(self) -> None:
        self.assertIn("Rename Memory", GUI_MEMORY_CONTROL_BUTTONS)
        self.assertIn("Delete Memory", GUI_MEMORY_CONTROL_BUTTONS)
        self.assertIn("Memory Trash", GUI_MEMORY_CONTROL_BUTTONS)
        self.assertIn("Restore Memory", GUI_MEMORY_CONTROL_BUTTONS)

    def test_gui_task_controls_are_declared(self) -> None:
        self.assertIn("Done", GUI_TASK_CONTROL_BUTTONS)
        self.assertIn("Rename Task", GUI_TASK_CONTROL_BUTTONS)
        self.assertIn("Set Due", GUI_TASK_CONTROL_BUTTONS)
        self.assertIn("Clear Due", GUI_TASK_CONTROL_BUTTONS)
        self.assertIn("Delete Task", GUI_TASK_CONTROL_BUTTONS)
        self.assertIn("Task Trash", GUI_TASK_CONTROL_BUTTONS)
        self.assertIn("Restore Deleted", GUI_TASK_CONTROL_BUTTONS)

    def test_gui_safety_controls_are_declared(self) -> None:
        self.assertIn("Safety Snapshot", GUI_SAFETY_CONTROL_BUTTONS)
        self.assertIn("Launch Snapshot", GUI_SAFETY_CONTROL_BUTTONS)
        self.assertIn("Shell Snapshot", GUI_SAFETY_CONTROL_BUTTONS)
        self.assertIn("Script Snapshot", GUI_SAFETY_CONTROL_BUTTONS)

    def test_show_safety_snapshots_use_safe_builtin_commands(self) -> None:
        gui = object.__new__(AssistantGui)
        gui._run_builtin = Mock()

        gui._show_safety_snapshot()
        gui._show_launch_safety_snapshot()
        gui._show_shell_safety_snapshot()
        gui._show_script_safety_snapshot()

        gui._run_builtin.assert_any_call("safety snapshot")
        gui._run_builtin.assert_any_call("safety snapshot launch")
        gui._run_builtin.assert_any_call("safety snapshot shell")
        gui._run_builtin.assert_any_call("safety snapshot scripts")

    def test_toolbar_bulk_checklist_verification_uses_safe_builtin_commands(self) -> None:
        gui = object.__new__(AssistantGui)
        gui._run_builtin = Mock()

        gui._toolbar_verify_bulk_write_checklist()
        gui._toolbar_verify_bulk_restore_checklist()

        gui._run_builtin.assert_any_call("verify bulk write checklist")
        gui._run_builtin.assert_any_call("verify bulk restore checklist")

    @patch("assistant.gui.ttk.Button")
    def test_voice_audit_buttons_use_safe_builtin_commands(self, mock_button) -> None:
        gui = object.__new__(AssistantGui)
        gui._run_builtin = Mock()
        frame = Mock()
        created_commands = []

        def make_button(parent, text, command):
            created_commands.append((text, command))
            button = Mock()
            button.grid = Mock()
            return button

        mock_button.side_effect = make_button

        gui._build_voice_audit_buttons(frame)
        for _, command in created_commands:
            command()

        gui._run_builtin.assert_any_call("voice audit confidence low")
        gui._run_builtin.assert_any_call("voice audit event action_preview")
        gui._run_builtin.assert_any_call("export voice audit")

    def test_voice_launch_help_uses_current_settings(self) -> None:
        gui = object.__new__(AssistantGui)
        gui.settings = AssistantSettings(model="smollm2:135m", num_gpu=0, voice_timeout=10)
        gui.model_label = "smollm2:135m"

        text = gui._voice_launch_help_text()

        self.assertIn("GUI voice launch help", text)
        self.assertIn("--voice --speak --voice-timeout 10", text)
        self.assertIn("--wake --speak --voice-timeout 10", text)
        self.assertIn("--model smollm2:135m", text)

    def test_voice_action_review_lists_confirmation_and_correction_phrases(self) -> None:
        gui = object.__new__(AssistantGui)

        text = gui._voice_action_review_text()

        self.assertIn("GUI voice action review", text)
        self.assertIn("Say 'yes' to confirm", text)
        self.assertIn("Say 'no' to cancel", text)
        self.assertIn("actually <command>", text)
        self.assertIn("I meant <command>", text)

    def test_copy_wake_launch_command_copies_to_clipboard(self) -> None:
        gui = object.__new__(AssistantGui)
        gui.settings = AssistantSettings(model="smollm2:135m", num_gpu=0, voice_timeout=10)
        gui.model_label = "smollm2:135m"
        gui.root = Mock()
        gui._append_assistant = Mock()

        gui._copy_wake_launch_command()

        gui.root.clipboard_clear.assert_called_once()
        copied = gui.root.clipboard_append.call_args.args[0]
        self.assertIn("--wake --speak --voice-timeout 10", copied)
        gui._append_assistant.assert_called_once()

    @patch("assistant.gui.collect_status")
    def test_show_status_appends_status_summary(self, mock_collect_status) -> None:
        gui = object.__new__(AssistantGui)
        gui.settings = object()
        gui._append_assistant = Mock()
        mock_collect_status.return_value.summary.return_value = "Local assistant status"

        gui._show_status()

        mock_collect_status.assert_called_once_with(gui.settings)
        gui._append_assistant.assert_called_once_with("Local assistant status")

    @patch("assistant.gui.save_settings")
    def test_save_settings_panel_values_writes_valid_updates(self, mock_save_settings) -> None:
        gui = object.__new__(AssistantGui)
        gui.settings = AssistantSettings(assistant_name="Eva", use_llm=True)
        gui.settings_path = "config/settings.json"
        gui.status_label = Mock()
        gui._refresh_startup_health = Mock()
        gui._append_assistant = Mock()
        window = Mock()
        variables = {
            "assistant_name": Mock(get=Mock(return_value="Friday")),
            "use_llm": Mock(get=Mock(return_value=False)),
        }

        gui._save_settings_panel_values(window, variables)

        mock_save_settings.assert_called_once()
        self.assertEqual(gui.settings.assistant_name, "Friday")
        self.assertFalse(gui.settings.use_llm)
        window.destroy.assert_called_once()
        gui._append_assistant.assert_called_once()

    @patch("assistant.gui.save_settings")
    def test_save_settings_panel_values_reports_validation_errors(self, mock_save_settings) -> None:
        gui = object.__new__(AssistantGui)
        gui.settings = AssistantSettings()
        gui.settings_path = "config/settings.json"
        gui._append_assistant = Mock()
        window = Mock()
        variables = {"voice_timeout": Mock(get=Mock(return_value="slow"))}

        gui._save_settings_panel_values(window, variables)

        mock_save_settings.assert_not_called()
        window.destroy.assert_not_called()
        self.assertIn("Settings error", gui._append_assistant.call_args.args[0])

    def test_execute_action_uses_assistant_confirmation_method(self) -> None:
        gui = object.__new__(AssistantGui)
        gui.assistant = Mock()
        gui.assistant.confirm_pending_action.return_value = "Done."
        gui.assistant.action_audit_store = Mock()
        gui.queue = Mock()
        action = Mock()

        gui._execute_action_in_background("yes", action)

        gui.assistant.confirm_pending_action.assert_called_once_with(action)

    def test_clear_transcript_clears_widget_and_appends_notice(self) -> None:
        gui = object.__new__(AssistantGui)
        gui.transcript = Mock()
        gui._append_assistant = Mock()

        gui._clear_transcript()

        gui.transcript.configure.assert_any_call(state="normal")
        gui.transcript.delete.assert_called_once_with("1.0", "end")
        gui.transcript.configure.assert_any_call(state="disabled")
        gui._append_assistant.assert_called_once_with("Transcript cleared.")

    def test_refresh_allowlist_tree_replaces_rows(self) -> None:
        tree = Mock()
        tree.get_children.return_value = ("old-row",)

        AssistantGui._refresh_allowlist_tree(tree, {"calculator": "calc.exe"})

        tree.delete.assert_called_once_with("old-row")
        tree.insert.assert_called_once_with("", "end", values=("calculator", "calc.exe"))

    def test_set_text_replaces_widget_content(self) -> None:
        widget = Mock()

        AssistantGui._set_text(widget, "hello")

        widget.configure.assert_any_call(state="normal")
        widget.delete.assert_called_once_with("1.0", "end")
        widget.insert.assert_called_once_with("end", "hello")
        widget.configure.assert_any_call(state="disabled")

    @patch("assistant.gui.build_startup_health_rows")
    def test_refresh_startup_health_updates_panel_labels(self, mock_rows) -> None:
        gui = object.__new__(AssistantGui)
        gui.settings = Mock()
        gui.assistant = Mock()
        gui.model_label = "disabled"
        gui.num_gpu = 0
        label = Mock()
        gui.health_value_labels = {"Assistant": label}
        mock_rows.return_value = [Mock(label="Assistant", value="Eva", ok=True)]

        gui._refresh_startup_health()

        label.configure.assert_called_once_with(text="OK: Eva")

    @patch("assistant.gui.build_startup_health_rows")
    def test_show_startup_health_appends_readable_summary(self, mock_rows) -> None:
        gui = object.__new__(AssistantGui)
        gui.settings = Mock()
        gui.assistant = Mock()
        gui.model_label = "disabled"
        gui.num_gpu = 0
        gui.health_value_labels = {}
        gui._append_assistant = Mock()
        mock_rows.return_value = [
            Mock(label="Assistant", value="Eva", ok=True),
            Mock(label="Voice model", value="missing", ok=False),
        ]

        gui._show_startup_health()

        appended = gui._append_assistant.call_args.args[0]
        self.assertIn("Startup health", appended)
        self.assertIn("Assistant: OK: Eva", appended)
        self.assertIn("Voice model: Check: missing", appended)

    @patch("assistant.gui.build_startup_dashboard", return_value="Startup dashboard")
    @patch("assistant.gui.load_persona", return_value="")
    @patch("assistant.gui.load_settings")
    def test_gui_startup_appends_dashboard(self, mock_settings, mock_persona, mock_dashboard) -> None:
        settings = Mock()
        settings.use_llm = False
        settings.assistant_name = "Eva"
        settings.persona_path = "config/persona.txt"
        settings.memory_path = "data/memory.json"
        settings.notes_path = "data/notes.md"
        settings.tasks_path = "data/tasks.json"
        settings.outbox_path = "data/outbox.json"
        settings.history_path = "data/history.jsonl"
        settings.history_enabled = True
        settings.action_audit_path = "data/action_audit.jsonl"
        settings.action_audit_enabled = False
        settings.voice_action_audit_path = "data/voice_action_audit.jsonl"
        settings.voice_action_audit_enabled = True
        settings.aliases_path = "config/aliases.json"
        settings.voice_model_path = "models/vosk-model-small-en-us-0.15"
        settings.model = "smollm2:135m"
        settings.num_gpu = 0
        mock_settings.return_value = settings

        gui = object.__new__(AssistantGui)
        root = Mock()
        with patch.object(AssistantGui, "_build_ui"), patch.object(AssistantGui, "_append_assistant") as mock_append:
            AssistantGui.__init__(gui, root, "config/settings.json", force_no_llm=True)

        mock_dashboard.assert_called_once()
        mock_append.assert_called_once_with("Startup dashboard")

    def test_set_pending_buttons_enables_confirmation_when_true(self) -> None:
        gui = object.__new__(AssistantGui)
        gui.confirm_button = Mock()
        gui.cancel_button = Mock()

        gui._set_pending_buttons(True)

        gui.confirm_button.configure.assert_called_with(state="normal")
        gui.cancel_button.configure.assert_called_with(state="normal")

    def test_set_pending_buttons_disables_confirmation_when_false(self) -> None:
        gui = object.__new__(AssistantGui)
        gui.confirm_button = Mock()
        gui.cancel_button = Mock()

        gui._set_pending_buttons(False)

        gui.confirm_button.configure.assert_called_with(state="disabled")
        gui.cancel_button.configure.assert_called_with(state="disabled")

    def test_append_assistant_adds_line_to_transcript(self) -> None:
        gui = object.__new__(AssistantGui)
        gui.transcript = Mock()

        gui._append_assistant("Hello, how can I help?")

        gui.transcript.configure.assert_any_call(state="normal")
        gui.transcript.insert.assert_called()
        gui.transcript.configure.assert_any_call(state="disabled")
        gui.transcript.see.assert_called_once()

    def test_append_user_adds_formatted_line_to_transcript(self) -> None:
        gui = object.__new__(AssistantGui)
        gui.transcript = Mock()

        gui._append_user("Hello assistant")

        gui.transcript.configure.assert_any_call(state="normal")
        gui.transcript.insert.assert_called()
        gui.transcript.configure.assert_any_call(state="disabled")

    def test_cancel_action_clears_pending_state(self) -> None:
        gui = object.__new__(AssistantGui)
        action = Mock()
        gui.pending_action = action
        gui.assistant = Mock()
        gui.assistant.action_audit_store = Mock()
        gui._set_pending_buttons = Mock()
        gui._append_assistant = Mock()

        gui._cancel_action()

        self.assertIsNone(gui.pending_action)
        gui._set_pending_buttons.assert_called_once_with(False)
        gui._append_assistant.assert_called_once()

    def test_send_ignores_empty_input(self) -> None:
        gui = object.__new__(AssistantGui)
        gui.input_var = Mock()
        gui.input_var.get.return_value = ""
        gui.assistant = Mock()

        gui._send()

        gui.assistant.respond.assert_not_called()

    def test_execute_action_handles_background_execution(self) -> None:
        gui = object.__new__(AssistantGui)
        gui.assistant = Mock()
        gui.assistant.confirm_pending_action.return_value = "Action completed"
        gui.queue = Mock()
        gui._append_assistant = Mock()
        action = Mock()

        gui._execute_action_in_background("yes", action)

        gui.assistant.confirm_pending_action.assert_called_once()

    def test_menu_builtin_commands_includes_essential_operations(self) -> None:
        commands = AssistantGui._menu_builtin_commands()

        self.assertIn("briefing", commands)
        self.assertIn("settings", commands)
        self.assertIn("safety", commands)
        self.assertIn("memories", commands)
        self.assertIn("tasks", commands)
        self.assertIn("command reference", commands)

    def test_gui_has_toolbar_methods(self) -> None:
        # Verify toolbar method names exist
        self.assertTrue(hasattr(AssistantGui, "_toolbar_list_files"))
        self.assertTrue(hasattr(AssistantGui, "_toolbar_search_files"))
        self.assertTrue(hasattr(AssistantGui, "_toolbar_find_file_names"))
        self.assertTrue(hasattr(AssistantGui, "_toolbar_preview_file"))
        self.assertTrue(hasattr(AssistantGui, "_toolbar_verify_bulk_write_checklist"))
        self.assertTrue(hasattr(AssistantGui, "_toolbar_verify_bulk_restore_checklist"))

    def test_gui_has_voice_methods(self) -> None:
        # Verify voice command methods exist
        self.assertTrue(hasattr(AssistantGui, "_voice_launch_help_text"))
        self.assertTrue(hasattr(AssistantGui, "_voice_action_review_text"))
        self.assertTrue(hasattr(AssistantGui, "_show_voice_launch_help"))
        self.assertTrue(hasattr(AssistantGui, "_copy_wake_launch_command"))

    def test_gui_safety_snapshot_methods_exist(self) -> None:
        # Verify all safety snapshot methods are wired
        self.assertTrue(hasattr(AssistantGui, "_show_safety_snapshot"))
        self.assertTrue(hasattr(AssistantGui, "_show_launch_safety_snapshot"))
        self.assertTrue(hasattr(AssistantGui, "_show_shell_safety_snapshot"))
        self.assertTrue(hasattr(AssistantGui, "_show_script_safety_snapshot"))


if __name__ == "__main__":
    unittest.main()
