import unittest

from assistant.launch_commands import launch_commands_text


class LaunchCommandTests(unittest.TestCase):
    def test_launch_commands_include_cli_gui_voice_and_checks(self) -> None:
        text = launch_commands_text()

        self.assertIn("Launch commands", text)
        self.assertIn("python -m assistant.cli", text)
        self.assertIn("python -m assistant.gui", text)
        self.assertIn("--voice --speak", text)
        self.assertIn("--wake --speak", text)
        self.assertIn("python scripts/check_all.py", text)
        self.assertIn("PowerShell", text)
