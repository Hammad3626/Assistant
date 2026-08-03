"""Check reversible allowlisted file trash using a temporary folder."""

from __future__ import annotations

import tempfile
from pathlib import Path

from assistant.actions import save_allowed_folders
from assistant.core import LocalAssistant


def main() -> int:
    print("Local assistant file trash check")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        workspace = root / "workspace"
        workspace.mkdir()
        target = workspace / "notes.txt"
        target.write_text("temporary file trash check\n", encoding="utf-8")
        folders_path = root / "folders.json"
        save_allowed_folders({"workspace": str(workspace)}, folders_path)
        assistant = LocalAssistant(
            use_llm=False,
            folders_path=folders_path,
            file_trash_dir=root / "trash",
            file_trash_manifest_path=root / "manifest.json",
        )

        delete_response = assistant.respond("delete file in workspace notes.txt")
        if delete_response.pending_action is None:
            print("ERROR: File delete did not require confirmation.")
            print(delete_response.text)
            return 1

        result = assistant.confirm_pending_action(delete_response.pending_action)
        if target.exists() or "Moved file to assistant trash" not in result:
            print("ERROR: Confirmed file delete did not move the file to assistant trash.")
            print(result)
            return 1

        trash = assistant.respond("file trash")
        if "workspace/notes.txt" not in trash.text:
            print("ERROR: File trash summary is missing the deleted file.")
            print(trash.text)
            return 1

        restore = assistant.respond("restore file 1")
        if "Restored file 1" not in restore.text or not target.exists():
            print("ERROR: File restore failed.")
            print(restore.text)
            return 1

    print(result)
    print("OK: File trash and restore are confirmation-gated and reversible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
