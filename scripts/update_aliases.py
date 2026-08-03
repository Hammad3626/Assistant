"""Show or update local command aliases."""

from __future__ import annotations

import argparse

from assistant.aliases import DEFAULT_ALIASES_PATH, AliasError, add_alias, load_aliases


def print_aliases(aliases: dict[str, str]) -> None:
    if not aliases:
        print("No aliases configured.")
        return
    for alias, target in sorted(aliases.items()):
        print(f"{alias} -> {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage local assistant aliases.")
    parser.add_argument("--aliases-path", default=str(DEFAULT_ALIASES_PATH))
    parser.add_argument("--show", action="store_true", help="Show configured aliases.")
    parser.add_argument(
        "--add",
        nargs=2,
        metavar=("ALIAS", "TARGET"),
        help="Add an alias, for example: --add \"show memory\" memories",
    )
    args = parser.parse_args()

    try:
        if args.add:
            alias, target = args.add
            aliases = add_alias(alias, target, args.aliases_path)
            print(f"Added alias: {alias} -> {target}")
            print_aliases(aliases)
            return 0

        aliases = load_aliases(args.aliases_path)
        print_aliases(aliases)
        return 0
    except AliasError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
