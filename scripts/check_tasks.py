"""Check local assistant tasks."""

from __future__ import annotations

import argparse

from assistant.tasks import DEFAULT_TASKS_PATH, TasksError, TasksStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local assistant tasks.")
    parser.add_argument("--tasks-path", default=str(DEFAULT_TASKS_PATH))
    args = parser.parse_args()

    store = TasksStore(args.tasks_path)
    print("Local assistant tasks check")
    print(f"Path: {args.tasks_path}")
    try:
        tasks = store.list_tasks()
    except TasksError as exc:
        print(f"ERROR: {exc}")
        return 1

    open_count = len([task for task in tasks if not task.completed])
    print(f"Tasks: {len(tasks)}")
    print(f"Open tasks: {open_count}")
    print("OK: Tasks loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
