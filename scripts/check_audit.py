"""Check local assistant action audit log."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.audit import DEFAULT_AUDIT_PATH, ActionAuditStore, AuditError


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local action audit log.")
    parser.add_argument("--audit-path", default=str(DEFAULT_AUDIT_PATH))
    args = parser.parse_args()

    store = ActionAuditStore(args.audit_path)
    try:
        entries = store.recent(limit=10)
    except AuditError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Action audit health check")
    print(f"Path: {args.audit_path}")
    print(f"Recent entries: {len(entries)}")
    print("OK: Action audit loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

