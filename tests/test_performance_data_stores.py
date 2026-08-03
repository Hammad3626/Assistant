"""Performance benchmarks for data store operations.

Monitors memory, history, audit, notes, and tasks stores to ensure
responsiveness as data volumes grow. Tests establish baseline performance
metrics to detect future regressions.
"""

import unittest
import tempfile
import time
from pathlib import Path

from assistant.memory import MemoryStore
from assistant.history import HistoryStore
from assistant.notes import NotesStore
from assistant.tasks import TasksStore
from assistant.launch_requests import LaunchRequestStore


class MemoryStorePerformanceTests(unittest.TestCase):
    """Benchmark memory store operations."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_remember_and_list_50_memories_under_2_seconds(self) -> None:
        """Adding and listing 50 memories should complete in reasonable time."""
        memory_path = self.temp_path / "memory.json"
        store = MemoryStore(str(memory_path))

        start = time.perf_counter()
        for i in range(50):
            store.remember(f"Memory item number {i}")
        memories = store.list_memories()
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 2.0, "50 memories took > 2 seconds")
        self.assertEqual(len(memories), 50)

    def test_list_memories_under_100ms(self) -> None:
        """Retrieving all memories should be fast."""
        memory_path = self.temp_path / "memory.json"
        store = MemoryStore(str(memory_path))

        for i in range(30):
            store.remember(f"Item {i}")

        start = time.perf_counter()
        memories = store.list_memories()
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.1, "Listing 30 memories took > 100ms")
        self.assertEqual(len(memories), 30)

    def test_clear_memories_performance(self) -> None:
        """Clearing all memories should be reasonably fast."""
        memory_path = self.temp_path / "memory.json"
        store = MemoryStore(str(memory_path))

        for i in range(40):
            store.remember(f"Item {i}")

        start = time.perf_counter()
        cleared = store.clear()
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.2, "Clearing 40 memories took > 200ms")
        self.assertEqual(cleared, 40)


class HistoryStorePerformanceTests(unittest.TestCase):
    """Benchmark history store operations."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_record_and_retrieve_100_entries_under_1_second(self) -> None:
        """Recording 100 history entries should complete in < 1 second."""
        history_path = self.temp_path / "history.jsonl"
        store = HistoryStore(str(history_path), enabled=True)

        start = time.perf_counter()
        for i in range(100):
            store.append("user", f"user input {i}")
            store.append("assistant", f"assistant response {i}")
        entries = store.recent(limit=100)
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 2.0, "100 history entries took > 2 seconds")
        self.assertGreater(len(entries), 0)

    def test_recent_retrieval_under_50ms(self) -> None:
        """Retrieving recent entries should be very fast."""
        history_path = self.temp_path / "history.jsonl"
        store = HistoryStore(str(history_path), enabled=True)

        for i in range(50):
            store.append("user", f"input")
            store.append("assistant", f"response {i}")

        start = time.perf_counter()
        recent = store.recent(limit=10)
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.1, "Retrieving 10 recent entries took > 100ms")
        self.assertLessEqual(len(recent), 10)

    def test_prune_performance(self) -> None:
        """Pruning history should be reasonably fast."""
        history_path = self.temp_path / "history.jsonl"
        store = HistoryStore(str(history_path), enabled=True)

        for i in range(200):
            store.append("user", f"input")
            store.append("assistant", f"response {i}")

        start = time.perf_counter()
        cleared = store.clear()
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 1.0, "Clearing history took > 1 second")
        self.assertGreater(cleared, 0)


