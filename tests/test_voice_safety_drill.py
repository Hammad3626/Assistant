import unittest

from assistant.voice_safety_drill import voice_safety_drill_text


class VoiceSafetyDrillTests(unittest.TestCase):
    def test_drill_is_read_only_and_no_microphone(self) -> None:
        text = voice_safety_drill_text()

        self.assertIn("Voice safety drill", text)
        self.assertIn("No microphone is used", text)
        self.assertIn("no app opens", text)
        self.assertIn("no action is queued", text)

    def test_drill_shows_two_step_low_confidence_flow(self) -> None:
        text = voice_safety_drill_text()

        self.assertIn("Say 'yes'", text)
        self.assertIn("confirm action", text)
        self.assertIn("Saying the second phrase first does not run the action", text)


if __name__ == "__main__":
    unittest.main()
