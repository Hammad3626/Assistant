"""Local Ollama model management helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import replace

from assistant.settings import (
    AssistantSettings,
    SettingsError,
    load_settings,
    save_settings,
)


class ModelToolError(RuntimeError):
    """Raised when local model discovery or settings update fails."""


def list_ollama_models(host: str = "http://127.0.0.1:11434") -> list[str]:
    request = urllib.request.Request(f"{host}/api/tags", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise ModelToolError("Ollama is not reachable.") from exc
    except json.JSONDecodeError as exc:
        raise ModelToolError("Ollama returned invalid JSON.") from exc

    models = [item["name"] for item in data.get("models", []) if "name" in item]
    return sorted(models)


def update_default_model(
    model: str,
    settings_path: str = "config/settings.json",
    host: str = "http://127.0.0.1:11434",
    num_gpu: int | None = None,
) -> AssistantSettings:
    installed_models = list_ollama_models(host)
    if model not in installed_models:
        available = ", ".join(installed_models) if installed_models else "none"
        raise ModelToolError(f"Model is not installed: {model}. Available: {available}")

    try:
        settings = load_settings(settings_path)
        updates = {"model": model}
        if num_gpu is not None:
            updates["num_gpu"] = num_gpu
        updated = replace(settings, **updates)
        save_settings(updated, settings_path)
    except SettingsError as exc:
        raise ModelToolError(str(exc)) from exc

    return updated

