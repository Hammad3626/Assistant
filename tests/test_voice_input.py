import unittest
from pathlib import Path

from assistant.voice_input import (
    DEFAULT_VOICE_MODEL_PATH,
    DEFAULT_WAKE_PHRASE,
    VoiceInputError,
    analyze_voice_confidence,
    format_voice_confidence,
    extract_wake_command,
    normalize_spoken_command,
    resolve_model_path,
    voice_confidence_status_text,
    wake_status_text,
)


class VoiceInputTests(unittest.TestCase):
    def test_default_model_path(self) -> None:
        self.assertEqual(resolve_model_path(), DEFAULT_VOICE_MODEL_PATH)

    def test_custom_model_path(self) -> None:
        self.assertEqual(resolve_model_path("custom-model"), Path("custom-model"))

    def test_normalizes_common_exit_misrecognition(self) -> None:
        self.assertEqual(normalize_spoken_command("as it"), "exit")

    def test_leaves_unknown_speech_unchanged(self) -> None:
        self.assertEqual(normalize_spoken_command("open notes"), "open notes")

    def test_extracts_command_after_wake_phrase(self) -> None:
        woke, command = extract_wake_command("hey eva open calculator")

        self.assertTrue(woke)
        self.assertEqual(command, "open calculator")

    def test_detects_wake_phrase_without_inline_command(self) -> None:
        woke, command = extract_wake_command("hey eva")

        self.assertTrue(woke)
        self.assertEqual(command, "")

    def test_ignores_speech_without_wake_phrase(self) -> None:
        woke, command = extract_wake_command("open calculator")

        self.assertFalse(woke)
        self.assertEqual(command, "")

    def test_wake_phrase_matches_whole_words(self) -> None:
        woke, command = extract_wake_command("hey evaluate this")

        self.assertFalse(woke)
        self.assertEqual(command, "")

    def test_empty_wake_phrase_is_rejected(self) -> None:
        with self.assertRaises(VoiceInputError):
            extract_wake_command("hello", "")

    def test_wake_status_describes_optional_loop(self) -> None:
        text = wake_status_text(DEFAULT_WAKE_PHRASE)

        self.assertIn("Wake voice loop", text)
        self.assertIn("--wake --speak", text)
        self.assertIn(DEFAULT_WAKE_PHRASE, text)

    def test_analyzes_high_voice_confidence(self) -> None:
        report = analyze_voice_confidence(
            {
                "text": "open calculator",
                "result": [
                    {"word": "open", "conf": 0.91},
                    {"word": "calculator", "conf": 0.86},
                ],
            }
        )

        self.assertEqual(report.level, "high")
        self.assertEqual(report.word_count, 2)
        self.assertIn("avg", format_voice_confidence(report))

    def test_reports_unavailable_voice_confidence(self) -> None:
        report = analyze_voice_confidence({"text": "hello"})

        self.assertEqual(report.level, "unavailable")
        self.assertIsNone(report.average_confidence)
        self.assertIn("no word scores", format_voice_confidence(report))

    def test_voice_confidence_status_is_read_only(self) -> None:
        text = voice_confidence_status_text()

        self.assertIn("Voice confidence reporting", text)
        self.assertIn("read-only", text)
        self.assertIn("still require explicit confirmation", text)


if __name__ == "__main__":
    unittest.main()
