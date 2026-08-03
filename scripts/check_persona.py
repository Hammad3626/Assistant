"""Validate local assistant persona prompt."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.persona import DEFAULT_PERSONA_PATH, PersonaError, build_system_prompt, load_persona


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local assistant persona.")
    parser.add_argument("--persona-path", default=str(DEFAULT_PERSONA_PATH))
    args = parser.parse_args()

    try:
        persona = load_persona(args.persona_path)
    except PersonaError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Persona health check")
    print(f"Path: {args.persona_path}")
    print(f"Persona characters: {len(persona)}")
    print(f"Final prompt characters: {len(build_system_prompt(persona))}")
    print("OK: Persona loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

