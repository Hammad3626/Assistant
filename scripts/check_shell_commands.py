"""Check confirmation-gated named safe shell command support."""

from __future__ import annotations

import tempfile
from pathlib import Path

from assistant.core import LocalAssistant


def main() -> int:
    print("Local assistant safe shell command check")
    assistant = LocalAssistant(use_llm=False)

    listing = assistant.respond("shell commands")
    if "Safe shell commands" not in listing.text or "python version" not in listing.text:
        print("ERROR: Shell command allowlist is missing expected commands.")
        print(listing.text)
        return 1

    response = assistant.respond("run shell python version")
    if response.pending_action is None or response.pending_action.kind != "shell_command":
        print("ERROR: run shell did not require confirmation.")
        print(response.text)
        return 1

    result = assistant.confirm_pending_action(response.pending_action)
    if "Shell command finished with exit code" not in result:
        print("ERROR: Confirmed shell command returned unexpected output.")
        print(result)
        return 1

    blocked = assistant.respond("run shell delete everything")
    if "Shell command error" not in blocked.text or blocked.pending_action is not None:
        print("ERROR: Unknown shell command was not safely blocked.")
        print(blocked.text)
        return 1

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_allowlist = Path(temp_dir) / "shell_commands.json"
        editor_assistant = LocalAssistant(use_llm=False, shell_commands_path=temp_allowlist)
        guide = editor_assistant.respond("shell command guide")
        wizard = editor_assistant.respond("shell command wizard")
        wizard_saved = editor_assistant.respond("python wizard check: python --version")
        added = editor_assistant.respond("add shell command python check: python --version")
        checklist = editor_assistant.respond("shell review checklist python check")
        checklist_verification = editor_assistant.respond("verify shell checklist python check")
        added_run = editor_assistant.respond("run shell python check")
        removed = editor_assistant.respond("remove shell command python wizard check")
        unsafe = editor_assistant.respond("add shell command unsafe: python -c print(1)")

    if "Safe shell command allowlist guide" not in guide.text:
        print("ERROR: Shell command guide is missing.")
        print(guide.text)
        return 1
    if "Saved safe shell command" not in added.text or added.pending_action is not None:
        print("ERROR: Adding a shell command did not save safely.")
        print(added.text)
        return 1
    if "Static review notes" not in added.text:
        print("ERROR: Added shell command did not include static review notes.")
        print(added.text)
        return 1
    if "Static risk score" not in added.text:
        print("ERROR: Added shell command did not include static risk scoring.")
        print(added.text)
        return 1
    if "Signed review metadata" not in added.text:
        print("ERROR: Added shell command did not include signed review metadata.")
        print(added.text)
        return 1
    if "Shell operator checklist created" not in checklist.text or checklist.pending_action is not None:
        print("ERROR: Shell review checklist was not created safely.")
        print(checklist.text)
        return 1
    if "No shell command was run" not in checklist.text:
        print("ERROR: Shell review checklist did not report no-run behavior.")
        print(checklist.text)
        return 1
    if "Status: verified" not in checklist_verification.text or checklist_verification.pending_action is not None:
        print("ERROR: Shell review checklist verification did not pass safely.")
        print(checklist_verification.text)
        return 1
    if "Safe shell command wizard" not in wizard.text:
        print("ERROR: Shell command wizard is missing.")
        print(wizard.text)
        return 1
    if "Saved safe shell command" not in wizard_saved.text or wizard_saved.pending_action is not None:
        print("ERROR: Shell command wizard did not save safely.")
        print(wizard_saved.text)
        return 1
    if "Static review notes" not in wizard_saved.text:
        print("ERROR: Shell command wizard save did not include static review notes.")
        print(wizard_saved.text)
        return 1
    if "Static risk score" not in wizard_saved.text:
        print("ERROR: Shell command wizard save did not include static risk scoring.")
        print(wizard_saved.text)
        return 1
    if "Signed review metadata" not in wizard_saved.text:
        print("ERROR: Shell command wizard save did not include signed review metadata.")
        print(wizard_saved.text)
        return 1
    if added_run.pending_action is None or added_run.pending_action.kind != "shell_command":
        print("ERROR: Added shell command did not require confirmation before running.")
        print(added_run.text)
        return 1
    if "Removed safe shell command" not in removed.text or removed.pending_action is not None:
        print("ERROR: Removing a shell command did not update safely.")
        print(removed.text)
        return 1
    if "Signed review metadata" not in removed.text:
        print("ERROR: Removing a shell command did not include signed review metadata.")
        print(removed.text)
        return 1
    if "Inline Python code" not in unsafe.text:
        print("ERROR: Unsafe inline Python command was not rejected.")
        print(unsafe.text)
        return 1

    print(listing.text)
    print(result)
    print(guide.text)
    print(wizard.text)
    print(wizard_saved.text)
    print(added.text)
    print(checklist.text)
    print(checklist_verification.text)
    print(removed.text)
    print("OK: Safe shell commands are confirmation-gated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
