import tempfile
import unittest
from pathlib import Path

from assistant.actions import PendingAction
from assistant.audit import ActionAuditStore
from assistant.data_tools import (
    build_report,
    build_report_from_stores,
    backups_summary,
    clear_data,
    export_data,
    export_data_from_stores,
    list_backups,
)
from assistant.history import HistoryStore
from assistant.memory import MemoryStore
from assistant.notes import NotesStore
from assistant.outbox import OutboxStore
from assistant.settings import AssistantSettings
from assistant.tasks import TasksStore


class DataToolsTests(unittest.TestCase):
    def test_build_report_counts_memory_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            memory_path = Path(temp_dir) / "memory.json"
            notes_path = Path(temp_dir) / "notes.md"
            tasks_path = Path(temp_dir) / "tasks.json"
            history_path = Path(temp_dir) / "history.jsonl"
            audit_path = Path(temp_dir) / "audit.jsonl"
            outbox_path = Path(temp_dir) / "outbox.json"
            MemoryStore(memory_path).remember("one")
            NotesStore(notes_path).add("note one")
            TasksStore(tasks_path).add("task one")
            TasksStore(tasks_path).add("task two")
            TasksStore(tasks_path).delete_open(2)
            OutboxStore(outbox_path).draft_message("Alex", "hello")
            HistoryStore(history_path).append("user", "hello")
            ActionAuditStore(audit_path).record(
                PendingAction("app", "calc.exe", "Open calculator"),
                status="cancelled",
                requested_by="no",
                result="Cancelled.",
            )
            settings = AssistantSettings(
                memory_path=str(memory_path),
                notes_path=str(notes_path),
                tasks_path=str(tasks_path),
                outbox_path=str(outbox_path),
                history_path=str(history_path),
                action_audit_path=str(audit_path),
            )

            report = build_report(settings)

        self.assertEqual(report.memory_count, 1)
        self.assertEqual(report.notes_count, 1)
        self.assertEqual(report.open_tasks_count, 1)
        self.assertEqual(report.deleted_tasks_count, 1)
        self.assertEqual(report.outbox_count, 1)
        self.assertEqual(report.history_count, 1)
        self.assertEqual(report.action_audit_count, 1)
        self.assertIn("Task trash: 1 item(s)", report.summary())

    def test_build_report_from_live_stores(self) -> None:
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
            history_store.append("user", "hello")

            report = build_report_from_stores(
                memory_store,
                notes_store,
                tasks_store,
                outbox_store,
                history_store,
                audit_store,
            )

        self.assertEqual(report.memory_count, 1)
        self.assertEqual(report.notes_count, 1)
        self.assertEqual(report.open_tasks_count, 1)
        self.assertEqual(report.deleted_tasks_count, 1)
        self.assertEqual(report.outbox_count, 1)
        self.assertEqual(report.history_count, 1)
        self.assertIn("memory.json", report.memory_path)

    def test_export_data_copies_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            memory_path = root / "memory.json"
            notes_path = root / "notes.md"
            tasks_path = root / "tasks.json"
            history_path = root / "history.jsonl"
            audit_path = root / "audit.jsonl"
            outbox_path = root / "outbox.json"
            MemoryStore(memory_path).remember("one")
            NotesStore(notes_path).add("note one")
            TasksStore(tasks_path).add("task one")
            OutboxStore(outbox_path).draft_message("Alex", "hello")
            HistoryStore(history_path).append("user", "hello")
            ActionAuditStore(audit_path).record(
                PendingAction("app", "calc.exe", "Open calculator"),
                status="cancelled",
                requested_by="no",
                result="Cancelled.",
            )
            settings = AssistantSettings(
                memory_path=str(memory_path),
                notes_path=str(notes_path),
                tasks_path=str(tasks_path),
                outbox_path=str(outbox_path),
                history_path=str(history_path),
                action_audit_path=str(audit_path),
            )

            export_dir = export_data(settings, root / "exports")

            self.assertTrue((export_dir / "memory.json").exists())
            self.assertTrue((export_dir / "notes.md").exists())
            self.assertTrue((export_dir / "tasks.json").exists())
            self.assertTrue((export_dir / "outbox.json").exists())
            self.assertTrue((export_dir / "history.jsonl").exists())
            self.assertTrue((export_dir / "action_audit.jsonl").exists())
            self.assertTrue((export_dir / "report.json").exists())

    def test_export_data_from_live_stores(self) -> None:
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
            outbox_store.draft_message("Alex", "hello")

            export_dir = export_data_from_stores(
                memory_store,
                notes_store,
                tasks_store,
                outbox_store,
                history_store,
                audit_store,
                output_dir=root / "exports",
            )

            self.assertTrue((export_dir / "memory.json").exists())
            self.assertTrue((export_dir / "notes.md").exists())
            self.assertTrue((export_dir / "tasks.json").exists())
            self.assertTrue((export_dir / "outbox.json").exists())
            self.assertTrue((export_dir / "report.json").exists())

    def test_list_backups_returns_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "assistant-data-20260702-010000").mkdir()
            (root / "assistant-data-20260702-020000").mkdir()
            (root / "not-a-backup").mkdir()

            backups = list_backups(root)

        self.assertEqual(
            [backup.name for backup in backups],
            ["assistant-data-20260702-020000", "assistant-data-20260702-010000"],
        )

    def test_backups_summary_handles_empty_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = backups_summary(Path(temp_dir) / "exports")

        self.assertIn("No local backups found", summary)

    def test_clear_data_only_clears_selected_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            memory_path = Path(temp_dir) / "memory.json"
            notes_path = Path(temp_dir) / "notes.md"
            tasks_path = Path(temp_dir) / "tasks.json"
            history_path = Path(temp_dir) / "history.jsonl"
            audit_path = Path(temp_dir) / "audit.jsonl"
            outbox_path = Path(temp_dir) / "outbox.json"
            MemoryStore(memory_path).remember("one")
            NotesStore(notes_path).add("note one")
            TasksStore(tasks_path).add("task one")
            OutboxStore(outbox_path).draft_message("Alex", "hello")
            HistoryStore(history_path).append("user", "hello")
            ActionAuditStore(audit_path).record(
                PendingAction("app", "calc.exe", "Open calculator"),
                status="cancelled",
                requested_by="no",
                result="Cancelled.",
            )
            settings = AssistantSettings(
                memory_path=str(memory_path),
                notes_path=str(notes_path),
                tasks_path=str(tasks_path),
                outbox_path=str(outbox_path),
                history_path=str(history_path),
                action_audit_path=str(audit_path),
            )

            report = clear_data(settings, clear_memory=True, clear_history=False)

            self.assertEqual(report.memory_count, 0)
            self.assertEqual(report.notes_count, 1)
            self.assertEqual(report.open_tasks_count, 1)
            self.assertEqual(report.outbox_count, 1)
            self.assertEqual(report.history_count, 1)
            self.assertEqual(report.action_audit_count, 1)


if __name__ == "__main__":
    unittest.main()
