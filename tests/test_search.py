import tempfile
import unittest
from pathlib import Path

from assistant.history import HistoryStore
from assistant.memory import MemoryStore
from assistant.notes import NotesStore
from assistant.search import LocalSearch, LocalSearchError
from assistant.tasks import TasksStore


class LocalSearchTests(unittest.TestCase):
    def test_search_finds_memory_note_task_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            memory_store = MemoryStore(root / "memory.json")
            notes_store = NotesStore(root / "notes.md")
            tasks_store = TasksStore(root / "tasks.json")
            history_store = HistoryStore(root / "history.jsonl")
            memory_store.remember("I prefer quiet notifications")
            notes_store.add("buy quiet keyboard")
            tasks_store.add("replace quiet fan due 2099-07-05")
            history_store.append("user", "quiet mode please")

            search = LocalSearch(memory_store, notes_store, tasks_store, history_store)
            results = search.search("quiet")

        self.assertEqual(
            [result.source for result in results],
            ["memory", "note", "task", "history"],
        )
        self.assertIn("[open] replace quiet fan", results[2].text)

    def test_empty_query_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            search = LocalSearch(
                MemoryStore(root / "memory.json"),
                NotesStore(root / "notes.md"),
                TasksStore(root / "tasks.json"),
                HistoryStore(root / "history.jsonl"),
            )

            with self.assertRaises(LocalSearchError):
                search.search("   ")


if __name__ == "__main__":
    unittest.main()
