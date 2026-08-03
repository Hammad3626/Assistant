import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assistant.windows_detection import (
    DetectedDrive,
    detect_common_folders,
    detected_drives_summary,
    detected_folders_summary,
)


class WindowsDetectionTests(unittest.TestCase):
    def test_detect_common_folders_finds_existing_user_folders(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            (home / "Desktop").mkdir()
            (home / "Documents").mkdir()
            one_drive = home / "OneDrive"
            one_drive.mkdir()

            folders = detect_common_folders(
                home=home,
                environ={"OneDrive": str(one_drive)},
            )

        names = {folder.name for folder in folders}
        self.assertIn("Desktop", names)
        self.assertIn("Documents", names)
        self.assertIn("OneDrive", names)
        self.assertNotIn("Downloads", names)

    @patch("assistant.windows_detection.detect_common_folders")
    def test_folders_summary_is_read_only(self, mock_detect) -> None:
        mock_detect.return_value = []

        text = detected_folders_summary()

        self.assertIn("Detected Windows folders", text)
        self.assertIn("read-only", text)

    @patch("assistant.windows_detection.detect_drives")
    def test_drives_summary_is_read_only(self, mock_detect) -> None:
        mock_detect.return_value = [DetectedDrive("C drive", "C:\\")]

        text = detected_drives_summary()

        self.assertIn("Detected Windows drives", text)
        self.assertIn("C drive", text)
        self.assertIn("Nothing was added", text)


if __name__ == "__main__":
    unittest.main()
