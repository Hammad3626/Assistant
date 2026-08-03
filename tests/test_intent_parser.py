import unittest

from assistant.intent_parser import normalize_intent


class IntentParserTests(unittest.TestCase):
    def test_natural_help_and_status_phrases(self) -> None:
        self.assertEqual(normalize_intent("what can you do for me?"), "help")
        self.assertEqual(normalize_intent("show all commands"), "command reference")
        self.assertEqual(normalize_intent("are you healthy?"), "status")
        self.assertEqual(normalize_intent("what is blocked"), "permissions dashboard")
        self.assertEqual(normalize_intent("how do I add safe shell commands"), "shell command guide")
        self.assertEqual(normalize_intent("show bulk apply safety"), "bulk apply safety")
        self.assertEqual(normalize_intent("design bulk write command"), "bulk write command design")
        self.assertEqual(normalize_intent("design bulk restore command"), "bulk restore command design")
        self.assertEqual(normalize_intent("design script allowlist"), "script allowlist design")

    def test_time_and_date_phrases(self) -> None:
        self.assertEqual(normalize_intent("tell me the time"), "time")
        self.assertEqual(normalize_intent("what day is it?"), "date")

    def test_natural_open_phrases_map_to_safe_actions(self) -> None:
        self.assertEqual(normalize_intent("launch calculator app"), "open calculator")
        self.assertEqual(normalize_intent("open google chrome"), "open chrome")
        self.assertEqual(normalize_intent("show my downloads folder"), "open downloads")
        self.assertEqual(normalize_intent("open drive d"), "open D drive")
        self.assertEqual(normalize_intent("open c colon"), "open C drive")
        self.assertEqual(normalize_intent("show computer"), "open this pc")
        self.assertEqual(normalize_intent("open windows settings"), "open settings")

    def test_memory_note_and_task_payloads_are_preserved(self) -> None:
        self.assertEqual(
            normalize_intent("save memory that I prefer short answers"),
            "remember I prefer short answers",
        )
        self.assertEqual(normalize_intent("make a note to buy milk"), "note buy milk")
        self.assertEqual(normalize_intent("remind me to call dentist"), "todo call dentist")

    def test_file_and_shell_phrases_map_to_existing_commands(self) -> None:
        self.assertEqual(normalize_intent("show file tools"), "file tools")
        self.assertEqual(normalize_intent("list files in downloads folder"), "list files in downloads")
        self.assertEqual(
            normalize_intent("search project folder for quiet"),
            "search files in project folder for quiet",
        )
        self.assertEqual(
            normalize_intent("find file names in project folder for readme"),
            "find files in project folder for readme",
        )
        self.assertEqual(
            normalize_intent("please open file in project folder README.md"),
            "open file in project folder README.md",
        )
        self.assertEqual(
            normalize_intent("preview README.md in project folder"),
            "open file in project folder README.md",
        )
        self.assertEqual(
            normalize_intent("dry run replace in project folder find old with new"),
            "preview replace in project folder find old with new",
        )
        self.assertIsNone(normalize_intent("preview rename files in project folder replace old with new"))
        self.assertEqual(normalize_intent("run python version check"), "run shell python version")

    def test_risky_open_paths_are_not_rewritten(self) -> None:
        self.assertIsNone(normalize_intent(r"open C:\Windows\System32\cmd.exe"))
        self.assertIsNone(normalize_intent("open mystery app"))
        self.assertIsNone(normalize_intent("send email to Alex"))


if __name__ == "__main__":
    unittest.main()
