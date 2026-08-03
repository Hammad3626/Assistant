import unittest
from unittest.mock import patch

from assistant.voice_output import VoiceOutputConfig, speak


class VoiceOutputTests(unittest.TestCase):
    @patch("assistant.voice_output.platform.system", return_value="Windows")
    @patch("assistant.voice_output.subprocess.run")
    def test_speak_passes_text_as_argument(self, mock_run, mock_system) -> None:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""

        speak("hello; not code", VoiceOutputConfig(rate=1, volume=80))

        command = mock_run.call_args.args[0]
        self.assertIn("-Command", command)
        self.assertIn("hello; not code", command)
        self.assertIn("1", command)
        self.assertIn("80", command)

    @patch("assistant.voice_output.subprocess.run")
    def test_blank_text_does_not_call_subprocess(self, mock_run) -> None:
        speak("   ")

        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
