import unittest
from unittest.mock import Mock, patch

from assistant.cli import (
    extract_voice_correction,
    is_confirmation,
    is_second_voice_confirmation,
    low_confidence_voice_confirmation_text,
    read_voice_command,
    requires_second_voice_confirmation,
    should_continue_wake_loop_after_voice_error,
    voice_action_preview_text,
)
from assistant.voice_input import (
    VoiceConfidenceReport,
    VoiceInputConfig,
    VoiceInputError,
    VoiceInputResult,
)


def voice_result(text: str, level: str = "high") -> VoiceInputResult:
    return VoiceInputResult(
        text=text,
        confidence=VoiceConfidenceReport(
            text=text,
            word_count=len(text.split()),
            average_confidence=0.9 if level != "unavailable" else None,
            minimum_confidence=0.85 if level != "unavailable" else None,
            level=level,
            notes=("test",),
        ),
        capture_seconds=1.0,
        speech_seconds=0.8,
        chunk_count=10,
        input_device=None,
        sample_rate=16000,
        audio_statuses=(),
    )


class CliVoiceLoopTests(unittest.TestCase):
    @patch("assistant.cli.listen_once_with_confidence", return_value=voice_result("hello"))
    def test_read_voice_command_without_wake_mode(self, mock_listen) -> None:
        command = read_voice_command(VoiceInputConfig(), False, "hey eva")

        self.assertEqual(command, "hello")
        mock_listen.assert_called_once()

    @patch("assistant.cli.listen_once_with_confidence", return_value=voice_result("hey eva hello"))
    def test_read_voice_command_extracts_inline_wake_command(self, mock_listen) -> None:
        command = read_voice_command(VoiceInputConfig(), True, "hey eva")

        self.assertEqual(command, "hello")
        mock_listen.assert_called_once()

    @patch(
        "assistant.cli.listen_once_with_confidence",
        side_effect=[voice_result("hey eva"), voice_result("as it")],
    )
    def test_read_voice_command_listens_again_after_bare_wake_phrase(self, mock_listen) -> None:
        command = read_voice_command(VoiceInputConfig(), True, "hey eva")

        self.assertEqual(command, "exit")
        self.assertEqual(mock_listen.call_count, 2)

    @patch("assistant.cli.listen_once_with_confidence", return_value=voice_result("random speech"))
    def test_read_voice_command_ignores_without_wake_phrase(self, mock_listen) -> None:
        command = read_voice_command(VoiceInputConfig(), True, "hey eva")

        self.assertIsNone(command)
        mock_listen.assert_called_once()

    def test_wake_loop_continues_after_silence_timeout(self) -> None:
        self.assertTrue(
            should_continue_wake_loop_after_voice_error(
                VoiceInputError("No speech recognized before timeout.")
            )
        )

    def test_wake_loop_does_not_continue_after_setup_error(self) -> None:
        self.assertFalse(
            should_continue_wake_loop_after_voice_error(
                VoiceInputError("Vosk model not found: missing")
            )
        )

    def test_voice_confirmation_words_are_limited(self) -> None:
        self.assertTrue(is_confirmation("yes"))
        self.assertTrue(is_confirmation("okay"))
        self.assertFalse(is_confirmation("yes delete it"))

    def test_second_voice_confirmation_phrase_is_specific(self) -> None:
        self.assertTrue(is_second_voice_confirmation("confirm action"))
        self.assertFalse(is_second_voice_confirmation("confirm"))
        self.assertFalse(is_second_voice_confirmation("yes"))

    def test_low_confidence_voice_actions_need_second_confirmation(self) -> None:
        self.assertTrue(requires_second_voice_confirmation("low"))
        self.assertTrue(requires_second_voice_confirmation("unavailable"))
        self.assertFalse(requires_second_voice_confirmation("medium"))
        self.assertFalse(requires_second_voice_confirmation("high"))

    def test_low_confidence_prompt_names_second_phrase(self) -> None:
        text = low_confidence_voice_confirmation_text("low")

        self.assertIn("Voice confidence was low", text)
        self.assertIn("confirm action", text)
        self.assertIn("no", text)

    def test_extract_voice_correction_from_spoken_phrase(self) -> None:
        self.assertEqual(extract_voice_correction("correct open notepad"), "open notepad")
        self.assertEqual(extract_voice_correction("change to open calculator"), "open calculator")
        self.assertEqual(extract_voice_correction("actually open documents"), "open documents")
        self.assertEqual(extract_voice_correction("no, open notepad"), "open notepad")
        self.assertEqual(extract_voice_correction("I meant open downloads"), "open downloads")
        self.assertEqual(extract_voice_correction("replace it with open settings"), "open settings")
        self.assertIsNone(extract_voice_correction("actually"))
        self.assertIsNone(extract_voice_correction("no"))
        self.assertIsNone(extract_voice_correction("open calculator"))

    def test_voice_action_preview_names_heard_command_and_action(self) -> None:
        action = Mock(description="Open calculator")

        text = voice_action_preview_text("open calculator", action)

        self.assertIn("Voice command preview", text)
        self.assertIn("I heard 'open calculator'", text)
        self.assertIn("Pending action: Open calculator.", text)
        self.assertIn("actually <command>", text)


if __name__ == "__main__":
    unittest.main()
