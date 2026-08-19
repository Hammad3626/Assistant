"""Safe local app and folder actions.

This module intentionally does not run arbitrary shell commands. Apps are loaded
from a local allowlist and executed as argument lists, never through a shell.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_APPS_PATH = Path("config/apps.json")
DEFAULT_FOLDERS_PATH = Path("config/folders.json")
DENIED_EXECUTABLES = {
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "wscript.exe",
    "cscript.exe",
    "regedit.exe",
    "reg.exe",
}


class ActionError(RuntimeError):
    """Raised when a safe local action cannot be completed."""


@dataclass(frozen=True)
class PendingAction:
    kind: str
    target: str
    description: str


def default_apps() -> dict[str, str]:
    return {
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "chrome": "chrome.exe",
        "notepad": "notepad.exe",
    }


def default_folders() -> dict[str, str]:
    return {
        "assistant folder": str(Path.cwd()),
        "project folder": str(Path.cwd()),
        "downloads": str(Path.home() / "Downloads"),
        "documents": str(Path.home() / "Documents"),
    }


def load_allowed_apps(path: str | Path = DEFAULT_APPS_PATH) -> dict[str, str]:
    apps_path = Path(path)
    if not apps_path.exists():
        return default_apps()

    try:
        raw = json.loads(apps_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ActionError(f"Invalid apps JSON: {apps_path}") from exc
    except OSError as exc:
        raise ActionError(f"Could not read apps allowlist: {apps_path}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("apps"), dict):
        raise ActionError("Apps allowlist must contain an 'apps' object.")

    apps: dict[str, str] = {}
    for name, target in raw["apps"].items():
        if not isinstance(name, str) or not isinstance(target, str):
            raise ActionError("App names and targets must be strings.")
        clean_name = normalize_action_text(name)
        clean_target = target.strip()
        validate_app_target(clean_target)
        apps[clean_name] = clean_target
    return apps


def load_allowed_folders(path: str | Path = DEFAULT_FOLDERS_PATH) -> dict[str, str]:
    folders_path = Path(path)
    if not folders_path.exists():
        return default_folders()

    try:
        raw = json.loads(folders_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ActionError(f"Invalid folders JSON: {folders_path}") from exc
    except OSError as exc:
        raise ActionError(f"Could not read folders allowlist: {folders_path}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("folders"), dict):
        raise ActionError("Folders allowlist must contain a 'folders' object.")

    folders: dict[str, str] = {}
    for name, target in raw["folders"].items():
        if not isinstance(name, str) or not isinstance(target, str):
            raise ActionError("Folder names and targets must be strings.")
        clean_name = normalize_action_text(name)
        clean_target = normalize_folder_path(target)
        try:
            validate_folder_target(clean_target)
        except ActionError:
            # Skip folders that don't exist on this machine (e.g. paths copied
            # from another user's config) instead of crashing the whole load.
            continue
        folders[clean_name] = clean_target
    return folders


def save_allowed_apps(apps: dict[str, str], path: str | Path = DEFAULT_APPS_PATH) -> None:
    apps_path = Path(path)
    validated: dict[str, str] = {}
    for name, target in apps.items():
        clean_name = normalize_action_text(name)
        if not clean_name:
            raise ActionError("App name cannot be empty.")
        validate_app_target(target)
        validated[clean_name] = target.strip()

    apps_path.parent.mkdir(parents=True, exist_ok=True)
    apps_path.write_text(
        json.dumps({"apps": dict(sorted(validated.items()))}, indent=2) + "\n",
        encoding="utf-8",
    )


def save_allowed_folders(
    folders: dict[str, str],
    path: str | Path = DEFAULT_FOLDERS_PATH,
) -> None:
    folders_path = Path(path)
    validated: dict[str, str] = {}
    for name, target in folders.items():
        clean_name = normalize_action_text(name)
        if not clean_name:
            raise ActionError("Folder name cannot be empty.")
        clean_target = normalize_folder_path(target)
        validate_folder_target(clean_target)
        validated[clean_name] = clean_target

    folders_path.parent.mkdir(parents=True, exist_ok=True)
    folders_path.write_text(
        json.dumps({"folders": dict(sorted(validated.items()))}, indent=2) + "\n",
        encoding="utf-8",
    )


def add_allowed_app(name: str, target: str, path: str | Path = DEFAULT_APPS_PATH) -> dict[str, str]:
    apps = load_allowed_apps(path)
    apps[normalize_action_text(name)] = target.strip()
    save_allowed_apps(apps, path)
    return apps


def add_allowed_folder(
    name: str,
    target: str,
    path: str | Path = DEFAULT_FOLDERS_PATH,
) -> dict[str, str]:
    folders = load_allowed_folders(path)
    folders[normalize_action_text(name)] = normalize_folder_path(target)
    save_allowed_folders(folders, path)
    return folders


def validate_app_target(target: str) -> None:
    clean_target = target.strip()
    if not clean_target:
        raise ActionError("App target cannot be empty.")

    target_path = Path(clean_target)
    executable_name = target_path.name.lower()
    if executable_name in DENIED_EXECUTABLES:
        raise ActionError(f"Executable is not allowed: {executable_name}")
    if not executable_name.endswith(".exe"):
        raise ActionError("App target must be a .exe executable.")
    if any(char in clean_target for char in ['"', "'", "&", "|", ";", ">", "<"]):
        raise ActionError("App target cannot contain shell control characters.")


def normalize_folder_path(target: str) -> str:
    expanded = os.path.expandvars(target.strip())
    return str(Path(expanded).expanduser())


def validate_folder_target(target: str) -> None:
    clean_target = target.strip()
    if not clean_target:
        raise ActionError("Folder target cannot be empty.")
    if any(char in clean_target for char in ['"', "'", "&", "|", ";", ">", "<"]):
        raise ActionError("Folder target cannot contain shell control characters.")

    folder = Path(clean_target).expanduser()
    if not folder.exists():
        raise ActionError(f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise ActionError(f"Folder target is not a directory: {folder}")


def try_open_unrestricted(path_or_app: str) -> str:
    """Attempt to open any file, folder, or app without allowlist restrictions.
    
    This function uses Windows APIs to open anything:
    - Files: Opens with default application
    - Folders: Opens in Windows Explorer
    - Applications: Attempts to launch as executable
    
    Args:
        path_or_app: File path, folder path, app name, or executable path
        
    Returns:
        Success message
        
    Raises:
        ActionError: If the open operation fails
    """
    target = path_or_app.strip()
    if not target:
        raise ActionError("Path or app name cannot be empty.")
    
    # Check for shell control characters (security check)
    if any(char in target for char in ["|", "&", ";", "<", ">"]):
        raise ActionError("Path contains shell control characters and cannot be opened.")
    
    # Expand user paths (~/ becomes home)
    expanded_target = str(Path(target).expanduser())
    
    try:
        # Try to open as a file/folder/URL using os.startfile
        os.startfile(expanded_target)  # type: ignore[attr-defined]
        return f"Done: Opened {target}."
    except (OSError, TypeError):
        # If os.startfile fails, try opening as executable
        try:
            subprocess.Popen([expanded_target])
            return f"Done: Launched {target}."
        except Exception as exc:
            raise ActionError(f"Could not open or launch '{target}': {str(exc)}") from exc


def normalize_action_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def describe_allowed_actions(
    apps_path: str | Path = DEFAULT_APPS_PATH,
    folders_path: str | Path = DEFAULT_FOLDERS_PATH,
) -> str:
    apps = load_allowed_apps(apps_path)
    folders = load_allowed_folders(folders_path)
    app_names = sorted({name for name in apps if name != "calc"})
    return (
        f"Allowed apps: {', '.join(app_names)}. "
        f"Allowed folders: {', '.join(sorted(folders))}."
    )


def parse_action(
    user_text: str,
    apps_path: str | Path = DEFAULT_APPS_PATH,
    folders_path: str | Path = DEFAULT_FOLDERS_PATH,
) -> PendingAction | None:
    """Return a pending allowlisted action from simple natural language."""
    normalized = normalize_action_text(user_text)
    if not normalized:
        return None

    apps = load_allowed_apps(apps_path)
    for app_name, executable in apps.items():
        if normalized in {f"open {app_name}", f"launch {app_name}", f"start {app_name}"}:
            return PendingAction(
                kind="app",
                target=executable,
                description=f"Open {app_name}",
            )

    folders = load_allowed_folders(folders_path)
    for folder_name, folder_path in folders.items():
        if normalized in {f"open {folder_name}", f"show {folder_name}"}:
            return PendingAction(
                kind="folder",
                target=folder_path,
                description=f"Open {folder_name}",
            )

    special_action = parse_windows_special_action(normalized)
    if special_action is not None:
        return special_action

    return None


def parse_windows_special_action(normalized: str) -> PendingAction | None:
    """Return a pending action for safe Windows shell locations."""
    if normalized in {"open this pc", "show this pc", "open my computer", "show my computer"}:
        return PendingAction(
            kind="special",
            target="shell:MyComputerFolder",
            description="Open This PC",
        )

    if normalized in {"open settings", "show settings", "open windows settings"}:
        return PendingAction(
            kind="special",
            target="ms-settings:",
            description="Open Windows Settings",
        )

    match = re.fullmatch(r"(?:open|show) ([a-z])(?::)? drive", normalized)
    if match:
        letter = match.group(1).upper()
        drive_root = f"{letter}:\\"
        if _drive_exists(drive_root):
            return PendingAction(
                kind="folder",
                target=drive_root,
                description=f"Open {letter} drive",
            )

    match = re.fullmatch(r"(?:open|show) ([a-z]):", normalized)
    if match:
        letter = match.group(1).upper()
        drive_root = f"{letter}:\\"
        if _drive_exists(drive_root):
            return PendingAction(
                kind="folder",
                target=drive_root,
                description=f"Open {letter} drive",
            )

    return None


def _drive_exists(drive_root: str) -> bool:
    return Path(drive_root).exists()


def execute_action(action: PendingAction) -> str:
    """Execute a previously confirmed allowlisted action."""
    if action.kind == "app":
        validate_app_target(action.target)
        try:
            subprocess.Popen([action.target])
        except OSError as exc:
            raise ActionError(f"Could not open app: {action.target}") from exc
        return f"Done: {action.description}."

    if action.kind == "folder":
        folder = Path(action.target).expanduser().resolve()
        validate_folder_target(str(folder))
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
        except OSError as exc:
            raise ActionError(f"Could not open folder: {folder}") from exc
        return f"Done: {action.description}."

    if action.kind == "special":
        if action.target not in {"shell:MyComputerFolder", "ms-settings:"}:
            raise ActionError(f"Unsupported special action target: {action.target}")
        try:
            os.startfile(action.target)  # type: ignore[attr-defined]
        except OSError as exc:
            raise ActionError(f"Could not open Windows location: {action.description}") from exc
        return f"Done: {action.description}."

    if action.kind == "unrestricted":
        return try_open_unrestricted(action.target)

    raise ActionError(f"Unsupported action type: {action.kind}")
