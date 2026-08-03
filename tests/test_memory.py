import tempfile
import unittest
from pathlib import Path

from assistant.memory import MemoryError, MemoryStore


class MemoryTests(unittest.TestCase):
    def test_missing_memory_starts_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.json")

            self.assertEqual(store.list_memories(), [])
            self.assertEqual(store.summary(), "No saved memories.")

    def test_remember_and_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.json")

            item = store.remember("I prefer short answers")
            memories = store.list_memories()

        self.assertEqual(item.text, "I prefer short answers")
        self.assertEqual(memories[0].text, "I prefer short answers")

    def test_clear_returns_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.json")
            store.remember("one")
            store.remember("two")

            count = store.clear()

            self.assertEqual(count, 2)
            self.assertEqual(store.list_memories(), [])

    def test_empty_memory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.json")

            with self.assertRaises(MemoryError):
                store.remember("   ")

    def test_rename_memory_updates_one_item(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.json")
            store.remember("old preference")

            renamed = store.rename(1, "new preference")
            memories = store.list_memories()

        self.assertEqual(renamed.text, "new preference")
        self.assertEqual(memories[0].text, "new preference")

    def test_delete_memory_moves_to_trash_and_restore_returns_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.json")
            store.remember("keep tea stocked")

            deleted = store.delete(1)
            trash_text = store.deleted_summary()
            restored = store.restore_deleted(1)
            memories = store.list_memories()

        self.assertEqual(deleted.text, "keep tea stocked")
        self.assertIn("Memory trash:", trash_text)
        self.assertEqual(restored.text, "keep tea stocked")
        self.assertEqual(memories[0].text, "keep tea stocked")


if __name__ == "__main__":
    unittest.main()
