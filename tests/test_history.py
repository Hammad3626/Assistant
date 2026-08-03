import tempfile
import unittest
from pathlib import Path

from assistant.history import HistoryStore


class HistoryTests(unittest.TestCase):
    def test_missing_history_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = HistoryStore(Path(temp_dir) / "history.jsonl")

            self.assertEqual(store.recent(), [])
            self.assertEqual(store.summary(), "No saved conversation history.")

    def test_append_and_recent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = HistoryStore(Path(temp_dir) / "history.jsonl")
            store.append("user", "hello")
            store.append("assistant", "hi")

            entries = store.recent(limit=2)

        self.assertEqual(entries[0].role, "user")
        self.assertEqual(entries[0].text, "hello")
        self.assertEqual(entries[1].role, "assistant")

    def test_disabled_history_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "history.jsonl"
            store = HistoryStore(path, enabled=False)
            store.append("user", "hello")

            self.assertFalse(path.exists())

    def test_clear_returns_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = HistoryStore(Path(temp_dir) / "history.jsonl")
            store.append("user", "one")
            store.append("assistant", "two")

            count = store.clear()

            self.assertEqual(count, 2)
            self.assertEqual(store.recent(), [])


if __name__ == "__main__":
    unittest.main()
