import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from assistant.briefing import build_briefing
from assistant.memory import MemoryStore
from assistant.notes import NotesStore
from assistant.tasks import TasksStore


class BriefingTests(unittest.TestCase):
    def test_build_briefing_summarizes_local_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            memory_store = MemoryStore(root / "memory.json")
            notes_store = NotesStore(root / "notes.md")
            tasks_store = TasksStore(root / "tasks.json")
            memory_store.remember("I prefer short answers")
            notes_store.add("buy tea")
            tasks_store.add("call dentist due 2026-07-05")
            tasks_store.add("renew license due 2026-06-30")

            briefing = build_briefing(
                memory_store,
                notes_store,
                tasks_store,
                now=datetime(2026, 7, 2, 9, 5),
            )

        text = briefing.summary()
        self.assertIn("Saved memories: 1", text)
        self.assertIn("call dentist (due 2026-07-05)", text)
        self.assertIn("Overdue tasks:", text)
        self.assertIn("renew license (due 2026-06-30)", text)
        self.assertIn("Due soon tasks:", text)
        self.assertIn("buy tea", text)

    def test_empty_briefing_is_clear(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            briefing = build_briefing(
                MemoryStore(root / "memory.json"),
                NotesStore(root / "notes.md"),
                TasksStore(root / "tasks.json"),
                now=datetime(2026, 7, 2, 9, 5),
            )

        text = briefing.summary()
        self.assertIn("Open tasks: none", text)
        self.assertIn("Overdue tasks: none", text)
        self.assertIn("Due soon tasks: none", text)
        self.assertIn("Recent notes: none", text)


if __name__ == "__main__":
    unittest.main()
