"""Run the local assistant's non-interactive health checks."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    command: list[str]
    required: bool = True


CHECKS = [
    Check("unit tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests"]),
    Check("environment", [sys.executable, "scripts/check_env.py"]),
    Check("settings", [sys.executable, "scripts/check_settings.py"]),
    Check("persona", [sys.executable, "scripts/check_persona.py"]),
    Check("aliases", [sys.executable, "scripts/check_aliases.py"]),
    Check("about command", [sys.executable, "scripts/check_about.py"]),
    Check("safety command", [sys.executable, "scripts/check_safety.py"]),
    Check("safety snapshot", [sys.executable, "scripts/check_safety_snapshot.py"]),
    Check("roadmap command", [sys.executable, "scripts/check_roadmap.py"]),
    Check("launch commands", [sys.executable, "scripts/check_launch_commands.py"]),
    Check("command reference", [sys.executable, "scripts/check_commands.py"]),
    Check("command suggestions", [sys.executable, "scripts/check_suggestions.py"]),
    Check("natural intents", [sys.executable, "scripts/check_intents.py"]),
    Check("focused help", [sys.executable, "scripts/check_help.py"]),
    Check("path report", [sys.executable, "scripts/check_paths.py"]),
    Check("Windows detection", [sys.executable, "scripts/check_windows_detection.py"]),
    Check("Windows open commands", [sys.executable, "scripts/check_windows_open_commands.py"]),
    Check("memory", [sys.executable, "scripts/check_memory.py"]),
    Check("history", [sys.executable, "scripts/check_history.py"]),
    Check("notes", [sys.executable, "scripts/check_notes.py"]),
    Check("tasks", [sys.executable, "scripts/check_tasks.py"]),
    Check("expanded task commands", [sys.executable, "scripts/check_task_commands.py"]),
    Check("search", [sys.executable, "scripts/check_search.py"]),
    Check("file tools", [sys.executable, "scripts/check_file_tools.py"]),
    Check("file trash", [sys.executable, "scripts/check_file_trash.py"]),
    Check("safe shell commands", [sys.executable, "scripts/check_shell_commands.py"]),
    Check("signed safety reviews", [sys.executable, "scripts/check_safety_reviews.py"]),
    Check("launch requests", [sys.executable, "scripts/check_launch_requests.py"]),
    Check("script allowlist design", [sys.executable, "scripts/check_script_allowlist_design.py"]),
    Check("script checklists", [sys.executable, "scripts/check_script_checklists.py"]),
    Check("script preflight", [sys.executable, "scripts/check_script_preflight.py"]),
    Check("file-type allowlist", [sys.executable, "scripts/check_file_type_allowlist.py"]),
    Check("file launch workflow", [sys.executable, "scripts/check_file_launch_workflow.py"]),
    Check("local outbox", [sys.executable, "scripts/check_outbox.py"]),
    Check("briefing", [sys.executable, "scripts/check_briefing.py"]),
    Check("status", [sys.executable, "scripts/status.py"], required=False),
    Check("models", [sys.executable, "scripts/models.py"], required=False),
    Check("model command", [sys.executable, "scripts/check_model_command.py"], required=False),
    Check("app allowlist", [sys.executable, "scripts/check_apps.py"]),
    Check("folder allowlist", [sys.executable, "scripts/check_folders.py"]),
    Check("action audit", [sys.executable, "scripts/check_audit.py"]),
    Check("GUI", [sys.executable, "scripts/check_gui.py"]),
    Check("GUI dashboard", [sys.executable, "scripts/check_gui_dashboard.py"]),
    Check("voice setup", [sys.executable, "scripts/check_voice.py"], required=False),
    Check("voice status command", [sys.executable, "scripts/check_voice_status.py"], required=False),
    Check("voice action audit", [sys.executable, "scripts/check_voice_audit.py"], required=False),
    Check("voice confidence", [sys.executable, "scripts/check_voice_confidence.py"], required=False),
    Check(
        "voice second confirmation",
        [sys.executable, "scripts/check_voice_second_confirmation.py"],
        required=False,
    ),
    Check("voice safety drill", [sys.executable, "scripts/check_voice_safety_drill.py"], required=False),
    Check("wake voice loop", [sys.executable, "scripts/check_wake_voice.py"], required=False),
    Check("script execution readiness", [sys.executable, "scripts/check_script_execution_readiness.py"], required=False),
    Check("script run simulation", [sys.executable, "scripts/check_script_run_simulation.py"], required=False),
    Check("script allowlist-entry simulation", [sys.executable, "scripts/check_script_allowlist_entry_simulation.py"], required=False),
    Check(
        "Ollama tiny model",
        [sys.executable, "scripts/check_ollama.py", "--model", "smollm2:135m", "--num-gpu", "0"],
        required=False,
    ),
]


def run_check(check: Check) -> bool:
    print(f"\n=== {check.name} ===", flush=True)
    result = subprocess.run(check.command, check=False, text=True)
    if result.returncode == 0:
        print(f"PASS: {check.name}", flush=True)
        return True

    label = "FAIL" if check.required else "WARN"
    print(f"{label}: {check.name} exited with code {result.returncode}", flush=True)
    return not check.required


def main() -> int:
    print("Local PC Assistant full health check")
    all_required_ok = True
    for check in CHECKS:
        if not run_check(check):
            all_required_ok = False

    if not all_required_ok:
        print("\nOne or more required checks failed.")
        return 1

    print("\nOK: Required checks passed. Optional checks may still need local device/model fixes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
