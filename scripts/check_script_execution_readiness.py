"""Check script execution readiness bundle creation without running scripts."""

from __future__ import annotations

import tempfile
from pathlib import Path

from assistant.core import LocalAssistant
from assistant.launch_requests import LaunchRequestStore


def main() -> int:
    print("Local PC Assistant script execution readiness check")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script = root / "cleanup.py"
        marker = root / "should_not_exist.txt"
        script.write_text(
            f"print('review only, no write to {marker}')\\n",
            encoding="utf-8",
        )
        assistant = LocalAssistant(
            use_llm=False,
            launch_request_store=LaunchRequestStore(root / "launch_requests.json"),
            script_checklist_dir=root / "script-checklists",
            script_preflight_dir=root / "script-preflights",
            script_execution_readiness_dir=root / "script-readiness",
        )

        commands = [
            (f"request script review cleanup: {script}", "Next review step: script review checklist 1"),
            ("script review checklist 1", "Script operator checklist created"),
            ("script allowlist preflight 1", "Preflight status: preflight_ready"),
            ("script execution readiness 1", "Execution readiness status: ready"),
        ]
        for command, expected in commands:
            response = assistant.respond(command)
            print(f"> {command}")
            print(response.text)
            if expected not in response.text:
                print(f"ERROR: expected text not found: {expected}")
                return 1
            if response.pending_action is not None:
                print("ERROR: readiness command path must not create pending actions.")
                return 1

        if marker.exists():
            print("ERROR: readiness path ran the script.")
            return 1

    print("OK: Script execution readiness bundle is review-only and execution remains disabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
