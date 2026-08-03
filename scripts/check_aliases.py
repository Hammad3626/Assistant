"""Check the local command aliases file."""

from __future__ import annotations

import argparse

from assistant.aliases import DEFAULT_ALIASES_PATH, AliasError, load_aliases


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local assistant aliases.")
    parser.add_argument("--aliases-path", default=str(DEFAULT_ALIASES_PATH))
    args = parser.parse_args()

    print("Local PC Assistant alias check")
    print(f"Path: {args.aliases_path}")
    try:
        aliases = load_aliases(args.aliases_path)
    except AliasError as exc:
        print(f"ERROR: {exc}")
        return 1

    if not aliases:
        print("No aliases configured.")
    else:
        print("Aliases:")
        for alias, target in sorted(aliases.items()):
            print(f"- {alias} -> {target}")

    print("OK: Aliases are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
