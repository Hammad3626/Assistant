import tempfile
import unittest
from datetime import date
from pathlib import Path

from assistant.tasks import TasksError, TasksStore, parse_task_text


class TasksTests(unittest.TestCase):
    def test_missing_tasks_are_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")

            self.assertEqual(store.list_tasks(), [])
            self.assertEqual(store.summary(), "No open tasks.")

    def test_add_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")

            task = store.add("  call dentist  ")
            open_tasks = store.open_tasks()

        self.assertEqual(task.text, "call dentist")
        self.assertEqual(open_tasks[0].text, "call dentist")

    def test_add_task_with_due_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")

            task = store.add("call dentist due 2026-07-05")
            summary = store.summary()

        self.assertEqual(task.text, "call dentist")
        self.assertEqual(task.due_date, "2026-07-05")
        self.assertIn("call dentist (due 2026-07-05)", summary)

    def test_complete_task_marks_open_task_done(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")
            store.add("first")
            store.add("second")

            completed = store.complete(1)

        self.assertEqual(completed.text, "first")
        self.assertTrue(completed.completed)

    def test_completed_and_all_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")
            store.add("first")
            store.add("second due 2026-07-05")
            store.complete(1)

            completed_summary = store.completed_summary()
            all_summary = store.all_summary()

        self.assertIn("Completed tasks:", completed_summary)
        self.assertIn("first", completed_summary)
        self.assertIn("[done] first", all_summary)
        self.assertIn("[open] second (due 2026-07-05)", all_summary)

    def test_complete_task_preserves_due_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")
            store.add("call dentist due 2026-07-05")

            completed = store.complete(1)

        self.assertEqual(completed.due_date, "2026-07-05")

    def test_invalid_task_number_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")

            with self.assertRaises(TasksError):
                store.complete(1)

    def test_parse_task_text_rejects_bad_due_date(self) -> None:
        with self.assertRaises(TasksError):
            parse_task_text("call dentist due tomorrow")

    def test_due_date_views_classify_open_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")
            store.add("past due 2026-07-01")
            store.add("today due 2026-07-02")
            store.add("future due 2026-07-03")
            store.add("undated task")

            overdue = store.overdue(date(2026, 7, 2))
            due_today = store.due_today(date(2026, 7, 2))
            upcoming = store.upcoming(date(2026, 7, 2))

        self.assertEqual([task.text for task in overdue], ["past"])
        self.assertEqual([task.text for task in due_today], ["today"])
        self.assertEqual([task.text for task in upcoming], ["today", "future"])

    def test_due_summary_handles_empty_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")

            summary = store.due_summary("Overdue", [])

        self.assertEqual(summary, "No overdue tasks.")

    def test_due_soon_filters_next_seven_days(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")
            store.add("today due 2026-07-02")
            store.add("soon due 2026-07-09")
            store.add("later due 2026-07-10")

            due_soon = store.due_soon(date(2026, 7, 2))

        self.assertEqual([task.text for task in due_soon], ["today", "soon"])

    def test_task_stats_counts_open_completed_and_due_dates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")
            store.add("first due 2026-07-05")
            store.add("second")
            store.complete(2)

            summary = store.stats_summary()

        self.assertIn("Total tasks: 2", summary)
        self.assertIn("Open tasks: 1", summary)
        self.assertIn("Completed tasks: 1", summary)
        self.assertIn("Open with due dates: 1", summary)

    def test_rename_open_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")
            store.add("old task due 2026-07-05")

            updated = store.rename(1, "new task")

        self.assertEqual(updated.text, "new task")
        self.assertEqual(updated.due_date, "2026-07-05")

    def test_set_and_clear_due_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")
            store.add("call dentist")

            dated = store.set_due_date(1, "2026-07-05")
            cleared = store.set_due_date(1, None)

        self.assertEqual(dated.due_date, "2026-07-05")
        self.assertIsNone(cleared.due_date)

    def test_delete_open_task_removes_only_selected_open_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")
            store.add("first")
            store.add("second")

            deleted = store.delete_open(1)
            remaining = store.open_tasks()
            deleted_tasks = store.list_deleted_tasks()

        self.assertEqual(deleted.text, "first")
        self.assertEqual([task.text for task in remaining], ["second"])
        self.assertEqual([task.text for task in deleted_tasks], ["first"])

    def test_deleted_summary_and_restore_deleted_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")
            store.add("first due 2026-07-05")
            store.delete_open(1)

            summary = store.deleted_summary()
            restored = store.restore_deleted(1)

        self.assertIn("Task trash:", summary)
        self.assertIn("first (due 2026-07-05)", summary)
        self.assertEqual(restored.text, "first")
        self.assertEqual(restored.due_date, "2026-07-05")

    def test_restore_completed_task_reopens_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TasksStore(Path(temp_dir) / "tasks.json")
            store.add("first due 2026-07-05")
            store.complete(1)

            restored = store.restore_completed(1)

        self.assertEqual(restored.text, "first")
        self.assertEqual(restored.due_date, "2026-07-05")
        self.assertFalse(restored.completed)


if __name__ == "__main__":
    unittest.main()
