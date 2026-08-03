"""Check confirmed script run simulation without running scripts."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from assistant.core import LocalAssistant
from assistant.launch_requests import LaunchRequestStore


def main() -> int:
    print("Local PC Assistant script run simulation check")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script = root / "cleanup.py"
        marker = root / "should_not_exist.txt"
        script.write_text(
            f"print('review only, no write to {marker}')\n",
            encoding="utf-8",
        )
        assistant = LocalAssistant(
            use_llm=False,
            launch_request_store=LaunchRequestStore(root / "launch_requests.json"),
            script_checklist_dir=root / "script-checklists",
            script_preflight_dir=root / "script-preflights",
            script_execution_readiness_dir=root / "script-readiness",
            script_run_simulation_dir=root / "script-simulations",
        )

        commands = [
            (f"request script review cleanup: {script}", "Next review step: script review checklist 1"),
            ("script review checklist 1", "Script operator checklist created"),
            ("script allowlist preflight 1", "Preflight status: preflight_ready"),
            ("script execution readiness 1", "Execution readiness status: ready"),
            (
                "confirm script run simulation 1: confirm script run",
                "Simulation status: simulated",
            ),
        ]
        for command, expected in commands:
            response = assistant.respond(command)
            print(f"> {command}")
            print(response.text)
            if expected not in response.text:
                print(f"ERROR: expected text not found: {expected}")
                return 1
            if response.pending_action is not None:
                print("ERROR: simulation command path must not create pending actions.")
                return 1

        if marker.exists():
            print("ERROR: simulation path ran the script.")
            return 1

        readiness_manifest = sorted((root / "script-readiness").glob("*/manifest.json"))[-1]
        readiness_raw = json.loads(readiness_manifest.read_text(encoding="utf-8"))
        readiness_raw["readiness_signature"] = "tampered"
        readiness_manifest.write_text(json.dumps(readiness_raw, indent=2) + "\n", encoding="utf-8")

        tamper_response = assistant.respond("confirm script run simulation 1: confirm script run")
        print("> confirm script run simulation 1: confirm script run")
        print(tamper_response.text)
        if "Simulation status: blocked" not in tamper_response.text:
            print("ERROR: tampered readiness signature should block simulation.")
            return 1
        if "Readiness signature validation failed." not in tamper_response.text:
            print("ERROR: tampered readiness signature reason missing.")
            return 1

        refresh = assistant.respond("script execution readiness 1")
        print("> script execution readiness 1")
        print(refresh.text)
        if "Execution readiness status: ready" not in refresh.text:
            print("ERROR: could not refresh readiness after tamper test.")
            return 1

        script.write_text("print('modified after review')\n", encoding="utf-8")
        mismatch_response = assistant.respond("confirm script run simulation 1: confirm script run")
        print("> confirm script run simulation 1: confirm script run")
        print(mismatch_response.text)
        if "Simulation status: blocked" not in mismatch_response.text:
            print("ERROR: hash mismatch should block simulation.")
            return 1
        if "Current script hash/size does not match readiness metadata." not in mismatch_response.text:
            print("ERROR: hash mismatch reason missing.")
            return 1

    print("OK: Confirmed script run simulation is read-only and blocks tampered or changed scripts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
