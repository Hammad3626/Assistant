import json
import tempfile
import unittest
from pathlib import Path

from assistant.aliases import (
    AliasError,
    add_alias,
    load_aliases,
    resolve_alias,
    save_aliases,
    validate_alias_target,
)


class AliasTests(unittest.TestCase):
    def test_missing_alias_file_uses_defaults(self) -> None:
        aliases = load_aliases("missing-alias-file.json")

        self.assertEqual(aliases["show me what you know"], "memories")

    def test_save_and_resolve_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "aliases.json"
            save_aliases({"show memory": "memories"}, path)

            resolved = resolve_alias("  Show   Memory  ", path)

        self.assertEqual(resolved, "memories")

    def test_alias_target_can_be_allowlisted_action(self) -> None:
        self.assertEqual(validate_alias_target("open calculator"), "open calculator")

    def test_invalid_alias_target_is_rejected(self) -> None:
        with self.assertRaises(AliasError):
            validate_alias_target("delete downloads")

    def test_add_alias_persists_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "aliases.json"

            add_alias("conversation", "history", path)
            aliases = load_aliases(path)

        self.assertEqual(aliases["conversation"], "history")

    def test_invalid_alias_json_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "aliases.json"
            path.write_text(json.dumps({"bad": {}}), encoding="utf-8")

            with self.assertRaises(AliasError):
                load_aliases(path)


if __name__ == "__main__":
    unittest.main()
