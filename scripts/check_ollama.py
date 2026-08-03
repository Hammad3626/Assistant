"""Health check for local Ollama generation.

This script verifies the exact part needed for Milestone 3: the local Ollama
HTTP API must be reachable and able to generate at least one tiny response.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from assistant.ollama_client import OllamaClient


def ollama_version() -> str:
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:  # pragma: no cover - diagnostic path
        return f"unknown ({exc})"

    output = (result.stdout or result.stderr).strip()
    return output or "unknown"


def list_models(host: str) -> list[str]:
    request = urllib.request.Request(f"{host}/api/tags", method="GET")
    with urllib.request.urlopen(request, timeout=5) as response:
        data = json.loads(response.read().decode("utf-8"))

    return [item["name"] for item in data.get("models", []) if "name" in item]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local Ollama generation.")
    parser.add_argument("--model", default="llama3.2:1b")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument(
        "--num-gpu",
        type=int,
        default=0,
        help="Number of model layers to offload to GPU. Default 0 keeps the check CPU-only.",
    )
    args = parser.parse_args()

    print("Ollama health check", flush=True)
    print(f"Version: {ollama_version()}", flush=True)
    print(f"Host: {args.host}", flush=True)
    print(f"Model: {args.model}", flush=True)
    print(f"GPU offload layers: {args.num_gpu}", flush=True)
    print("Checking installed models...", flush=True)

    try:
        models = list_models(args.host)
    except (TimeoutError, socket.timeout):
        print("ERROR: Ollama API timed out while listing models.")
        print("Fix: restart Ollama, then run this script again.")
        return 1
    except urllib.error.URLError as exc:
        print(f"ERROR: Ollama API is not reachable: {exc}")
        print("Fix: start Ollama, then run this script again.")
        return 1

    print("Installed models:", flush=True)
    for model in models:
        print(f"- {model}", flush=True)

    if args.model not in models:
        print(f"ERROR: Model '{args.model}' is not installed.", flush=True)
        print(
            "Fix: choose one listed above, for example: "
            f"python scripts/check_ollama.py --model {models[0] if models else '<model>'}",
            flush=True,
        )
        return 1

    client = OllamaClient(
        model=args.model,
        host=args.host,
        timeout_seconds=20,
        num_predict=8,
        num_gpu=args.num_gpu,
    )

    print("Testing a tiny generation request...", flush=True)
    try:
        answer = client.generate("Say OK only.")
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        print("Fixes to try:")
        print("1. Restart Ollama from the Windows tray icon or Task Manager.")
        print("2. Close memory-heavy apps and retry.")
        print("3. Try a tiny installed model with --model smollm2:135m.")
        print("4. If tiny models crash too, update/reinstall Ollama.")
        return 1

    print(f"Generation response: {answer}")
    print("OK: Ollama generation is working.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
