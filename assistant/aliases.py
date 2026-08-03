"""Voice-friendly command aliases for the local assistant.

Aliases only rewrite text into commands the assistant already understands.
They do not execute anything by themselves.
"""

from __future__ import annotations

import json
from pathlib import Path

from assistant.actions import ActionError, parse_action


DEFAULT_ALIASES_PATH = Path("config/aliases.json")

BUILTIN_ALIAS_TARGETS = {
    "about",
    "about assistant",
    "action audit",
    "actions",
    "all tasks",
    "backups",
    "bye",
    "architecture",
    "briefing",
    "clear history",
    "commands",
    "command list",
    "command reference",
    "daily briefing",
    "data report",
    "date",
    "delete memory",
    "delete task",
    "deleted memories",
    "deleted tasks",
    "done tasks",
    "due soon",
    "exit",
    "export data",
    "export safety reviews",
    "export signed reviews",
    "forget memories",
    "full help",
    "good morning",
    "hello",
    "help",
    "hey",
    "hi",
    "history",
    "memory",
    "memories",
    "memory trash",
    "next steps",
    "notes",
    "local data",
    "local backup",
    "list backups",
    "list models",
    "launch commands",
    "local models",
    "models",
    "ollama models",
    "rename memory",
    "restore memory",
    "overdue",
    "overdue tasks",
    "paths",
    "file paths",
    "data paths",
    "where is my data",
    "quit",
    "roadmap",
    "restore task",
    "restore deleted task",
    "reopen task",
    "project roadmap",
    "what next",
    "start commands",
    "startup commands",
    "how do i launch",
    "privacy report",
    "privacy",
    "backup data",
    "settings",
    "security",
    "safety",
    "shell review checklist",
    "verify shell checklist",
    "permissions",
    "search notes",
    "status",
    "show history",
    "show memories",
    "show backups",
    "show notes",
    "show tasks",
    "tasks",
    "tasks due today",
    "tasks due soon",
    "task history",
    "task trash",
    "task stats",
    "task summary",
    "todo stats",
    "health",
    "system status",
    "system architecture",
    "time",
    "upcoming",
    "upcoming tasks",
    "speech confidence",
    "export voice audit",
    "voice action audit",
    "voice audit",
    "voice audit confidence low",
    "voice audit event action_preview",
    "voice audit retention keep 100",
    "prune voice audit keep 100",
    "voice confidence",
    "voice confidence status",
    "voice drill",
    "voice safety drill",
    "voice setup",
    "voice status",
    "check voice",
    "what can you do",
}


class AliasError(RuntimeError):
    """Raised when aliases cannot be loaded or validated."""


def default_aliases() -> dict[str, str]:
    return {
        "recent conversation": "history",
        "show action log": "action audit",
        "show me what you know": "memories",
        "show saved memories": "memories",
    }


def normalize_alias_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def load_aliases(path: str | Path = DEFAULT_ALIASES_PATH) -> dict[str, str]:
    aliases_path = Path(path)
    if not aliases_path.exists():
        return default_aliases()

    try:
        raw = json.loads(aliases_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise AliasError(f"Invalid aliases JSON: {aliases_path}") from exc
    except OSError as exc:
        raise AliasError(f"Could not read aliases file: {aliases_path}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("aliases"), dict):
        raise AliasError("Aliases file must contain an 'aliases' object.")

    aliases: dict[str, str] = {}
    for alias, target in raw["aliases"].items():
        if not isinstance(alias, str) or not isinstance(target, str):
            raise AliasError("Alias names and targets must be strings.")
        clean_alias = normalize_alias_text(alias)
        clean_target = validate_alias_target(target)
        if not clean_alias:
            raise AliasError("Alias cannot be empty.")
        aliases[clean_alias] = clean_target
    return aliases


def save_aliases(
    aliases: dict[str, str],
    path: str | Path = DEFAULT_ALIASES_PATH,
) -> None:
    aliases_path = Path(path)
    validated: dict[str, str] = {}
    for alias, target in aliases.items():
        clean_alias = normalize_alias_text(alias)
        if not clean_alias:
            raise AliasError("Alias cannot be empty.")
        validated[clean_alias] = validate_alias_target(target)

    aliases_path.parent.mkdir(parents=True, exist_ok=True)
    aliases_path.write_text(
        json.dumps({"aliases": dict(sorted(validated.items()))}, indent=2) + "\n",
        encoding="utf-8",
    )


def add_alias(
    alias: str,
    target: str,
    path: str | Path = DEFAULT_ALIASES_PATH,
) -> dict[str, str]:
    aliases = load_aliases(path)
    clean_alias = normalize_alias_text(alias)
    if not clean_alias:
        raise AliasError("Alias cannot be empty.")
    aliases[clean_alias] = validate_alias_target(target)
    save_aliases(aliases, path)
    return aliases


def resolve_alias(
    user_text: str,
    path: str | Path = DEFAULT_ALIASES_PATH,
) -> str:
    normalized = normalize_alias_text(user_text)
    if not normalized:
        return user_text
    return load_aliases(path).get(normalized, user_text.strip())


def validate_alias_target(target: str) -> str:
    clean_target = normalize_alias_text(target)
    if not clean_target:
        raise AliasError("Alias target cannot be empty.")

    if clean_target in BUILTIN_ALIAS_TARGETS:
        return clean_target

    try:
        action = parse_action(clean_target)
    except ActionError as exc:
        raise AliasError(f"Alias target is not a valid safe command: {exc}") from exc

    if action is None:
        raise AliasError(
            "Alias target must be a built-in command or an allowlisted app/folder action."
        )
    return clean_target
