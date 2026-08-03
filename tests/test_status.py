import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assistant.audit import ActionAuditStore
from assistant.history import HistoryStore
from assistant.memory import MemoryStore
from assistant.notes import NotesStore
from assistant.outbox import OutboxStore
from assistant.settings import AssistantSettings
from assistant.status import collect_status, collect_status_from_stores
from assistant.tasks import TasksStore


class StatusTests(unittest.TestCase):
    @patch("assistant.status._ollama_status", return_value=(True, ["smollm2:135m"]))
    @patch("assistant.status.load_allowed_folders", return_value={"downloads": "C:/Users/Test/Downloads"})
    @patch("assistant.status.load_allowed_apps", return_value={"calculator": "calc.exe"})
    @patch("assistant.status.build_report")
    def test_collect_status_summarizes_local_state(
        self,
        mock_report,
        mock_apps,
        mock_folders,
        mock_ollama,
    ) -> None:
        mock_report.return_value.memory_count = 1
        mock_report.return_value.notes_count = 4
        mock_report.return_value.open_tasks_count = 5
        mock_report.return_value.deleted_tasks_count = 6
        mock_report.return_value.outbox_count = 7
        mock_report.return_value.history_count = 2
        mock_report.return_value.action_audit_count = 3

        status = collect_status(AssistantSettings(assistant_name="Eva"))

        self.assertEqual(status.assistant_name, "Eva")
        self.assertTrue(status.ollama_reachable)
        self.assertEqual(status.app_count, 1)
        self.assertEqual(status.folder_count, 1)
        self.assertEqual(status.notes_count, 4)
        self.assertEqual(status.open_tasks_count, 5)
        self.assertEqual(status.deleted_tasks_count, 6)
        self.assertEqual(status.outbox_count, 7)
        self.assertIn("Task trash entries: 6", status.summary())
        self.assertIn("Outbox drafts: 7", status.summary())
        self.assertIn("Local assistant status", status.summary())

    @patch("assistant.status._ollama_status", return_value=(False, []))
    @patch("assistant.status.load_allowed_folders", return_value={"downloads": "C:/Users/Test/Downloads"})
    @patch("assistant.status.load_allowed_apps", return_value={"calculator": "calc.exe"})
    def test_collect_status_from_live_stores(
        self,
        mock_apps,
        mock_folders,
        mock_ollama,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            memory_store = MemoryStore(root / "memory.json")
            notes_store = NotesStore(root / "notes.md")
            tasks_store = TasksStore(root / "tasks.json")
            history_store = HistoryStore(root / "history.jsonl")
            audit_store = ActionAuditStore(root / "audit.jsonl")
            outbox_store = OutboxStore(root / "outbox.json")
            memory_store.remember("one")
            notes_store.add("note one")
            tasks_store.add("task one")
            tasks_store.add("task two")
            tasks_store.delete_open(2)
            outbox_store.draft_message("Alex", "hello")

            status = collect_status_from_stores(
                assistant_name="Eva",
                model="disabled",
                use_llm=False,
                memory_store=memory_store,
                notes_store=notes_store,
                tasks_store=tasks_store,
                outbox_store=outbox_store,
                history_store=history_store,
                action_audit_store=audit_store,
            )

        self.assertEqual(status.assistant_name, "Eva")
        self.assertFalse(status.use_llm)
        self.assertEqual(status.memory_count, 1)
        self.assertEqual(status.notes_count, 1)
        self.assertEqual(status.open_tasks_count, 1)
        self.assertEqual(status.deleted_tasks_count, 1)
        self.assertEqual(status.outbox_count, 1)


if __name__ == "__main__":
    unittest.main()
