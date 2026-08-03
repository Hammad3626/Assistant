"""Check explicit local assistant memory."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.core import LocalAssistant
from assistant.memory import DEFAULT_MEMORY_PATH, MemoryError, MemoryStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local assistant memory.")
    parser.add_argument("--memory-path", default=str(DEFAULT_MEMORY_PATH))
    args = parser.parse_args()

    store = MemoryStore(args.memory_path)
    try:
        memories = store.list_memories()
    except MemoryError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Memory health check")
    print(f"Path: {args.memory_path}")
    print(f"Saved memories: {len(memories)}")
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_store = MemoryStore(Path(temp_dir) / "memory.json")
        assistant = LocalAssistant(use_llm=False, memory_store=temp_store)
        assistant.respond("remember test preference")
        renamed = assistant.respond("rename memory 1 to updated preference")
        delete_response = assistant.respond("delete memory 1")
        if delete_response.pending_action is None:
            print("ERROR: Memory delete did not require confirmation.")
            return 1
        deleted = assistant.confirm_pending_action(delete_response.pending_action)
        trash = assistant.respond("memory trash")
        restored = assistant.respond("restore memory 1")
        if "Renamed memory 1" not in renamed.text:
            print("ERROR: Memory rename command failed.")
            return 1
        if "Moved memory 1 to trash" not in deleted or "Memory trash:" not in trash.text:
            print("ERROR: Memory trash flow failed.")
            return 1
        if "Restored memory 1" not in restored.text:
            print("ERROR: Memory restore command failed.")
            return 1
    print("OK: Memory loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
