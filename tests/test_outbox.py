import tempfile
import unittest
from pathlib import Path

from assistant.outbox import OutboxError, OutboxStore, blocked_send_text


class OutboxTests(unittest.TestCase):
    def test_drafts_are_saved_and_listed_locally(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = OutboxStore(Path(temp_dir) / "outbox.json")

            store.draft_message("Alex", "running late")
            store.draft_email("alex@example.com", "Hello", "quick note")
            store.draft_network_request("GET", "https://example.com", "health check")
            summary = store.summary()

        self.assertIn("Outbox drafts (local only, not sent):", summary)
        self.assertIn("message to Alex: running late", summary)
        self.assertIn("email to alex@example.com subject 'Hello'", summary)
        self.assertIn("network request GET https://example.com", summary)

    def test_invalid_network_request_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = OutboxStore(Path(temp_dir) / "outbox.json")

            with self.assertRaises(OutboxError):
                store.draft_network_request("DELETE", "https://example.com")

            with self.assertRaises(OutboxError):
                store.draft_network_request("GET", "not-a-url")

    def test_clear_removes_local_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = OutboxStore(Path(temp_dir) / "outbox.json")
            store.draft_message("Alex", "hello")

            count = store.clear()

        self.assertEqual(count, 1)
        self.assertEqual(store.summary(), "Outbox drafts: none. Nothing has been sent.")

    def test_blocked_send_text_points_to_drafts(self) -> None:
        text = blocked_send_text()

        self.assertIn("Sending is not enabled", text)
        self.assertIn("draft message", text)


if __name__ == "__main__":
    unittest.main()
