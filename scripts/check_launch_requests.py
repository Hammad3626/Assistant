"""Check that unlisted apps/scripts are review-only and never executed."""

from __future__ import annotations

import tempfile
from pathlib import Path

from assistant.core import LocalAssistant
from assistant.launch_requests import LaunchRequestStore


def main() -> int:
    print("Local PC Assistant launch request check")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        document = root / "report.pdf"
        document.write_text("local test", encoding="utf-8")
        script = root / "cleanup.py"
        script.write_text(
            "import subprocess\n"
            "subprocess.run(['python', '--version'])\n",
            encoding="utf-8",
        )
        folder = root / "archive"
        folder.mkdir()
        store = LaunchRequestStore(
            root / "launch_requests.json",
            file_type_allowlist_path=root / "file_types.json",
        )
        assistant = LocalAssistant(use_llm=False, launch_request_store=store)

        checks = [
            ("open mystery app", "Unlisted apps, scripts, files, and folders cannot open"),
            ("request app paint: mspaint.exe", "Launch request saved locally, not run"),
            (
                f"request script review cleanup: {script}",
                "read-only static inspection",
            ),
            (
                f"request file review report: {document}",
                "File review request saved locally, not run",
            ),
            (
                f"request folder review archive: {folder}",
                "Folder review request saved locally, not run",
            ),
            ("launch requests", "Launch requests (local review only; nothing was run):"),
        ]
        for command, expected in checks:
            response = assistant.respond(command)
            print(f"> {command}")
            print(response.text)
            if expected not in response.text:
                print(f"ERROR: expected text not found: {expected}")
                return 1

        if len(store.list_requests()) != 4:
            print("ERROR: blocked launch attempt should not create a request automatically.")
            return 1

    print("OK: Unlisted apps/scripts/files/folders are blocked and review requests are local-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
