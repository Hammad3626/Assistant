import tempfile
import unittest
from pathlib import Path

from assistant.persona import PersonaError, build_system_prompt, load_persona


class PersonaTests(unittest.TestCase):
    def test_missing_persona_uses_default(self) -> None:
        persona = load_persona("missing-persona.txt")

        self.assertIn("local offline PC assistant", persona)

    def test_load_persona_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "persona.txt"
            path.write_text("Be concise.", encoding="utf-8")

            persona = load_persona(path)

        self.assertEqual(persona, "Be concise.")

    def test_empty_persona_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "persona.txt"
            path.write_text("   ", encoding="utf-8")

            with self.assertRaises(PersonaError):
                load_persona(path)

    def test_build_system_prompt_keeps_safety_footer(self) -> None:
        prompt = build_system_prompt("Be concise.")

        self.assertIn("Be concise.", prompt)
        self.assertIn("Non-negotiable safety rules", prompt)


if __name__ == "__main__":
    unittest.main()

