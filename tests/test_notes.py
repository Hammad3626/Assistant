import tempfile
import unittest
from pathlib import Path

from assistant.notes import NotesError, NotesStore


class NotesTests(unittest.TestCase):
    def test_missing_notes_are_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = NotesStore(Path(temp_dir) / "notes.md")

            self.assertEqual(store.list_notes(), [])
            self.assertEqual(store.summary(), "No saved notes.")

    def test_add_note_appends_markdown_note(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "notes.md"
            store = NotesStore(path)

            item = store.add("  buy printer paper  ")
            notes = store.list_notes()

        self.assertEqual(item.text, "buy printer paper")
        self.assertEqual(notes[0].text, "buy printer paper")

    def test_empty_note_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = NotesStore(Path(temp_dir) / "notes.md")

            with self.assertRaises(NotesError):
                store.add("   ")


if __name__ == "__main__":
    unittest.main()
