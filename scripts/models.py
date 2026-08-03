"""List local Ollama models and safely set the assistant default model."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.model_tools import ModelToolError, list_ollama_models, update_default_model


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage local Ollama model settings.")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--settings-path", default="config/settings.json")
    parser.add_argument("--list", action="store_true", help="List installed local models.")
    parser.add_argument("--set-default", metavar="MODEL", help="Set default model if installed.")
    parser.add_argument("--num-gpu", type=int, default=None, help="Set GPU offload layers too.")
    args = parser.parse_args()

    try:
        if args.set_default:
            settings = update_default_model(
                args.set_default,
                settings_path=args.settings_path,
                host=args.host,
                num_gpu=args.num_gpu,
            )
            print("Updated default model:")
            print(settings.summary())
            return 0

        models = list_ollama_models(args.host)
    except ModelToolError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Installed Ollama models:")
    for model in models:
        print(f"- {model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

