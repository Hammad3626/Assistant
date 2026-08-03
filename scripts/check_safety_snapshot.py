"""Check the read-only safety snapshot command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from assistant.core import LocalAssistant
from assistant.launch_requests import LaunchRequestStore


def main() -> int:
    print("Local PC Assistant safety snapshot check")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        document = root / "report.txt"
        document.write_text("local report", encoding="utf-8")
        script_path = root / "cleanup.py"
        script_path.write_text("print('cleanup dry run')\n", encoding="utf-8")
        script_drift_path = root / "cleanup_drift.py"
        script_drift_path.write_text("print('cleanup drift dry run')\n", encoding="utf-8")
        launch_store = LaunchRequestStore(root / "launch_requests.json")
        assistant = LocalAssistant(
            use_llm=False,
            launch_request_store=launch_store,
            shell_commands_path=root / "shell_commands.json",
            script_checklist_dir=root / "script-checklists",
            script_preflight_dir=root / "script-preflights",
            script_execution_readiness_dir=root / "script-readiness",
            script_run_simulation_dir=root / "script-run-simulations",
            script_allowlist_simulation_dir=root / "script-allowlist-simulations",
        )

        assistant.respond("request app paint: mspaint.exe")
        assistant.respond(f"request script review cleanup: {script_path}")
        assistant.respond("script review checklist 1")
        assistant.respond("script allowlist preflight 1")
        assistant.respond("script execution readiness 1")
        assistant.respond("confirm script run simulation 1: confirm script run")
        assistant.respond("script allowlist entry simulation 1: python --version")
        assistant.respond(f"request script review cleanup-drift: {script_drift_path}")
        assistant.respond("script review checklist 2")
        assistant.respond("script allowlist preflight 2")
        assistant.respond("script execution readiness 2")
        drift_manifest_candidates = sorted((root / "script-readiness").glob("script-execution-readiness-*/manifest.json"))
        drift_manifest_path = drift_manifest_candidates[-1]
        drift_manifest = json.loads(drift_manifest_path.read_text(encoding="utf-8-sig"))
        static_metadata = drift_manifest.get("static_metadata")
        if isinstance(static_metadata, dict):
            static_metadata["path"] = str(root / "tampered_different_target.py")
        drift_manifest_path.write_text(json.dumps(drift_manifest, indent=2) + "\n", encoding="utf-8")
        script_drift_path.write_text("print('cleanup drift changed content')\n", encoding="utf-8")
        assistant.respond("confirm script run simulation 2: confirm script run")
        assistant.respond("script allowlist entry simulation 2: python --version")
        assistant.respond(f"request file review report: {document}")
        assistant.respond("add shell command python check: python --version")
        response = assistant.respond("safety snapshot")
        launch_response = assistant.respond("safety snapshot launch")
        shell_response = assistant.respond("safety snapshot shell")
        script_response = assistant.respond("safety snapshot scripts")
        script_drift_response = assistant.respond("safety snapshot scripts drift")
        script_drift_signature_response = assistant.respond("safety snapshot scripts drift signature")
        script_drift_hash_response = assistant.respond("safety snapshot scripts drift hash")
        script_drift_path_response = assistant.respond("safety snapshot scripts drift path")
        print(response.text)
        print()
        print(launch_response.text)
        print()
        print(shell_response.text)
        print()
        print(script_response.text)
        print()
        print(script_drift_response.text)
        print()
        print(script_drift_signature_response.text)
        print()
        print(script_drift_hash_response.text)
        print()
        print(script_drift_path_response.text)

        required = (
            "Safety snapshot",
            "Read-only",
            "Launch review requests: 4",
            "Shell allowlist review records: 1",
            "signature valid",
            "No apps, scripts, files, folders, or shell commands were opened or run",
        )
        missing = [phrase for phrase in required if phrase not in response.text]
        if missing:
            print("ERROR: Safety snapshot is missing expected text:")
            for phrase in missing:
                print(f"- {phrase}")
            return 1
        if "Shell allowlist review records" in launch_response.text:
            print("ERROR: Launch snapshot should not include shell review records.")
            return 1
        if "Launch review requests" in shell_response.text:
            print("ERROR: Shell snapshot should not include launch review requests.")
            return 1
        if "Launch review requests" in script_response.text or "Shell allowlist review records" in script_response.text:
            print("ERROR: Script snapshot should only include script review requests.")
            return 1
        if "Safety snapshot: launch requests" not in launch_response.text:
            print("ERROR: Launch snapshot title missing.")
            return 1
        if "Safety snapshot: shell reviews" not in shell_response.text:
            print("ERROR: Shell snapshot title missing.")
            return 1
        if "Safety snapshot: script reviews" not in script_response.text:
            print("ERROR: Script snapshot title missing.")
            return 1
        if "Script review requests: 2" not in script_response.text:
            print("ERROR: Script snapshot did not report script review request count.")
            return 1
        if "checklist: verified" not in script_response.text:
            print("ERROR: Script snapshot did not report verified checklist details.")
            return 1
        if "preflight: " not in script_response.text:
            print("ERROR: Script snapshot did not report preflight details.")
            return 1
        if "readiness: ready" not in script_response.text:
            print("ERROR: Script snapshot did not report execution readiness details.")
            return 1
        if "run-simulation: simulated" not in script_response.text:
            print("ERROR: Script snapshot did not report run-simulation details.")
            return 1
        if "allowlist-simulation: simulated" not in script_response.text:
            print("ERROR: Script snapshot did not report allowlist-entry simulation details.")
            return 1
        if "allowlist-simulation: blocked" not in script_response.text:
            print("ERROR: Script snapshot did not report blocked allowlist simulation for drift scenario.")
            return 1
        if "drift warning:" not in script_response.text:
            print("ERROR: Script snapshot did not report drift warnings.")
            return 1
        drift_required = (
            "readiness-signature mismatch",
            "script-hash mismatch",
            "path mismatch",
        )
        missing_drift = [phrase for phrase in drift_required if phrase not in script_response.text]
        if missing_drift:
            print("ERROR: Script snapshot missing expected drift warning details:")
            for phrase in missing_drift:
                print(f"- {phrase}")
            return 1
        if "Safety snapshot: script drift warnings" not in script_drift_response.text:
            print("ERROR: Script drift snapshot title missing.")
            return 1
        if "Script requests with drift warnings: 1" not in script_drift_response.text:
            print("ERROR: Script drift snapshot did not report expected drift count.")
            return 1
        if "Drift warning breakdown: signature=1, hash=1, path=1" not in script_drift_response.text:
            print("ERROR: Script drift snapshot did not report expected warning-type breakdown counts.")
            return 1
        if "cleanup-drift" not in script_drift_response.text:
            print("ERROR: Script drift snapshot did not include drifting request.")
            return 1
        if "cleanup ->" in script_drift_response.text:
            print("ERROR: Script drift snapshot should not include non-drifting requests.")
            return 1
        if "Safety snapshot: script drift warnings (signature)" not in script_drift_signature_response.text:
            print("ERROR: Signature-filtered script drift snapshot title missing.")
            return 1
        if "Script requests with drift warnings (signature): 1" not in script_drift_signature_response.text:
            print("ERROR: Signature-filtered script drift snapshot did not report expected count.")
            return 1
        if "cleanup-drift" not in script_drift_signature_response.text:
            print("ERROR: Signature-filtered script drift snapshot did not include drifting request.")
            return 1
        if "Safety snapshot: script drift warnings (hash)" not in script_drift_hash_response.text:
            print("ERROR: Hash-filtered script drift snapshot title missing.")
            return 1
        if "Script requests with drift warnings (hash): 1" not in script_drift_hash_response.text:
            print("ERROR: Hash-filtered script drift snapshot did not report expected count.")
            return 1
        if "cleanup-drift" not in script_drift_hash_response.text:
            print("ERROR: Hash-filtered script drift snapshot did not include drifting request.")
            return 1
        if "Safety snapshot: script drift warnings (path)" not in script_drift_path_response.text:
            print("ERROR: Path-filtered script drift snapshot title missing.")
            return 1
        if "Script requests with drift warnings (path): 1" not in script_drift_path_response.text:
            print("ERROR: Path-filtered script drift snapshot did not report expected count.")
            return 1
        if "cleanup-drift" not in script_drift_path_response.text:
            print("ERROR: Path-filtered script drift snapshot did not include drifting request.")
            return 1

    print("OK: Safety snapshot is read-only and summarizes local review records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
