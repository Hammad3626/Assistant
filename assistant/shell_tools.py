"""Confirmation-gated local command runner for named safe shell commands."""

from __future__ import annotations

import json
import hashlib
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


DEFAULT_SHELL_COMMANDS_PATH = Path("config/shell_commands.json")
DEFAULT_SHELL_CHECKLIST_DIR = Path("exports/shell-review-checklists")
SHELL_REVIEW_SCHEMA = "safe_shell_review_v1"
SHELL_CHECKLIST_SCHEMA = "safe_shell_operator_checklist_v1"
MAX_OUTPUT_CHARS = 4_000
DEFAULT_TIMEOUT_SECONDS = 15
DENIED_EXECUTABLES = {
    "cmd",
    "cmd.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "reg",
    "reg.exe",
    "regedit",
    "regedit.exe",
    "wscript",
    "wscript.exe",
    "cscript",
    "cscript.exe",
}
DENIED_TOKENS = {
    "&",
    "|",
    ";",
    ">",
    "<",
    "&&",
    "||",
    "del",
    "erase",
    "format",
    "move-item",
    "rd",
    "remove-item",
    "ren",
    "rename-item",
    "restart-computer",
    "rmdir",
    "rm",
    "shutdown",
    "start-process",
    "stop-process",
}
INLINE_CODE_FLAGS = {"-c", "/c", "--command", "-command"}


class ShellToolError(RuntimeError):
    """Raised when a named shell command is invalid or cannot run safely."""


@dataclass(frozen=True)
class SafeShellCommand:
    name: str
    argv: tuple[str, ...]

    def display(self) -> str:
        return " ".join(self.argv)


@dataclass(frozen=True)
class ShellRiskProfile:
    level: str
    score: int
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class ShellReviewChecklistResult:
    summary: str
    checklist_dir: Path
    manifest_path: Path
    checklist_path: Path


@dataclass(frozen=True)
class ShellReviewChecklistVerification:
    summary: str
    checklist_dir: Path | None
    status: str


def default_shell_commands() -> dict[str, list[str]]:
    return {
        "python version": ["python", "--version"],
        "pip version": ["python", "-m", "pip", "--version"],
        "ollama version": ["ollama", "--version"],
    }


