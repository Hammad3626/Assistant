"""Check explicit per-file-type allowlisting for future file launch workflows."""

from __future__ import annotations

import tempfile
from pathlib import Path

from assistant.core import LocalAssistant
from assistant.launch_requests import LaunchRequestStore


def main() -> int:
    print("Local PC Assistant file-type allowlist check")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        file_types_path = root / "file_types.json"
        launch_requests_path = root / "launch_requests.json"
        first_document = root / "report.pdf"
        second_document = root / "invoice.pdf"
        third_document = root / "manual.pdf"
        for file_path in (first_document, second_document, third_document):
            file_path.write_text("local test", encoding="utf-8")

        launch_request_store = LaunchRequestStore(
            launch_requests_path,
            file_type_allowlist_path=file_types_path,
        )
        assistant = LocalAssistant(
            use_llm=False,
            launch_request_store=launch_request_store,
            file_type_allowlist_path=file_types_path,
        )

        checks = [
            ("file type allowlist", "File type allowlist: none"),
            (
                f"request file review report: {first_document}",
                "Launch eligibility: blocked until this file type is explicitly allowlisted.",
            ),
            ("allow file type pdf", "File type allowlisted: .pdf"),
            (
                f"request file review invoice: {second_document}",
                "Launch eligibility: file type is explicitly allowlisted for future launch workflows.",
            ),
            ("disallow file type .pdf", "File type removed from allowlist: .pdf"),
            (
                f"request file review manual: {third_document}",
                "Launch eligibility: blocked until this file type is explicitly allowlisted.",
            ),
        ]

        for command, expected in checks:
            response = assistant.respond(command)
            print(f"> {command}")
            print(response.text)
            if expected not in response.text:
                print(f"ERROR: expected text not found: {expected}")
                return 1

    print("OK: File-type allowlist gating behaves as expected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())