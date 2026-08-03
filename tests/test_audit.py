import tempfile
import unittest
from pathlib import Path

from assistant.actions import PendingAction
from assistant.audit import ActionAuditStore


class ActionAuditTests(unittest.TestCase):
    def test_missing_audit_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ActionAuditStore(Path(temp_dir) / "audit.jsonl")

            self.assertEqual(store.recent(), [])
            self.assertEqual(store.summary(), "No saved action audit entries.")

    def test_record_and_recent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ActionAuditStore(Path(temp_dir) / "audit.jsonl")
            action = PendingAction("app", "calc.exe", "Open calculator")

            store.record(action, status="confirmed", requested_by="yes", result="Done.")
            entries = store.recent()

        self.assertEqual(entries[0].status, "confirmed")
        self.assertEqual(entries[0].description, "Open calculator")

    def test_disabled_audit_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "audit.jsonl"
            store = ActionAuditStore(path, enabled=False)
            action = PendingAction("app", "calc.exe", "Open calculator")

            store.record(action, status="confirmed", requested_by="yes", result="Done.")

            self.assertFalse(path.exists())

    def test_clear_returns_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ActionAuditStore(Path(temp_dir) / "audit.jsonl")
            action = PendingAction("app", "calc.exe", "Open calculator")
            store.record(action, status="confirmed", requested_by="yes", result="Done.")

            count = store.clear()

            self.assertEqual(count, 1)
            self.assertEqual(store.recent(), [])


if __name__ == "__main__":
    unittest.main()

