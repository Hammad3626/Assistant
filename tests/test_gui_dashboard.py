import unittest
from unittest.mock import Mock

from assistant.gui_dashboard import build_startup_dashboard, build_startup_health_rows
from assistant.settings import AssistantSettings


class GuiDashboardTests(unittest.TestCase):
    def test_dashboard_includes_model_counts_and_commands(self) -> None:
        assistant = Mock()
        assistant.memory_store.list_memories.return_value = [object()]
        assistant.notes_store.list_notes.return_value = [object(), object()]
        assistant.tasks_store.open_tasks.return_value = [object(), object(), object()]
        assistant.tasks_store.list_deleted_tasks.return_value = [object()]
        assistant.outbox_store.list_drafts.return_value = [object(), object()]
        assistant.history_store.recent.return_value = []
        assistant.action_audit_store.recent.return_value = []
        assistant.voice_action_audit_store.recent.return_value = []

        text = build_startup_dashboard(
            AssistantSettings(assistant_name="Eva", voice_model_path="missing-model"),
            assistant,
            "disabled",
            0,
        )

        self.assertIn("Startup dashboard", text)
        self.assertIn("Assistant: Eva", text)
        self.assertIn("Model: disabled", text)
        self.assertIn("- Memories: 1", text)
        self.assertIn("- Notes: 2", text)
        self.assertIn("- Open tasks: 3", text)
        self.assertIn("- Task trash: 1", text)
        self.assertIn("- Outbox drafts: 2", text)
        self.assertIn("Useful commands:", text)

    def test_health_rows_include_startup_counts(self) -> None:
        assistant = Mock()
        assistant.memory_store.list_memories.return_value = [object()]
        assistant.notes_store.list_notes.return_value = [object(), object()]
        assistant.tasks_store.open_tasks.return_value = [object(), object(), object()]
        assistant.tasks_store.list_deleted_tasks.return_value = [object()]
        assistant.outbox_store.list_drafts.return_value = [object(), object()]
        assistant.history_store.recent.return_value = []
        assistant.action_audit_store.recent.return_value = []
        assistant.voice_action_audit_store.recent.return_value = []

        rows = build_startup_health_rows(
            AssistantSettings(assistant_name="Eva", voice_model_path="missing-model"),
            assistant,
            "disabled",
            0,
        )

        values = {row.label: row for row in rows}
        self.assertEqual(values["Assistant"].value, "Eva")
        self.assertEqual(values["Model"].value, "disabled")
        self.assertEqual(values["Open tasks"].value, "3")
        self.assertEqual(values["Task trash"].value, "1")
        self.assertEqual(values["Outbox"].value, "2")
        self.assertFalse(values["Voice model"].ok)

    def test_dashboard_reports_count_errors(self) -> None:
        assistant = Mock()
        assistant.memory_store.list_memories.side_effect = RuntimeError("bad memory")
        assistant.notes_store.list_notes.return_value = []
        assistant.tasks_store.open_tasks.return_value = []
        assistant.tasks_store.list_deleted_tasks.return_value = []
        assistant.outbox_store.list_drafts.return_value = []
        assistant.history_store.recent.return_value = []
        assistant.action_audit_store.recent.return_value = []
        assistant.voice_action_audit_store.recent.return_value = []

        text = build_startup_dashboard(AssistantSettings(), assistant, "disabled", 0)

        self.assertIn("Memories: error: bad memory", text)

    def test_health_rows_report_count_errors(self) -> None:
        assistant = Mock()
        assistant.memory_store.list_memories.side_effect = RuntimeError("bad memory")
        assistant.notes_store.list_notes.return_value = []
        assistant.tasks_store.open_tasks.return_value = []
        assistant.tasks_store.list_deleted_tasks.return_value = []
        assistant.outbox_store.list_drafts.return_value = []
        assistant.history_store.recent.return_value = []
        assistant.action_audit_store.recent.return_value = []
        assistant.voice_action_audit_store.recent.return_value = []

        rows = build_startup_health_rows(AssistantSettings(), assistant, "disabled", 0)

        values = {row.label: row for row in rows}
        self.assertEqual(values["Memories"].value, "error: bad memory")
        self.assertFalse(values["Memories"].ok)

    def test_dashboard_includes_voice_model_status(self) -> None:
        assistant = Mock()
        assistant.memory_store.list_memories.return_value = []
        assistant.notes_store.list_notes.return_value = []
        assistant.tasks_store.open_tasks.return_value = []
        assistant.tasks_store.list_deleted_tasks.return_value = []
        assistant.outbox_store.list_drafts.return_value = []
        assistant.history_store.recent.return_value = []
        assistant.action_audit_store.recent.return_value = []
        assistant.voice_action_audit_store.recent.return_value = []

        text = build_startup_dashboard(
            AssistantSettings(voice_model_path="models/vosk-model-small-en-us-0.15"),
            assistant,
            "smollm2:135m",
            0,
        )

        self.assertIn("Voice model:", text)

    def test_health_rows_report_llm_model_when_enabled(self) -> None:
        assistant = Mock()
        assistant.memory_store.list_memories.return_value = []
        assistant.notes_store.list_notes.return_value = []
        assistant.tasks_store.open_tasks.return_value = []
        assistant.tasks_store.list_deleted_tasks.return_value = []
        assistant.outbox_store.list_drafts.return_value = []
        assistant.history_store.recent.return_value = []
        assistant.action_audit_store.recent.return_value = []
        assistant.voice_action_audit_store.recent.return_value = []

        rows = build_startup_health_rows(
            AssistantSettings(assistant_name="Thursday", use_llm=True),
            assistant,
            "llama2:7b",
            1,
        )

        values = {row.label: row for row in rows}
        self.assertEqual(values["Model"].value, "llama2:7b")

    def test_health_rows_include_ok_status_for_valid_configuration(self) -> None:
        assistant = Mock()
        assistant.memory_store.list_memories.return_value = [object()]
        assistant.notes_store.list_notes.return_value = []
        assistant.tasks_store.open_tasks.return_value = []
        assistant.tasks_store.list_deleted_tasks.return_value = []
        assistant.outbox_store.list_drafts.return_value = []
        assistant.history_store.recent.return_value = []
        assistant.action_audit_store.recent.return_value = []
        assistant.voice_action_audit_store.recent.return_value = []

        rows = build_startup_health_rows(
            AssistantSettings(assistant_name="Alice"),
            assistant,
            "disabled",
            0,
        )

        values = {row.label: row for row in rows}
        self.assertTrue(values["Assistant"].ok)
        self.assertTrue(values["Memories"].ok)

    def test_dashboard_includes_useful_commands_section(self) -> None:
        assistant = Mock()
        assistant.memory_store.list_memories.return_value = []
        assistant.notes_store.list_notes.return_value = []
        assistant.tasks_store.open_tasks.return_value = []
        assistant.tasks_store.list_deleted_tasks.return_value = []
        assistant.outbox_store.list_drafts.return_value = []
        assistant.history_store.recent.return_value = []
        assistant.action_audit_store.recent.return_value = []
        assistant.voice_action_audit_store.recent.return_value = []

        text = build_startup_dashboard(AssistantSettings(), assistant, "disabled", 0)

        self.assertIn("useful commands", text.lower())
        self.assertIn("status", text.lower())
        self.assertIn("safety", text.lower())
        self.assertIn("roadmap", text.lower())


if __name__ == "__main__":
    unittest.main()
