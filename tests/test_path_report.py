import unittest

from assistant.path_report import format_path_report


class PathReportTests(unittest.TestCase):
    def test_format_path_report_includes_paths_and_read_only_note(self) -> None:
        text = format_path_report(
            {
                "Settings": "config/settings.json",
                "Memory": "data/memory.json",
                "Voice model": None,
            }
        )

        self.assertIn("Local assistant paths", text)
        self.assertIn("Settings: config/settings.json", text)
        self.assertIn("Voice model: not configured", text)
        self.assertIn("read-only", text)
