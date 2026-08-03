import unittest
from pathlib import Path
from unittest.mock import patch

from assistant.voice_status import voice_status_text


class VoiceStatusTests(unittest.TestCase):
    @patch("assistant.voice_status.platform.system", return_value="Windows")
    @patch("assistant.voice_status.list_input_devices", return_value=["0: Microphone"])
    def test_voice_status_reports_model_and_devices(self, mock_devices, mock_system) -> None:
        text = voice_status_text(Path("missing-model"))

        self.assertIn("Voice status", text)
        self.assertIn("Input model path: missing-model", text)
        self.assertIn("Input devices: 1", text)
        self.assertIn("Voice output supported: yes", text)

    @patch("assistant.voice_status.list_input_devices")
    def test_voice_status_reports_device_errors(self, mock_devices) -> None:
        from assistant.voice_input import VoiceInputError

        mock_devices.side_effect = VoiceInputError("Missing dependency: sounddevice")

        text = voice_status_text("missing-model")

        self.assertIn("Input devices: error: Missing dependency: sounddevice", text)
        self.assertIn("does not listen or speak", text)
