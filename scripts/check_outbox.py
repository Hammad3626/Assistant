"""Check local-only message, email, and request draft behavior."""

from __future__ import annotations

import tempfile
from pathlib import Path

from assistant.core import LocalAssistant
from assistant.outbox import OutboxStore


def main() -> int:
    print("Local PC Assistant outbox check")
    with tempfile.TemporaryDirectory() as temp_dir:
        outbox_store = OutboxStore(Path(temp_dir) / "outbox.json")
        assistant = LocalAssistant(use_llm=False, outbox_store=outbox_store)

        checks = [
            ("draft message to Alex: running late", "Draft saved locally, not sent"),
            (
                "draft email to alex@example.com subject Hello: quick local note",
                "Draft saved locally, not sent",
            ),
            (
                "draft network request GET https://example.com health check",
                "Draft saved locally, request not made",
            ),
            ("send message to Alex: hello", "Sending is not enabled"),
            ("outbox", "Outbox drafts (local only, not sent):"),
        ]

        for command, expected in checks:
            response = assistant.respond(command)
            print(f"> {command}")
            print(response.text)
            if expected not in response.text:
                print(f"ERROR: expected text not found: {expected}")
                return 1

        if len(outbox_store.list_drafts()) != 3:
            print("ERROR: blocked send command should not create a draft.")
            return 1

    print("OK: Outbox drafts are local only and direct sending is blocked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
