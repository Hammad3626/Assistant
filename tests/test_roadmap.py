import unittest

from assistant.roadmap import roadmap_text


class RoadmapTests(unittest.TestCase):
    def test_roadmap_lists_current_and_future_work(self) -> None:
        text = roadmap_text("Eva")

        self.assertIn("Eva roadmap", text)
        self.assertIn("Working now:", text)
        self.assertIn("Recommended next upgrades:", text)
        self.assertIn("Not planned until safety is designed:", text)
        self.assertIn("GUI settings panel", text)
        self.assertIn("GUI startup summaries", text)
        self.assertIn("Voice action preview and correction", text)
        self.assertIn("Task editing, restore, and confirmed task deletion", text)
        self.assertIn("Confirmation-gated named safe shell command runner", text)
        self.assertIn("Guided safe shell command allowlist editor", text)
        self.assertIn("Confirmed bulk write and restore command designs", text)
        self.assertIn("Optional per-file-type trust signals", text)
        self.assertIn("Read-only script review snapshot filtering", text)
        self.assertIn("Script checklist verification details", text)
        self.assertIn("Review-only script allowlist preflight records", text)
        self.assertIn("Raw arbitrary shell command execution", text)
