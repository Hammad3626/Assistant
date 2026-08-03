"""Check expanded local task commands."""

from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path

from assistant.core import LocalAssistant
from assistant.tasks import TasksStore


def main() -> int:
    print("Local PC Assistant expanded task command check")
    with tempfile.TemporaryDirectory() as temp_dir:
        tasks_store = TasksStore(Path(temp_dir) / "tasks.json")
        assistant = LocalAssistant(use_llm=False, tasks_store=tasks_store)
        due_date = (date.today() + timedelta(days=3)).isoformat()

        checks = [
            assistant.respond(f"todo call dentist due {due_date}").text,
            assistant.respond("task stats").text,
            assistant.respond("due soon").text,
            assistant.respond("rename task 1 to call doctor").text,
            assistant.respond(f"due 1 {due_date}").text,
            assistant.respond("clear due 1").text,
            assistant.respond("done 1").text,
            assistant.respond("restore task 1").text,
        ]
        delete_response = assistant.respond("delete task 1")
        checks.append(delete_response.text)
        if delete_response.pending_action is not None:
            checks.append(assistant.confirm_pending_action(delete_response.pending_action))
        checks.append(assistant.respond("task trash").text)
        checks.append(assistant.respond("restore deleted task 1").text)

    joined = "\n".join(checks)
    required = (
        "Task stats",
        "Due soon",
        "Renamed task 1: call doctor",
        "Updated due date for task 1: call doctor",
        "Cleared due date for task 1: call doctor",
        "Restored task 1: call doctor",
        "Please confirm: Delete task 1",
        "Done: Moved task 1 to trash: call doctor.",
        "Task trash:",
        "Restored deleted task 1: call doctor",
    )
    missing = [phrase for phrase in required if phrase not in joined]
    if missing:
        print("ERROR: Expanded task commands are missing expected text:")
        for phrase in missing:
            print(f"- {phrase}")
        print(joined)
        return 1

    print(joined)
    print("OK: Expanded task commands are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