def normalize_shell_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def load_shell_commands(path: str | Path = DEFAULT_SHELL_COMMANDS_PATH) -> dict[str, SafeShellCommand]:
    commands_path = Path(path)
    if not commands_path.exists():
        raw_commands = default_shell_commands()
    else:
        try:
            raw = json.loads(commands_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise ShellToolError(f"Invalid shell commands JSON: {commands_path}") from exc
        except OSError as exc:
            raise ShellToolError(f"Could not read shell command allowlist: {commands_path}") from exc

        if not isinstance(raw, dict) or not isinstance(raw.get("commands"), dict):
            raise ShellToolError("Shell command allowlist must contain a 'commands' object.")
        raw_commands = raw["commands"]

    commands: dict[str, SafeShellCommand] = {}
    for name, argv in raw_commands.items():
        if not isinstance(name, str) or not isinstance(argv, list):
            raise ShellToolError("Shell command names must be strings and values must be arrays.")
        clean_name = normalize_shell_name(name)
        if not clean_name:
            raise ShellToolError("Shell command name cannot be empty.")
        clean_argv = _validate_argv(argv)
        commands[clean_name] = SafeShellCommand(clean_name, tuple(clean_argv))
    return commands


def save_shell_commands(
    commands: dict[str, SafeShellCommand],
    path: str | Path = DEFAULT_SHELL_COMMANDS_PATH,
    review_metadata: dict[str, object] | None = None,
) -> None:
    """Save validated named commands to the local allowlist."""
    commands_path = Path(path)
    payload: dict[str, list[str]] = {}
    for name, command in commands.items():
        clean_name = normalize_shell_name(name)
        if not clean_name:
            raise ShellToolError("Shell command name cannot be empty.")
        payload[clean_name] = _validate_argv(list(command.argv))

    reviews = _load_existing_reviews(commands_path)
    if review_metadata is not None:
        reviews.append(review_metadata)

    commands_path.parent.mkdir(parents=True, exist_ok=True)
    commands_path.write_text(
        json.dumps({"commands": dict(sorted(payload.items())), "reviews": reviews}, indent=2) + "\n",
        encoding="utf-8",
    )


def add_shell_command(
    name: str,
    argv: list[str],
    path: str | Path = DEFAULT_SHELL_COMMANDS_PATH,
) -> SafeShellCommand:
    """Add or update one validated safe shell command."""
    clean_name = normalize_shell_name(name)
    if not clean_name:
        raise ShellToolError("Shell command name cannot be empty.")
    clean_argv = tuple(_validate_argv(argv))

    commands = load_shell_commands(path)
    command = SafeShellCommand(clean_name, clean_argv)
    commands[clean_name] = command
    save_shell_commands(commands, path, _build_shell_review_metadata("add", command))
    return command


def shell_command_static_review_notes(command: SafeShellCommand) -> str:
    """Return static review notes for a saved command without running it."""
    executable_name = Path(command.argv[0]).name.lower()
    risk = shell_command_risk_profile(command)
    notes = [
        "Static review notes",
        "- Saved only: this review did not run the command.",
        "- Validation passed: no shell executable, inline code, pipes, redirection, or chaining were detected.",
        f"- Static risk score: {risk.level} ({risk.score}/10).",
        "- Execution gate: running this command still requires 'run shell <name>' and confirmation.",
    ]
    notes.extend(f"- Risk reason: {reason}" for reason in risk.reasons)
    if executable_name in {"python", "python.exe", "py", "py.exe"}:
        notes.append("- Python review: inline code is blocked; review any module arguments before running.")
    elif executable_name in {"pip", "pip.exe"} or "pip" in command.argv:
        notes.append("- Package tool review: inspect arguments carefully because package tools can modify environments.")
    elif executable_name in {"ollama", "ollama.exe"}:
        notes.append("- Ollama review: local model commands can use CPU, memory, disk, or local network service time.")
    elif "." in executable_name:
        notes.append("- Executable review: verify this executable path/name is the program you intended.")
    else:
        notes.append("- Executable review: verify this command is a simple local diagnostic before running.")
    if len(command.argv) == 1:
        notes.append("- Argument review: no arguments were configured.")
    else:
        notes.append(f"- Argument review: {len(command.argv) - 1} argument(s) configured.")
    return "\n".join(notes)


def shell_command_risk_profile(command: SafeShellCommand) -> ShellRiskProfile:
    """Return deterministic static review risk for a validated command without running it."""
    executable_name = Path(command.argv[0]).name.lower()
    argv_lower = [arg.lower() for arg in command.argv]
    score = 1
    reasons = ["Command passed the safe argv validator."]

    if len(command.argv) > 3:
        score += 1
        reasons.append("Command has multiple arguments, so review intent carefully.")
    if any(arg in {"--version", "-v", "version"} for arg in argv_lower):
        reasons.append("Version-style diagnostic commands are usually low risk.")
    elif any(arg in {"list", "show", "status", "info", "help", "--help", "-h"} for arg in argv_lower):
        score += 1
        reasons.append("Read-style diagnostic command; still review output and target.")
    else:
        score += 2
        reasons.append("Command is not an obvious version/status diagnostic.")

    if executable_name in {"pip", "pip.exe"} or "pip" in argv_lower:
        score += 2
        reasons.append("Package tools can modify local environments.")
    if executable_name in {"ollama", "ollama.exe"}:
        score += 2
        reasons.append("Ollama commands can use local model, CPU, memory, disk, or service time.")
    if executable_name in {"python", "python.exe", "py", "py.exe"} and "-m" in argv_lower:
        score += 1
        reasons.append("Python module execution can do more than a simple executable version check.")
    if "\\" in command.argv[0] or "/" in command.argv[0]:
        score += 1
        reasons.append("Executable is path-based; verify it is the intended local program.")

    score = min(score, 10)
    if score <= 3:
        level = "low"
    elif score <= 6:
        level = "medium"
    else:
        level = "high"
    return ShellRiskProfile(level, score, tuple(reasons))


def latest_shell_review_metadata(
    path: str | Path,
    action: str,
    command: SafeShellCommand,
) -> dict[str, object] | None:
    """Return the latest matching signed review metadata for a command change."""
    reviews = _load_existing_reviews(Path(path))
    expected = {
        "action": action,
        "command_name": command.name,
        "argv": list(command.argv),
    }
    for review in reversed(reviews):
        if all(review.get(key) == value for key, value in expected.items()):
            return review
    return None


def shell_command_signed_review_text(metadata: dict[str, object] | None) -> str:
    """Return user-facing signed review metadata details."""
    if metadata is None:
        return "Signed review metadata: not found."
    signature = metadata.get("review_signature")
    created_at = metadata.get("created_at")
    action = metadata.get("action")
    risk = metadata.get("static_risk")
    if not isinstance(signature, str) or not signature:
        return "Signed review metadata: invalid."
    risk_line = "- Static risk: not recorded."
    if isinstance(risk, dict):
        level = risk.get("level")
        score = risk.get("score")
        if isinstance(level, str) and isinstance(score, int):
            risk_line = f"- Static risk: {level} ({score}/10)."
    return "\n".join(
        [
            "Signed review metadata",
            f"- Action: {action}",
            f"- Created: {created_at}",
            risk_line,
            f"- Signature: {signature}",
            "- Purpose: tamper-evident local review record; it does not run the command.",
        ]
    )


def shell_review_records(path: str | Path = DEFAULT_SHELL_COMMANDS_PATH) -> list[dict[str, object]]:
    """Return saved shell allowlist review metadata without running commands."""
    return _load_existing_reviews(Path(path))


def shell_review_signature_valid(metadata: dict[str, object]) -> bool:
    """Return whether a saved shell review metadata signature matches its contents."""
    signature = metadata.get("review_signature")
    return isinstance(signature, str) and signature == _shell_review_signature(metadata)


def create_shell_review_checklist(
    name: str,
    commands_path: str | Path = DEFAULT_SHELL_COMMANDS_PATH,
    output_dir: str | Path = DEFAULT_SHELL_CHECKLIST_DIR,
) -> ShellReviewChecklistResult:
    """Create a local operator checklist for an allowlisted shell command without running it."""
    command = get_shell_command(name, commands_path)
    risk = shell_command_risk_profile(command)
    latest_add_review = latest_shell_review_metadata(commands_path, "add", command)
    checklist_dir = _create_shell_checklist_dir(Path(output_dir), command.name)
    manifest = {
        "schema": SHELL_CHECKLIST_SCHEMA,
        "created_at": _utc_now_iso(),
        "command_name": command.name,
        "argv": list(command.argv),
        "execution_enabled": False,
        "runs_command": False,
        "static_risk": risk.as_dict(),
        "latest_add_review": latest_add_review,
        "checklist": _shell_operator_checklist_items(risk),
        "notes": [
            "This checklist is for human review only.",
            "Creating this checklist does not run the command.",
            "Running the command still requires run shell <name> and confirmation.",
        ],
    }
    manifest["checklist_signature"] = _shell_checklist_signature(manifest)
    manifest_path = checklist_dir / "manifest.json"
    checklist_path = checklist_dir / "checklist.md"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    checklist_path.write_text(_shell_operator_checklist_markdown(manifest), encoding="utf-8")

    summary = "\n".join(
        [
            "Shell operator checklist created",
            "No shell command was run.",
            f"Command: {command.name}: {command.display()}",
            f"Static risk: {risk.level} ({risk.score}/10)",
            f"Checklist folder: {checklist_dir}",
            "Files: checklist.md, manifest.json",
        ]
    )
    return ShellReviewChecklistResult(summary, checklist_dir, manifest_path, checklist_path)


def verify_shell_review_checklist(
    name: str,
    commands_path: str | Path = DEFAULT_SHELL_COMMANDS_PATH,
    output_dir: str | Path = DEFAULT_SHELL_CHECKLIST_DIR,
) -> ShellReviewChecklistVerification:
    """Verify the latest local operator checklist for a command without running it."""
    command = get_shell_command(name, commands_path)
    checklist_dir, manifest = _latest_shell_checklist_manifest(command.name, Path(output_dir))
    if checklist_dir is None or manifest is None:
        return ShellReviewChecklistVerification(
            summary=f"Shell checklist verification blocked: no checklist found for {command.name}.",
            checklist_dir=None,
            status="blocked",
        )

    status = "verified"
    notes = ["No shell command was run."]
    if manifest.get("schema") != SHELL_CHECKLIST_SCHEMA:
        status = "blocked"
        notes.append("Checklist schema is not recognized.")
    if manifest.get("execution_enabled") is not False or manifest.get("runs_command") is not False:
        status = "blocked"
        notes.append("Checklist must keep execution_enabled and runs_command false.")
    if manifest.get("command_name") != command.name or manifest.get("argv") != list(command.argv):
        status = "blocked"
        notes.append("Checklist command no longer matches the current allowlist.")
    recorded_signature = manifest.get("checklist_signature")
    if not isinstance(recorded_signature, str) or recorded_signature != _shell_checklist_signature(manifest):
        status = "blocked"
        notes.append("Checklist signature mismatch.")
    checklist_items = manifest.get("checklist")
    if not isinstance(checklist_items, list) or not checklist_items:
        status = "blocked"
        notes.append("Checklist has no review items.")
    if status == "verified":
        notes.append("Checklist signature matches.")
        notes.append("Checklist no-run flags are intact.")
        notes.append("Checklist command matches the current allowlist.")

    lines = [
        "Shell checklist verification",
        f"Status: {status}",
        f"Command: {command.name}: {command.display()}",
        f"Checklist folder: {checklist_dir}",
        "Verification notes:",
    ]
    lines.extend(f"- {note}" for note in notes)
    lines.append("This does not grant permission or run the command.")
    return ShellReviewChecklistVerification("\n".join(lines), checklist_dir, status)


def remove_shell_command(
    name: str,
    path: str | Path = DEFAULT_SHELL_COMMANDS_PATH,
) -> SafeShellCommand:
    """Remove one named safe shell command from the local allowlist."""
    commands = load_shell_commands(path)
    clean_name = normalize_shell_name(name)
    if not clean_name:
        raise ShellToolError("Shell command name cannot be empty.")
    command = commands.pop(clean_name, None)
    if command is None:
        allowed = ", ".join(sorted(commands)) or "none"
        raise ShellToolError(f"Shell command must be one of: {allowed}")
    save_shell_commands(commands, path, _build_shell_review_metadata("remove", command))
    return command


def parse_shell_command_request(text: str) -> tuple[str, list[str]]:
    """Parse '<name>: <executable> [args...]' for guided allowlist editing."""
    name, separator, argv_text = text.partition(":")
    if not separator:
        raise ShellToolError("Add shell command expects: add shell command <name>: <executable> [args...]")
    clean_name = normalize_shell_name(name)
    if not clean_name:
        raise ShellToolError("Shell command name cannot be empty.")
    argv = argv_text.strip().split()
    if not argv:
        raise ShellToolError("Shell command argv cannot be empty.")
    return clean_name, argv


def shell_command_wizard_text(path: str | Path = DEFAULT_SHELL_COMMANDS_PATH) -> str:
    """Return guided instructions for safely editing the shell allowlist."""
    return "\n".join(
        [
            "Safe shell command wizard",
            "This wizard adds or updates one named command in the local allowlist.",
            "Reply with:",
            "name: executable arg1 arg2",
            "Example:",
            "python version check: python --version",
            "Rules:",
            "- The command is saved only; it is not run.",
            "- Static review notes are shown after saving.",
            "- Static risk scoring is shown and saved for local audit.",
            "- Signed review metadata is saved for allowlist changes.",
            "- Running later still requires: run shell <name>, then confirmation.",
            "- Shells, scripts, inline code, pipes, redirection, chaining, and destructive commands are blocked.",
            "- Type cancel to leave the wizard.",
            "",
            shell_commands_summary(path),
        ]
    )


def shell_commands_summary(path: str | Path = DEFAULT_SHELL_COMMANDS_PATH) -> str:
    commands = load_shell_commands(path)
    if not commands:
        return "No safe shell commands are configured."

    lines = [
        "Safe shell commands",
        "Only named allowlisted commands can run, and each run requires confirmation.",
    ]
    for name in sorted(commands):
        lines.append(f"- {name}: {commands[name].display()}")
    return "\n".join(lines)


def _load_existing_reviews(commands_path: Path) -> list[dict[str, object]]:
    if not commands_path.exists():
        return []
    try:
        raw = json.loads(commands_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return []
    reviews = raw.get("reviews") if isinstance(raw, dict) else None
    if not isinstance(reviews, list):
        return []
    return [review for review in reviews if isinstance(review, dict)]


def _build_shell_review_metadata(action: str, command: SafeShellCommand) -> dict[str, object]:
    risk = shell_command_risk_profile(command)
    metadata: dict[str, object] = {
        "schema": SHELL_REVIEW_SCHEMA,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "action": action,
        "command_name": command.name,
        "argv": list(command.argv),
        "static_risk": risk.as_dict(),
        "review_notes": [
            "Allowlist edit only; command was not run.",
            "Command argv passed safe shell validation.",
            f"Static risk score: {risk.level} ({risk.score}/10).",
            "Running this command still requires explicit confirmation.",
        ],
    }
    metadata["review_signature"] = _shell_review_signature(metadata)
    return metadata


def _shell_operator_checklist_items(risk: ShellRiskProfile) -> list[str]:
    items = [
        "Confirm the executable name and path are the intended local program.",
        "Confirm every argument is necessary and written as argv, not shell text.",
        "Confirm the command does not send messages, emails, or network requests on your behalf.",
        "Confirm the command does not delete, move, rename, overwrite, or bulk-edit files.",
        "Confirm the command does not launch a shell, script host, registry tool, or inline code.",
        "Confirm the command still requires run shell <name> and explicit confirmation before execution.",
    ]
    if risk.level in {"medium", "high"}:
        items.append("Because risk is not low, get a second manual review before running.")
    if risk.level == "high":
        items.append("Because risk is high, prefer replacing this with a narrower diagnostic command.")
    return items


def _shell_operator_checklist_markdown(manifest: dict[str, object]) -> str:
    risk = manifest.get("static_risk")
    risk_text = "unknown"
    if isinstance(risk, dict):
        risk_text = f"{risk.get('level', 'unknown')} ({risk.get('score', '?')}/10)"
    lines = [
        "# Shell Operator Checklist",
        "",
        f"Command: {manifest.get('command_name')}",
        f"Argv: {' '.join(str(item) for item in manifest.get('argv', []))}",
        f"Static risk: {risk_text}",
        "",
        "This checklist is review-only. It did not run the command.",
        "",
        "## Required Checks",
    ]
    checklist = manifest.get("checklist")
    if isinstance(checklist, list):
        lines.extend(f"- [ ] {item}" for item in checklist)
    lines.extend(
        [
            "",
            "## Final Review",
            "- [ ] I understand this checklist does not grant permission or execute anything.",
            "- [ ] I will only run this with the existing confirmation-gated command path.",
            "",
            f"Checklist signature: {manifest.get('checklist_signature')}",
        ]
    )
    return "\n".join(lines) + "\n"


def _create_shell_checklist_dir(output_dir: Path, command_name: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(char if char.isalnum() else "-" for char in command_name).strip("-") or "command"
    checklist_dir = output_dir / f"shell-checklist-{safe_name}-{timestamp}"
    if checklist_dir.exists():
        checklist_dir = output_dir / f"shell-checklist-{safe_name}-{timestamp}-{uuid4().hex[:8]}"
    checklist_dir.mkdir(parents=True, exist_ok=False)
    return checklist_dir


def _latest_shell_checklist_manifest(
    command_name: str,
    output_dir: Path,
) -> tuple[Path | None, dict[str, object] | None]:
    if not output_dir.exists():
        return None, None
    matches: list[tuple[Path, dict[str, object]]] = []
    for manifest_path in sorted(output_dir.glob("shell-checklist-*/manifest.json")):
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(raw, dict) and raw.get("command_name") == command_name:
            matches.append((manifest_path.parent, raw))
    if not matches:
        return None, None
    return matches[-1]


def _shell_checklist_signature(manifest: dict[str, object]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "checklist_signature"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _shell_review_signature(metadata: dict[str, object]) -> str:
    payload = {key: value for key, value in metadata.items() if key != "review_signature"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_shell_command(name: str, path: str | Path = DEFAULT_SHELL_COMMANDS_PATH) -> SafeShellCommand:
    commands = load_shell_commands(path)
    clean_name = normalize_shell_name(name)
    command = commands.get(clean_name)
    if command is None:
        allowed = ", ".join(sorted(commands)) or "none"
        raise ShellToolError(f"Shell command must be one of: {allowed}")
    return command


def run_shell_command(
    command: SafeShellCommand,
    cwd: str | Path = ".",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Run a validated command without invoking a shell and return captured output."""
    _validate_argv(list(command.argv))
    try:
        result = subprocess.run(
            list(command.argv),
            cwd=Path(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise ShellToolError(f"Command timed out after {timeout_seconds} seconds.") from exc
    except OSError as exc:
        raise ShellToolError(f"Command failed to start: {exc}") from exc

    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    if not output:
        output = "(no output)"
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n(Output truncated.)"
    return (
        f"Shell command finished with exit code {result.returncode}: {command.name}\n"
        f"{output}"
    )


def _validate_argv(argv: list[object]) -> list[str]:
    if not argv:
        raise ShellToolError("Shell command argv cannot be empty.")
    clean_argv: list[str] = []
    for item in argv:
        if not isinstance(item, str):
            raise ShellToolError("Shell command argv entries must be strings.")
        clean = item.strip()
        if not clean:
            raise ShellToolError("Shell command argv entries cannot be empty.")
        lowered = clean.lower()
        if lowered in DENIED_TOKENS or any(token in lowered for token in ("&&", "||")):
            raise ShellToolError(f"Shell command token is not allowed: {clean}")
        if any(char in clean for char in ('"', "'", "&", "|", ";", ">", "<")):
            raise ShellToolError("Shell command arguments cannot contain shell control characters.")
        clean_argv.append(clean)

    executable_name = Path(clean_argv[0]).name.lower()
    if executable_name in DENIED_EXECUTABLES:
        raise ShellToolError(f"Shell executable is not allowed: {executable_name}")
    if executable_name in {"python", "python.exe", "py", "py.exe"}:
        for arg in clean_argv[1:]:
            if arg.lower() in INLINE_CODE_FLAGS:
                raise ShellToolError("Inline Python code is not allowed in safe shell commands.")
    return clean_argv