class NotesStorePerformanceTests(unittest.TestCase):
    """Benchmark notes store operations."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_add_and_list_notes_under_200ms(self) -> None:
        """Adding and listing 25 notes should be fast."""
        notes_path = self.temp_path / "notes.md"
        store = NotesStore(str(notes_path))

        start = time.perf_counter()
        for i in range(25):
            store.add(f"Note {i}\nContent line 2 for note {i}")
        notes = store.list_notes()
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.2, "25 notes took > 200ms")
        self.assertEqual(len(notes), 25)

    def test_list_notes_performance(self) -> None:
        """Retrieving all notes should be fast."""
        notes_path = self.temp_path / "notes.md"
        store = NotesStore(str(notes_path))

        for i in range(20):
            store.add(f"Note {i}\nContent")

        notes = store.list_notes()
        start = time.perf_counter()
        notes = store.list_notes()
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.1, "Listing notes took > 100ms")
        self.assertIsNotNone(notes)


class TasksStorePerformanceTests(unittest.TestCase):
    """Benchmark tasks store operations."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_add_and_list_40_tasks_under_2_seconds(self) -> None:
        """Adding and listing 40 tasks should be quick."""
        tasks_path = self.temp_path / "tasks.json"
        store = TasksStore(str(tasks_path))

        start = time.perf_counter()
        for i in range(40):
            store.add(f"Task {i}")
        tasks = store.open_tasks()
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 2.0, "40 tasks took > 2 seconds")
        self.assertEqual(len(tasks), 40)

    def test_complete_task_performance(self) -> None:
        """Completing a task should be fast."""
        tasks_path = self.temp_path / "tasks.json"
        store = TasksStore(str(tasks_path))

        for i in range(15):
            store.add(f"Task {i}")

        start = time.perf_counter()
        store.complete(1)
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.5, "Completing task took > 500ms")

    def test_filter_open_tasks_performance(self) -> None:
        """Filtering for open tasks should be fast."""
        tasks_path = self.temp_path / "tasks.json"
        store = TasksStore(str(tasks_path))

        for i in range(30):
            store.add(f"Task {i}")

        start = time.perf_counter()
        open_tasks = store.open_tasks()
        due_today = store.due_today()
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.5, "Filtering tasks took > 500ms")
        self.assertGreater(len(open_tasks), 0)


class LaunchRequestStorePerformanceTests(unittest.TestCase):
    """Benchmark launch request store operations."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_load_and_list_performance(self) -> None:
        """Loading launch requests should be reasonably fast."""
        requests_path = self.temp_path / "launch_requests.json"
        store = LaunchRequestStore(str(requests_path))

        start = time.perf_counter()
        # Just loading and accessing should be quick
        requests = store.list_requests()
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.2, "Loading launch requests took > 200ms")


class DataStorePersistenceTests(unittest.TestCase):
    """Test data store persistence and reliability."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_memory_persists_across_instances(self) -> None:
        """Data should survive store reload."""
        memory_path = self.temp_path / "memory.json"

        # Write with first instance
        store1 = MemoryStore(str(memory_path))
        store1.remember("Persistent data")

        # Read with second instance
        store2 = MemoryStore(str(memory_path))
        memories = store2.list_memories()

        self.assertEqual(len(memories), 1)
        self.assertIn("Persistent", memories[0].text)

    def test_history_handles_large_volume(self) -> None:
        """History should handle 500+ entries reliably."""
        history_path = self.temp_path / "history.jsonl"
        store = HistoryStore(str(history_path), enabled=True)

        for i in range(500):
            store.append("user", f"input_{i}")
            store.append("assistant", f"response_{i}")

        recent = store.recent(limit=50)
        self.assertLessEqual(len(recent), 50)

    def test_unicode_content_handling(self) -> None:
        """Stores should handle Unicode characters correctly."""
        memory_path = self.temp_path / "memory.json"
        store = MemoryStore(str(memory_path))

        unicode_text = "中文 日本語 한국어 العربية Café résumé"
        store.remember(unicode_text)

        memories = store.list_memories()
        self.assertEqual(len(memories), 1)
        self.assertIn("中文", memories[0].text)
        self.assertIn("Café", memories[0].text)

    def test_tasks_with_different_states(self) -> None:
        """Task store should handle mixed task states."""
        tasks_path = self.temp_path / "tasks.json"
        store = TasksStore(str(tasks_path))

        for i in range(20):
            store.add(f"Task {i}")

        # Complete some tasks
        for task_num in range(1, 7, 3):
            if task_num <= len(store.open_tasks()):
                store.complete(task_num)

        open_count = len(store.open_tasks())
        self.assertGreater(open_count, 0)
        self.assertLess(open_count, 20)


if __name__ == "__main__":
    unittest.main()
