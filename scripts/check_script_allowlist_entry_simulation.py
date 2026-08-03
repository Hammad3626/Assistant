"""Check script allowlist-entry simulation without running scripts."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from assistant.core import LocalAssistant
from assistant.launch_requests import LaunchRequestStore


def main() -> int:
    print("Local PC Assistant script allowlist-entry simulation check")
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
            script_allowlist_simulation_dir=root / "script-allowlist-simulations",
        )

        bootstrap = [
            (f"request script review cleanup: {script}", "Next review step: script review checklist 1"),
            ("script review checklist 1", "Script operator checklist created"),
            ("script allowlist preflight 1", "Preflight status: preflight_ready"),
            ("script execution readiness 1", "Execution readiness status: ready"),
        ]
        for command, expected in bootstrap:
            response = assistant.respond(command)
            print(f"> {command}")
            print(response.text)
            if expected not in response.text:
                print(f"ERROR: expected text not found: {expected}")
                return 1

        ok = assistant.respond("script allowlist entry simulation 1: python --version")
        print("> script allowlist entry simulation 1: python --version")
        print(ok.text)
        if "Simulation status: simulated" not in ok.text:
            print("ERROR: expected simulated status for python --version policy.")
            return 1

        bad_arg = assistant.respond("script allowlist entry simulation 1: python -c print(1)")
        print("> script allowlist entry simulation 1: python -c print(1)")
        print(bad_arg.text)
        if "Simulation status: blocked" not in bad_arg.text:
            print("ERROR: blocked status expected for -c argument.")
            return 1
        if "Argument policy failed" not in bad_arg.text:
            print("ERROR: blocked argument reason missing.")
            return 1

        tamper_manifest = sorted((root / "script-readiness").glob("*/manifest.json"))[-1]
        tamper_raw = json.loads(tamper_manifest.read_text(encoding="utf-8"))
        tamper_raw["readiness_signature"] = "tampered"
        tamper_manifest.write_text(json.dumps(tamper_raw, indent=2) + "\n", encoding="utf-8")

        tampered = assistant.respond("script allowlist entry simulation 1: python --version")
        print("> script allowlist entry simulation 1: python --version")
        print(tampered.text)
        if "Simulation status: blocked" not in tampered.text:
            print("ERROR: tampered readiness signature should block allowlist-entry simulation.")
            return 1
        if "Readiness signature validation failed." not in tampered.text:
            print("ERROR: tampered readiness signature reason missing.")
            return 1

        refresh = assistant.respond("script execution readiness 1")
        print("> script execution readiness 1")
        print(refresh.text)
        if "Execution readiness status: ready" not in refresh.text:
            print("ERROR: could not refresh readiness after tamper test.")
            return 1

        script.write_text("print('modified after review')\n", encoding="utf-8")
        changed = assistant.respond("script allowlist entry simulation 1: python --version")
        print("> script allowlist entry simulation 1: python --version")
        print(changed.text)
        if "Simulation status: blocked" not in changed.text:
            print("ERROR: changed script should block allowlist-entry simulation.")
            return 1
        if "Current script hash/size does not match readiness metadata." not in changed.text:
            print("ERROR: changed script reason missing.")
            return 1

        if marker.exists():
            print("ERROR: allowlist-entry simulation path ran the script.")
            return 1

    print("OK: Script allowlist-entry simulation is read-only and blocks unsafe policy/tamper/hash states.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
