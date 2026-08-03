import unittest

from assistant.about import about_text


class AboutTests(unittest.TestCase):
    def test_about_text_includes_architecture_and_safety(self) -> None:
        text = about_text("Eva")

        self.assertIn("About Eva", text)
        self.assertIn("Architecture:", text)
        self.assertIn("Ollama", text)
        self.assertIn("Vosk", text)
        self.assertIn("allowlisted", text)
        self.assertIn("no raw arbitrary shell commands", text)
