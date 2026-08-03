"""Local review requests for unlisted apps, scripts, files, and folders.

Requests are intentionally inert: creating a request never runs a program and
never edits the app allowlist. The user can inspect requests and manually decide
whether to add a trusted target later.
"""

from __future__ import annotations

import json
import hashlib
import shlex
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from assistant.actions import ActionError, validate_app_target
from assistant.file_type_allowlist import (
    DEFAULT_FILE_TYPE_ALLOWLIST_PATH,
    FileTypeAllowlistStore,
)


DEFAULT_LAUNCH_REQUESTS_PATH = Path("data/launch_requests.json")
DEFAULT_SCRIPT_CHECKLIST_DIR = Path("exports/script-review-checklists")
DEFAULT_SCRIPT_PREFLIGHT_DIR = Path("exports/script-allowlist-preflights")
DEFAULT_SCRIPT_EXECUTION_READINESS_DIR = Path("exports/script-execution-readiness")
DEFAULT_SCRIPT_RUN_SIMULATION_DIR = Path("exports/script-run-simulations")
DEFAULT_SCRIPT_ALLOWLIST_SIMULATION_DIR = Path("exports/script-allowlist-simulations")
SCRIPT_CHECKLIST_SCHEMA = "script_review_operator_checklist_v1"
SCRIPT_PREFLIGHT_SCHEMA = "script_allowlist_preflight_v1"
SCRIPT_EXECUTION_READINESS_SCHEMA = "script_execution_readiness_v1"
SCRIPT_RUN_SIMULATION_SCHEMA = "script_run_simulation_v1"
SCRIPT_ALLOWLIST_SIMULATION_SCHEMA = "script_allowlist_entry_simulation_v1"
SCRIPT_EXTENSIONS = {".py", ".ps1", ".bat", ".cmd", ".vbs", ".js"}
SCRIPT_INTERPRETER_BY_EXTENSION = {
    ".py": {"python", "python.exe"},
    ".ps1": {"powershell", "powershell.exe", "pwsh", "pwsh.exe"},
    ".bat": {"cmd", "cmd.exe"},
    ".cmd": {"cmd", "cmd.exe"},
    ".vbs": {"cscript", "cscript.exe", "wscript", "wscript.exe"},
    ".js": {"node", "node.exe", "cscript", "cscript.exe", "wscript", "wscript.exe"},
}
SCRIPT_ALLOWLIST_SIMULATION_BLOCKED_INTERPRETERS = {
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "cmd",
    "cmd.exe",
    "cscript",
    "cscript.exe",
    "wscript",
    "wscript.exe",
}
SCRIPT_ALLOWLIST_SIMULATION_BLOCKED_ARGS = {
    "-c",
    "/c",
    "-command",
    "/command",
    "-encodedcommand",
    "/k",
    "-file",
}
EXECUTABLE_EXTENSIONS = {".exe", ".msi", ".msix", ".msixbundle", ".com", ".scr", ".dll", ".sys"}
SHORTCUT_EXTENSIONS = {".lnk", ".url", ".website"}
ARCHIVE_EXTENSIONS = {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".iso"}
DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".docm",
    ".xls",
    ".xlsx",
    ".xlsm",
    ".ppt",
    ".pptx",
    ".pptm",
    ".rtf",
}
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".log",
    ".xml",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".py",
}
MEDIA_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
    ".mp3",
    ".wav",
    ".flac",
    ".mp4",
    ".mov",
    ".mkv",
}
SCRIPT_REVIEW_READ_LIMIT_BYTES = 64_000
SCRIPT_REVIEW_FINDINGS = {
    "destructive file operation": (
        "Remove-Item",
        "rm ",
        "del ",
        "erase ",
        "shutil.rmtree",
        "unlink(",
        "rmdir",
    ),
    "shell or process launch": (
        "Start-Process",
        "subprocess.",
        "os.system",
        "ShellExecute",
        "Popen(",
        "cmd.exe",
        "powershell",
        "pwsh",
        "wscript",
        "cscript",
    ),
    "network access": (
        "Invoke-WebRequest",
        "Invoke-RestMethod",
        "curl ",
        "wget ",
        "requests.",
        "urllib.",
        "socket.",
        "http://",
        "https://",
    ),
    "dynamic code execution": (
        "eval(",
        "exec(",
        "Invoke-Expression",
        "iex ",
    ),
    "registry or policy change": (
        "reg add",
        "reg delete",
        "Set-ExecutionPolicy",
        "New-ItemProperty",
        "Set-ItemProperty",
    ),
}


class LaunchRequestError(RuntimeError):
    """Raised when launch review requests cannot be read or written."""


@dataclass(frozen=True)
class ScriptReviewChecklistResult:
    summary: str
    checklist_dir: Path
    manifest_path: Path
    checklist_path: Path


@dataclass(frozen=True)
class ScriptReviewChecklistVerification:
    summary: str
    checklist_dir: Path | None
    status: str


@dataclass(frozen=True)
class ScriptAllowlistPreflightResult:
    summary: str
    preflight_dir: Path
    manifest_path: Path
    status: str


@dataclass(frozen=True)
class ScriptExecutionReadinessResult:
    summary: str
    readiness_dir: Path
    manifest_path: Path
    status: str


@dataclass(frozen=True)
class ScriptRunSimulationResult:
    summary: str
    simulation_dir: Path
    manifest_path: Path
    status: str


@dataclass(frozen=True)
class ScriptAllowlistEntrySimulationResult:
    summary: str
    simulation_dir: Path
    manifest_path: Path
    status: str


@dataclass(frozen=True)
class LaunchRequest:
    kind: str
    name: str
    target: str
    reason: str
    created_at: str
    file_type_category: str = ""
    file_type_extension: str = ""
    file_type_allowed_for_launch: bool = False
    file_type_risk: str = ""
    file_type_note: str = ""
    script_review_risk: str = ""
    script_review_summary: str = ""

    def display_text(self) -> str:
        reason_text = f" reason: {self.reason}" if self.reason else ""
        file_type_text = ""
        if self.kind == "file" and self.file_type_category:
            file_type_text = (
                f" file-type: {self.file_type_category}"
                f" (ext: {self.file_type_extension}; risk: {self.file_type_risk}; {self.file_type_note};"
                f" launch-eligible: {'yes' if self.file_type_allowed_for_launch else 'no'})"
            )
        script_review_text = ""
        if self.kind == "script" and self.script_review_summary:
            script_review_text = (
                f" static-review: {self.script_review_risk}; {self.script_review_summary}"
            )
        return f"{self.kind} '{self.name}' -> {self.target}{reason_text}{file_type_text}{script_review_text}"


class LaunchRequestStore:
    """Append-only local store for unlisted launch/open review requests."""

    def __init__(
        self,
        path: str | Path = DEFAULT_LAUNCH_REQUESTS_PATH,
        file_type_allowlist_path: str | Path = DEFAULT_FILE_TYPE_ALLOWLIST_PATH,
    ) -> None:
        self.path = Path(path)
        self.file_type_allowlist = FileTypeAllowlistStore(file_type_allowlist_path)

    def request_app(self, name: str, target: str, reason: str = "") -> LaunchRequest:
        clean_name = _clean_required_text(name, "App request name")
        clean_target = _clean_required_text(target, "App target")
        try:
            validate_app_target(clean_target)
        except ActionError as exc:
            raise LaunchRequestError(str(exc)) from exc
        request = LaunchRequest("app", clean_name, clean_target, reason.strip(), _utc_now_iso())
        self._append(request)
        return request

    def request_script_review(self, name: str, target: str, reason: str = "") -> LaunchRequest:
        clean_name = _clean_required_text(name, "Script request name")
        clean_target = _clean_required_text(target, "Script path")
        _validate_script_target(clean_target)
        risk, summary = _static_script_review(clean_target)
        request = LaunchRequest(
            "script",
            clean_name,
            clean_target,
            reason.strip(),
            _utc_now_iso(),
            script_review_risk=risk,
            script_review_summary=summary,
        )
        self._append(request)
        return request

    def request_file_review(self, name: str, target: str, reason: str = "") -> LaunchRequest:
        clean_name = _clean_required_text(name, "File request name")
        clean_target = _clean_required_text(target, "File path")
        path = _validate_file_target(clean_target)
        category, extension, risk, note = _review_file_type(path)
        allowed_for_launch = self.file_type_allowlist.is_allowed_extension(extension)
        launch_note = (
            "file type is explicitly allowlisted for future launch workflows"
            if allowed_for_launch
            else "file type is not allowlisted; future launch workflows remain blocked"
        )
        request = LaunchRequest(
            "file",
            clean_name,
            clean_target,
            reason.strip(),
            _utc_now_iso(),
            file_type_category=category,
            file_type_extension=extension,
            file_type_allowed_for_launch=allowed_for_launch,
            file_type_risk=risk,
            file_type_note=f"{note}; {launch_note}",
        )
        self._append(request)
        return request

    def request_folder_review(self, name: str, target: str, reason: str = "") -> LaunchRequest:
        clean_name = _clean_required_text(name, "Folder request name")
        clean_target = _clean_required_text(target, "Folder path")
        _validate_folder_review_target(clean_target)
        request = LaunchRequest("folder", clean_name, clean_target, reason.strip(), _utc_now_iso())
        self._append(request)
        return request

    def list_requests(self) -> list[LaunchRequest]:
        raw = self._read_raw()
        requests_raw = raw.get("requests", [])
        if not isinstance(requests_raw, list):
            raise LaunchRequestError("Launch requests file has invalid 'requests' value.")

        requests: list[LaunchRequest] = []
        for item in requests_raw:
            if not isinstance(item, dict):
                continue
            request = _request_from_raw(item)
            if request is not None:
                requests.append(request)
        return requests

    def script_review_count(self) -> int:
        """Return the number of saved script review requests."""
        return len([request for request in self.list_requests() if request.kind == "script"])

    def summary(self, limit: int = 10) -> str:
        requests = self.list_requests()
        if not requests:
            return "Launch requests: none. Unlisted apps, scripts, files, and folders are still blocked."

        lines = ["Launch requests (local review only; nothing was run):"]
        for index, request in enumerate(requests[-limit:], start=1):
            lines.append(f"{index}. {request.display_text()} ({request.created_at})")
        if len(requests) > limit:
            lines.append(f"Showing latest {limit} of {len(requests)} request(s).")
        return "\n".join(lines)

    def clear(self) -> int:
        requests = self.list_requests()
        self._write_all([])
        return len(requests)

    def create_script_review_checklist(
        self,
        request_number: int,
        output_dir: str | Path = DEFAULT_SCRIPT_CHECKLIST_DIR,
    ) -> ScriptReviewChecklistResult:
        """Create a review-only script operator checklist without running scripts."""
        request = self._script_request_by_number(request_number)
        checklist_dir = _create_script_checklist_dir(Path(output_dir), request.name)
        static_metadata = _script_file_metadata(request.target)
        manifest: dict[str, object] = {
            "schema": SCRIPT_CHECKLIST_SCHEMA,
            "created_at": _utc_now_iso(),
            "request_number": request_number,
            "request_signature": _launch_request_signature(request),
            "script_name": request.name,
            "script_target": request.target,
            "script_review_risk": request.script_review_risk or "unknown",
            "script_review_summary": request.script_review_summary,
            "static_metadata": static_metadata,
            "execution_enabled": False,
            "runs_script": False,
            "allowlist_enabled": False,
            "checklist": _script_operator_checklist_items(request, static_metadata),
            "notes": [
                "This checklist is for human review only.",
                "Creating this checklist does not run the script.",
                "Creating this checklist does not add a script allowlist entry.",
                "Script execution remains disabled in this build.",
            ],
        }
        manifest["checklist_signature"] = _script_checklist_signature(manifest)
        manifest_path = checklist_dir / "manifest.json"
        checklist_path = checklist_dir / "checklist.md"
        try:
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            checklist_path.write_text(_script_operator_checklist_markdown(manifest), encoding="utf-8")
        except OSError as exc:
            raise LaunchRequestError(f"Could not write script review checklist: {checklist_dir}") from exc

        summary = "\n".join(
            [
                "Script operator checklist created",
                "No script was run.",
                "No script allowlist entry was created.",
                f"Request: {request_number}. {request.display_text()}",
                f"Static risk: {request.script_review_risk or 'unknown'}",
                f"Checklist folder: {checklist_dir}",
                "Files: checklist.md, manifest.json",
            ]
        )
        return ScriptReviewChecklistResult(summary, checklist_dir, manifest_path, checklist_path)

    def verify_script_review_checklist(
        self,
        request_number: int,
        output_dir: str | Path = DEFAULT_SCRIPT_CHECKLIST_DIR,
    ) -> ScriptReviewChecklistVerification:
        """Verify the latest script checklist for a review request without running scripts."""
        request = self._script_request_by_number(request_number)
        checklist_dir, manifest = _latest_script_checklist_manifest(
            _launch_request_signature(request),
            Path(output_dir),
        )
        if checklist_dir is None or manifest is None:
            return ScriptReviewChecklistVerification(
                summary=f"Script checklist verification blocked: no checklist found for request {request_number}.",
                checklist_dir=None,
                status="blocked",
            )

        status = "verified"
        notes = ["No script was run.", "No script allowlist entry was created."]
        if manifest.get("schema") != SCRIPT_CHECKLIST_SCHEMA:
            status = "blocked"
            notes.append("Checklist schema is not recognized.")
        if (
            manifest.get("execution_enabled") is not False
            or manifest.get("runs_script") is not False
            or manifest.get("allowlist_enabled") is not False
        ):
            status = "blocked"
            notes.append("Checklist must keep execution_enabled, runs_script, and allowlist_enabled false.")
        if manifest.get("request_signature") != _launch_request_signature(request):
            status = "blocked"
            notes.append("Checklist no longer matches the selected script review request.")
        recorded_signature = manifest.get("checklist_signature")
        if not isinstance(recorded_signature, str) or recorded_signature != _script_checklist_signature(manifest):
            status = "blocked"
            notes.append("Checklist signature mismatch.")
        checklist_items = manifest.get("checklist")
        if not isinstance(checklist_items, list) or not checklist_items:
            status = "blocked"
            notes.append("Checklist has no review items.")
        if status == "verified":
            notes.append("Checklist signature matches.")
            notes.append("Checklist no-run and no-allowlist flags are intact.")
            notes.append("Checklist matches the selected script review request.")

        lines = [
            "Script checklist verification",
            f"Status: {status}",
            f"Request: {request_number}. {request.display_text()}",
            f"Checklist folder: {checklist_dir}",
            "Verification notes:",
        ]
        lines.extend(f"- {note}" for note in notes)
        lines.append("This does not grant permission, add an allowlist entry, or run the script.")
        return ScriptReviewChecklistVerification("\n".join(lines), checklist_dir, status)

    def create_script_allowlist_preflight(
        self,
        request_number: int,
        checklist_dir: str | Path = DEFAULT_SCRIPT_CHECKLIST_DIR,
        output_dir: str | Path = DEFAULT_SCRIPT_PREFLIGHT_DIR,
    ) -> ScriptAllowlistPreflightResult:
        """Create a signed review-only preflight before any future script allowlist."""
        request = self._script_request_by_number(request_number)
        verification = self.verify_script_review_checklist(request_number, output_dir=checklist_dir)
        static_metadata = _script_file_metadata(request.target)
        status, notes = _script_allowlist_preflight_status(verification, static_metadata)
        preflight_dir = _create_script_preflight_dir(Path(output_dir), request.name)
        manifest: dict[str, object] = {
            "schema": SCRIPT_PREFLIGHT_SCHEMA,
            "created_at": _utc_now_iso(),
            "status": status,
            "request_number": request_number,
            "request_signature": _launch_request_signature(request),
            "script_name": request.name,
            "script_target": request.target,
            "script_review_risk": request.script_review_risk or "unknown",
            "script_review_summary": request.script_review_summary,
            "static_metadata": static_metadata,
            "checklist_status": verification.status,
            "checklist_dir": str(verification.checklist_dir) if verification.checklist_dir else "",
            "execution_enabled": False,
            "runs_script": False,
            "allowlist_enabled": False,
            "preflight_notes": notes,
        }
        manifest["preflight_signature"] = _script_preflight_signature(manifest)
        manifest_path = preflight_dir / "manifest.json"
        try:
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            raise LaunchRequestError(f"Could not write script allowlist preflight: {preflight_dir}") from exc

        summary = "\n".join(
            [
                "Script allowlist preflight created",
                f"Preflight status: {status}",
                "No script was run.",
                "No script allowlist entry was created.",
                f"Request: {request_number}. {request.display_text()}",
                f"Checklist status: {verification.status}",
                f"Preflight folder: {preflight_dir}",
                "Manifest: manifest.json",
                "Preflight notes:",
                *[f"- {note}" for note in notes],
            ]
        )
        return ScriptAllowlistPreflightResult(summary, preflight_dir, manifest_path, status)

    def create_script_execution_readiness_bundle(
        self,
        request_number: int,
        checklist_dir: str | Path = DEFAULT_SCRIPT_CHECKLIST_DIR,
        preflight_dir: str | Path = DEFAULT_SCRIPT_PREFLIGHT_DIR,
        output_dir: str | Path = DEFAULT_SCRIPT_EXECUTION_READINESS_DIR,
    ) -> ScriptExecutionReadinessResult:
        """Create a signed no-run execution-readiness bundle for a script review request."""
        request = self._script_request_by_number(request_number)
        verification = self.verify_script_review_checklist(request_number, output_dir=checklist_dir)
        static_metadata = _script_file_metadata(request.target)
        latest_preflight_dir, latest_preflight = _latest_script_preflight_manifest(
            _launch_request_signature(request),
            Path(preflight_dir),
        )

        status, notes = _script_execution_readiness_status(
            request=request,
            checklist_verification=verification,
            static_metadata=static_metadata,
            preflight_manifest=latest_preflight,
        )
        readiness_dir = _create_script_readiness_dir(Path(output_dir), request.name)
        confirm_phrase = "confirm script run"
        manifest: dict[str, object] = {
            "schema": SCRIPT_EXECUTION_READINESS_SCHEMA,
            "created_at": _utc_now_iso(),
            "status": status,
            "request_number": request_number,
            "request_signature": _launch_request_signature(request),
            "script_name": request.name,
            "script_target": request.target,
            "script_review_risk": request.script_review_risk or "unknown",
            "script_review_summary": request.script_review_summary,
            "static_metadata": static_metadata,
            "checklist_status": verification.status,
            "checklist_dir": str(verification.checklist_dir) if verification.checklist_dir else "",
            "preflight_status": str(latest_preflight.get("status", "missing")) if latest_preflight else "missing",
            "preflight_dir": str(latest_preflight_dir) if latest_preflight_dir else "",
            "preflight_signature_valid": _script_preflight_signature_valid(latest_preflight),
            "typed_confirmation_phrase": confirm_phrase,
            "audit_dry_run": {
                "enabled": True,
                "result": "no_run_recorded",
                "note": "This bundle is review-only and does not execute or allowlist scripts.",
            },
            "execution_enabled": False,
            "runs_script": False,
            "allowlist_enabled": False,
            "readiness_notes": notes,
        }
        manifest["readiness_signature"] = _script_readiness_signature(manifest)
        manifest_path = readiness_dir / "manifest.json"
        try:
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            raise LaunchRequestError(f"Could not write script execution readiness bundle: {readiness_dir}") from exc

        summary = "\n".join(
            [
                "Script execution readiness bundle created",
                f"Execution readiness status: {status}",
                "No script was run.",
                "No script allowlist entry was created.",
                f"Request: {request_number}. {request.display_text()}",
                f"Checklist status: {verification.status}",
                f"Preflight status: {manifest['preflight_status']}",
                f"Typed confirmation phrase (future design): {confirm_phrase}",
                "Audit dry run: recorded no-run review metadata.",
                f"Readiness folder: {readiness_dir}",
                "Manifest: manifest.json",
                "Readiness notes:",
                *[f"- {note}" for note in notes],
            ]
        )
        return ScriptExecutionReadinessResult(summary, readiness_dir, manifest_path, status)

    def simulate_confirmed_script_run(
        self,
        request_number: int,
        typed_confirmation: str,
        readiness_dir: str | Path = DEFAULT_SCRIPT_EXECUTION_READINESS_DIR,
        output_dir: str | Path = DEFAULT_SCRIPT_RUN_SIMULATION_DIR,
        required_confirmation: str = "confirm script run",
    ) -> ScriptRunSimulationResult:
        """Create a no-run simulation record for a confirmed script run flow."""
        request = self._script_request_by_number(request_number)
        request_signature = _launch_request_signature(request)
        latest_readiness_dir, latest_readiness = _latest_script_readiness_manifest(
            request_signature,
            Path(readiness_dir),
        )
        current_metadata = _script_file_metadata(request.target)
        status, notes = _script_run_simulation_status(
            request=request,
            readiness_manifest=latest_readiness,
            current_metadata=current_metadata,
            typed_confirmation=typed_confirmation,
            required_confirmation=required_confirmation,
        )

        simulation_dir = _create_script_run_simulation_dir(Path(output_dir), request.name)
        manifest: dict[str, object] = {
            "schema": SCRIPT_RUN_SIMULATION_SCHEMA,
            "created_at": _utc_now_iso(),
            "status": status,
            "request_number": request_number,
            "request_signature": request_signature,
            "script_name": request.name,
            "script_target": request.target,
            "typed_confirmation": typed_confirmation,
            "required_confirmation": required_confirmation,
            "readiness_dir": str(latest_readiness_dir) if latest_readiness_dir else "",
            "readiness_status": str(latest_readiness.get("status", "missing")) if latest_readiness else "missing",
            "readiness_signature_valid": _script_readiness_signature_valid(latest_readiness),
            "readiness_preflight_signature_valid": bool(latest_readiness.get("preflight_signature_valid", False))
            if isinstance(latest_readiness, dict)
            else False,
            "readiness_static_metadata": latest_readiness.get("static_metadata", {}) if isinstance(latest_readiness, dict) else {},
            "current_static_metadata": current_metadata,
            "runs_script": False,
            "allowlist_enabled": False,
            "execution_enabled": False,
            "simulation_notes": notes,
            "audit_dry_run": {
                "enabled": True,
                "result": "no_run_recorded",
                "note": "Simulation validates readiness gates and records no-run audit metadata only.",
            },
        }
        manifest["simulation_signature"] = _script_run_simulation_signature(manifest)
        manifest_path = simulation_dir / "manifest.json"
        try:
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            raise LaunchRequestError(f"Could not write script run simulation manifest: {simulation_dir}") from exc

        summary = "\n".join(
            [
                "Confirmed script run simulation created",
                f"Simulation status: {status}",
                "No script was run.",
                "No script allowlist entry was created.",
                f"Request: {request_number}. {request.display_text()}",
                f"Typed confirmation: {typed_confirmation or '(empty)'}",
                f"Required confirmation: {required_confirmation}",
                f"Readiness status: {manifest['readiness_status']}",
                f"Readiness signature valid: {'yes' if manifest['readiness_signature_valid'] else 'no'}",
                "Audit dry run: recorded no-run simulation metadata.",
                f"Simulation folder: {simulation_dir}",
                "Manifest: manifest.json",
                "Simulation notes:",
                *[f"- {note}" for note in notes],
            ]
        )
        return ScriptRunSimulationResult(summary, simulation_dir, manifest_path, status)

    def simulate_script_allowlist_entry(
        self,
        request_number: int,
        interpreter_argv_text: str,
        readiness_dir: str | Path = DEFAULT_SCRIPT_EXECUTION_READINESS_DIR,
        output_dir: str | Path = DEFAULT_SCRIPT_ALLOWLIST_SIMULATION_DIR,
    ) -> ScriptAllowlistEntrySimulationResult:
        """Create a no-run allowlist-entry simulation record for interpreter and argument policy checks."""
        request = self._script_request_by_number(request_number)
        request_signature = _launch_request_signature(request)
        latest_readiness_dir, latest_readiness = _latest_script_readiness_manifest(
            request_signature,
            Path(readiness_dir),
        )
        interpreter, args = _parse_interpreter_argv(interpreter_argv_text)
        current_metadata = _script_file_metadata(request.target)
        status, notes = _script_allowlist_entry_simulation_status(
            request=request,
            interpreter=interpreter,
            args=args,
            readiness_manifest=latest_readiness,
            current_metadata=current_metadata,
        )

        simulation_dir = _create_script_allowlist_simulation_dir(Path(output_dir), request.name)
        manifest: dict[str, object] = {
            "schema": SCRIPT_ALLOWLIST_SIMULATION_SCHEMA,
            "created_at": _utc_now_iso(),
            "status": status,
            "request_number": request_number,
            "request_signature": request_signature,
            "script_name": request.name,
            "script_target": request.target,
            "script_extension": Path(request.target).suffix.lower(),
            "interpreter": interpreter,
            "args": args,
            "readiness_dir": str(latest_readiness_dir) if latest_readiness_dir else "",
            "readiness_status": str(latest_readiness.get("status", "missing")) if latest_readiness else "missing",
            "readiness_signature_valid": _script_readiness_signature_valid(latest_readiness),
            "readiness_preflight_signature_valid": bool(latest_readiness.get("preflight_signature_valid", False))
            if isinstance(latest_readiness, dict)
            else False,
            "readiness_static_metadata": latest_readiness.get("static_metadata", {}) if isinstance(latest_readiness, dict) else {},
            "current_static_metadata": current_metadata,
            "path_pinning": {
                "review_target": str(Path(request.target).expanduser().resolve()),
                "pinned_ready": _path_pin_ready(request, latest_readiness),
            },
            "runs_script": False,
            "allowlist_enabled": False,
            "execution_enabled": False,
            "simulation_notes": notes,
            "audit_dry_run": {
                "enabled": True,
                "result": "no_run_recorded",
                "note": "Allowlist-entry simulation validates policy gates only and does not execute scripts.",
            },
        }
        manifest["simulation_signature"] = _script_allowlist_simulation_signature(manifest)
        manifest_path = simulation_dir / "manifest.json"
        try:
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            raise LaunchRequestError(f"Could not write script allowlist-entry simulation manifest: {simulation_dir}") from exc

        summary = "\n".join(
            [
                "Script allowlist-entry simulation created",
                f"Simulation status: {status}",
                "No script was run.",
                "No script allowlist entry was created.",
                f"Request: {request_number}. {request.display_text()}",
                f"Interpreter: {interpreter}",
                f"Arguments: {' '.join(args) if args else '(none)'}",
                f"Readiness status: {manifest['readiness_status']}",
                f"Readiness signature valid: {'yes' if manifest['readiness_signature_valid'] else 'no'}",
                f"Path pinning ready: {'yes' if manifest['path_pinning']['pinned_ready'] else 'no'}",
                "Audit dry run: recorded no-run allowlist-entry metadata.",
                f"Simulation folder: {simulation_dir}",
                "Manifest: manifest.json",
                "Simulation notes:",
                *[f"- {note}" for note in notes],
            ]
        )
        return ScriptAllowlistEntrySimulationResult(summary, simulation_dir, manifest_path, status)

    def _append(self, request: LaunchRequest) -> None:
        requests = self.list_requests()
        requests.append(request)
        self._write_all(requests)

    def _script_request_by_number(self, request_number: int) -> LaunchRequest:
        script_requests = [request for request in self.list_requests() if request.kind == "script"]
        if not script_requests:
            raise LaunchRequestError("No script review requests are saved yet.")
        if request_number < 1 or request_number > len(script_requests):
            raise LaunchRequestError(
                f"Script review number must be between 1 and {len(script_requests)}. "
                "Use launch requests to view saved script reviews."
            )
        return script_requests[request_number - 1]

    def _read_raw(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"requests": []}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise LaunchRequestError(f"Invalid launch requests JSON: {self.path}") from exc
        except OSError as exc:
            raise LaunchRequestError(f"Could not read launch requests: {self.path}") from exc
        if not isinstance(raw, dict):
            raise LaunchRequestError("Launch requests file must contain a JSON object.")
        return raw

    def _write_all(self, requests: list[LaunchRequest]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = {"requests": [_request_to_raw(request) for request in requests]}
        try:
            self.path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            raise LaunchRequestError(f"Could not write launch requests: {self.path}") from exc


def blocked_unlisted_launch_text() -> str:
    return (
        "Unlisted apps, scripts, files, and folders cannot open automatically. "
        "Create a local review request instead: request app <name>: <exe>, "
        "request script review <name>: <path>, request file review <name>: <path>, "
        "or request folder review <name>: <path>. "
        "For future file launch workflows, explicitly allow file types first with: "
        "allow file type <extension>."
    )


def _clean_required_text(value: str, label: str) -> str:
    clean = value.strip()
    if not clean:
        raise LaunchRequestError(f"{label} cannot be empty.")
    return clean


def _validate_script_target(target: str) -> None:
    if any(char in target for char in ['"', "'", "&", "|", ";", ">", "<"]):
        raise LaunchRequestError("Script path cannot contain shell control characters.")
    suffix = Path(target).suffix.lower()
    if suffix not in SCRIPT_EXTENSIONS:
        allowed = ", ".join(sorted(SCRIPT_EXTENSIONS))
        raise LaunchRequestError(f"Script review target must use one of: {allowed}.")


def _static_script_review(target: str) -> tuple[str, str]:
    path = Path(target).expanduser()
    suffix = path.suffix.lower() or "(no extension)"
    if not path.exists():
        return (
            "unknown",
            f"read-only path review; {suffix} script path was saved but file was not found for inspection",
        )
    if not path.is_file():
        return (
            "high",
            f"read-only path review; {suffix} target exists but is not a regular file",
        )

    try:
        size = path.stat().st_size
    except OSError as exc:
        raise LaunchRequestError(f"Could not inspect script metadata: {path}") from exc

    if size > SCRIPT_REVIEW_READ_LIMIT_BYTES:
        return (
            "medium",
            (
                f"read-only static inspection skipped content because file is {size} bytes "
                f"(limit {SCRIPT_REVIEW_READ_LIMIT_BYTES}); extension {suffix}"
            ),
        )

    try:
        content = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise LaunchRequestError(f"Could not inspect script content: {path}") from exc

    line_count = len(content.splitlines())
    findings = _script_static_findings(content)
    if findings:
        risk = "high"
        finding_text = ", ".join(findings)
    else:
        risk = "low"
        finding_text = "no obvious high-risk tokens found"
    return (
        risk,
        (
            f"read-only static inspection; extension {suffix}; size {size} bytes; "
            f"lines {line_count}; findings: {finding_text}"
        ),
    )


def _script_static_findings(content: str) -> list[str]:
    lowered = content.lower()
    findings: list[str] = []
    for label, tokens in SCRIPT_REVIEW_FINDINGS.items():
        if any(token.lower() in lowered for token in tokens):
            findings.append(label)
    return findings


def _script_file_metadata(target: str) -> dict[str, object]:
    path = Path(target).expanduser()
    metadata: dict[str, object] = {
        "path": str(path),
        "extension": path.suffix.lower() or "(no extension)",
        "exists": path.exists(),
        "is_file": path.is_file() if path.exists() else False,
    }
    if not path.exists() or not path.is_file():
        metadata["sha256"] = ""
        metadata["size_bytes"] = 0
        metadata["hash_status"] = "unavailable"
        return metadata
    try:
        data = path.read_bytes()
        metadata["size_bytes"] = len(data)
        metadata["sha256"] = hashlib.sha256(data).hexdigest()
        metadata["hash_status"] = "recorded"
    except OSError:
        metadata["size_bytes"] = 0
        metadata["sha256"] = ""
        metadata["hash_status"] = "unavailable"
    return metadata


def _script_operator_checklist_items(
    request: LaunchRequest,
    static_metadata: dict[str, object],
) -> list[str]:
    items = [
        "Confirm the script path is the intended local script.",
        "Confirm the script extension is expected for this review.",
        "Confirm static inspection notes were reviewed before any future allowlist decision.",
        "Confirm no messages, emails, network requests, or external services are contacted without a separate safety design.",
        "Confirm destructive file operations, process launches, registry changes, and dynamic code findings are understood.",
        "Confirm this checklist does not add a script allowlist entry and does not run the script.",
    ]
    if request.script_review_risk in {"medium", "high", "unknown"}:
        items.append("Because script review risk is not low, require a second manual review before future allowlisting.")
    if static_metadata.get("hash_status") != "recorded":
        items.append("Because the script hash was not recorded, block future allowlisting until the file can be hashed.")
    else:
        items.append("Record the script SHA-256 hash for any future exact-hash allowlist design.")
    return items


def _script_operator_checklist_markdown(manifest: dict[str, object]) -> str:
    metadata = manifest.get("static_metadata")
    metadata_text = "unknown"
    if isinstance(metadata, dict):
        metadata_text = (
            f"extension {metadata.get('extension', 'unknown')}; "
            f"size {metadata.get('size_bytes', 'unknown')} bytes; "
            f"sha256 {metadata.get('sha256', '') or 'unavailable'}"
        )
    lines = [
        "# Script Operator Checklist",
        "",
        f"Request: {manifest.get('request_number')}",
        f"Script: {manifest.get('script_name')}",
        f"Target: {manifest.get('script_target')}",
        f"Static risk: {manifest.get('script_review_risk')}",
        f"Static metadata: {metadata_text}",
        "",
        "This checklist is review-only. It did not run the script and did not create a script allowlist entry.",
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
            "- [ ] I understand script execution remains disabled in this build.",
            "",
            f"Checklist signature: {manifest.get('checklist_signature')}",
        ]
    )
    return "\n".join(lines) + "\n"


def _create_script_checklist_dir(output_dir: Path, request_name: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(char if char.isalnum() else "-" for char in request_name).strip("-") or "script"
    checklist_dir = output_dir / f"script-checklist-{safe_name}-{timestamp}"
    if checklist_dir.exists():
        checklist_dir = output_dir / f"script-checklist-{safe_name}-{timestamp}-{uuid4().hex[:8]}"
    checklist_dir.mkdir(parents=True, exist_ok=False)
    return checklist_dir


def _latest_script_checklist_manifest(
    request_signature: str,
    output_dir: Path,
) -> tuple[Path | None, dict[str, object] | None]:
    if not output_dir.exists():
        return None, None
    matches: list[tuple[Path, dict[str, object]]] = []
    for manifest_path in sorted(output_dir.glob("script-checklist-*/manifest.json")):
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(raw, dict) and raw.get("request_signature") == request_signature:
            matches.append((manifest_path.parent, raw))
    if not matches:
        return None, None
    return matches[-1]


def _latest_script_preflight_manifest(
    request_signature: str,
    output_dir: Path,
) -> tuple[Path | None, dict[str, object] | None]:
    if not output_dir.exists():
        return None, None
    matches: list[tuple[Path, dict[str, object]]] = []
    for manifest_path in sorted(output_dir.glob("script-allowlist-preflight-*/manifest.json")):
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(raw, dict) and raw.get("request_signature") == request_signature:
            matches.append((manifest_path.parent, raw))
    if not matches:
        return None, None
    return matches[-1]


def _latest_script_readiness_manifest(
    request_signature: str,
    output_dir: Path,
) -> tuple[Path | None, dict[str, object] | None]:
    if not output_dir.exists():
        return None, None
    matches: list[tuple[Path, dict[str, object]]] = []
    for manifest_path in sorted(output_dir.glob("script-execution-readiness-*/manifest.json")):
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(raw, dict) and raw.get("request_signature") == request_signature:
            matches.append((manifest_path.parent, raw))
    if not matches:
        return None, None
    return matches[-1]


def _launch_request_signature(request: LaunchRequest) -> str:
    payload = {
        "kind": request.kind,
        "name": request.name,
        "target": request.target,
        "reason": request.reason,
        "created_at": request.created_at,
        "script_review_risk": request.script_review_risk,
        "script_review_summary": request.script_review_summary,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _script_checklist_signature(manifest: dict[str, object]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "checklist_signature"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _script_allowlist_preflight_status(
    verification: ScriptReviewChecklistVerification,
    static_metadata: dict[str, object],
) -> tuple[str, list[str]]:
    notes = [
        "Script execution is disabled; this preflight is for review only.",
        "Script allowlisting is disabled; this preflight does not approve anything.",
    ]
    status = "preflight_ready"
    if verification.status != "verified":
        status = "blocked"
        notes.append("Checklist verification is not verified.")
    else:
        notes.append("Checklist verification is verified.")
    if static_metadata.get("hash_status") != "recorded":
        status = "blocked"
        notes.append("Script hash is not recorded; exact-hash allowlisting cannot be reviewed.")
    else:
        notes.append("Script SHA-256 hash is recorded for future exact-hash comparison.")
    if static_metadata.get("exists") is not True or static_metadata.get("is_file") is not True:
        status = "blocked"
        notes.append("Script target is not an existing regular file.")
    return status, notes


def _create_script_preflight_dir(output_dir: Path, request_name: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(char if char.isalnum() else "-" for char in request_name).strip("-") or "script"
    preflight_dir = output_dir / f"script-allowlist-preflight-{safe_name}-{timestamp}"
    if preflight_dir.exists():
        preflight_dir = output_dir / f"script-allowlist-preflight-{safe_name}-{timestamp}-{uuid4().hex[:8]}"
    preflight_dir.mkdir(parents=True, exist_ok=False)
    return preflight_dir


def _script_preflight_signature(manifest: dict[str, object]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "preflight_signature"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _script_preflight_signature_valid(manifest: dict[str, object] | None) -> bool:
    if not isinstance(manifest, dict):
        return False
    signature = manifest.get("preflight_signature")
    if not isinstance(signature, str):
        return False
    return signature == _script_preflight_signature(manifest)


def _script_execution_readiness_status(
    request: LaunchRequest,
    checklist_verification: ScriptReviewChecklistVerification,
    static_metadata: dict[str, object],
    preflight_manifest: dict[str, object] | None,
) -> tuple[str, list[str]]:
    status = "ready"
    notes = [
        "Execution remains disabled; this readiness bundle is review-only.",
        "Typed confirmation phrase and audit dry run are design gates, not execution permission.",
    ]

    if checklist_verification.status != "verified":
        status = "blocked"
        notes.append("Checklist verification is not verified.")
    else:
        notes.append("Checklist verification is verified.")

    if static_metadata.get("hash_status") != "recorded":
        status = "blocked"
        notes.append("Exact-hash pin prerequisite failed: script SHA-256 is not recorded.")
    else:
        notes.append("Exact-hash pin prerequisite satisfied: script SHA-256 is recorded.")

    if static_metadata.get("exists") is not True or static_metadata.get("is_file") is not True:
        status = "blocked"
        notes.append("Script target is not an existing regular file.")

    if not isinstance(preflight_manifest, dict):
        status = "blocked"
        notes.append("Preflight binding failed: no matching script allowlist preflight record found.")
    else:
        preflight_status = str(preflight_manifest.get("status", "unknown"))
        preflight_signature_valid = _script_preflight_signature_valid(preflight_manifest)
        preflight_checklist_status = str(preflight_manifest.get("checklist_status", "unknown"))
        if preflight_status != "preflight_ready":
            status = "blocked"
            notes.append(f"Preflight status is not preflight_ready (got: {preflight_status}).")
        else:
            notes.append("Preflight status is preflight_ready.")
        if preflight_checklist_status != "verified":
            status = "blocked"
            notes.append(f"Preflight checklist status is not verified (got: {preflight_checklist_status}).")
        else:
            notes.append("Preflight checklist status is verified.")
        if not preflight_signature_valid:
            status = "blocked"
            notes.append("Preflight signature validation failed.")
        else:
            notes.append("Preflight signature is valid.")

    if request.script_review_risk in {"high", "unknown"}:
        status = "blocked"
        notes.append(
            f"Script review risk is {request.script_review_risk}; manual multi-party safety review is required before enablement design."
        )
    return status, notes


def _create_script_readiness_dir(output_dir: Path, request_name: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(char if char.isalnum() else "-" for char in request_name).strip("-") or "script"
    readiness_dir = output_dir / f"script-execution-readiness-{safe_name}-{timestamp}"
    if readiness_dir.exists():
        readiness_dir = output_dir / f"script-execution-readiness-{safe_name}-{timestamp}-{uuid4().hex[:8]}"
    readiness_dir.mkdir(parents=True, exist_ok=False)
    return readiness_dir


def _script_readiness_signature(manifest: dict[str, object]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "readiness_signature"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _script_readiness_signature_valid(manifest: dict[str, object] | None) -> bool:
    if not isinstance(manifest, dict):
        return False
    signature = manifest.get("readiness_signature")
    if not isinstance(signature, str):
        return False
    return signature == _script_readiness_signature(manifest)


def _script_run_simulation_status(
    request: LaunchRequest,
    readiness_manifest: dict[str, object] | None,
    current_metadata: dict[str, object],
    typed_confirmation: str,
    required_confirmation: str,
) -> tuple[str, list[str]]:
    status = "simulated"
    notes = [
        "This is a read-only simulation; no script execution is performed.",
        "This simulation does not create or change script allowlist entries.",
    ]

    if typed_confirmation.strip() != required_confirmation:
        status = "blocked"
        notes.append("Typed confirmation phrase does not match required confirmation.")
    else:
        notes.append("Typed confirmation phrase matches required confirmation.")

    if not isinstance(readiness_manifest, dict):
        status = "blocked"
        notes.append("No readiness bundle found for this script review request.")
        return status, notes

    readiness_status = str(readiness_manifest.get("status", "unknown"))
    if readiness_status != "ready":
        status = "blocked"
        notes.append(f"Readiness status is not ready (got: {readiness_status}).")
    else:
        notes.append("Readiness status is ready.")

    if not _script_readiness_signature_valid(readiness_manifest):
        status = "blocked"
        notes.append("Readiness signature validation failed.")
    else:
        notes.append("Readiness signature is valid.")

    preflight_signature_valid = bool(readiness_manifest.get("preflight_signature_valid", False))
    if not preflight_signature_valid:
        status = "blocked"
        notes.append("Readiness record reports invalid preflight signature state.")
    else:
        notes.append("Readiness record reports valid preflight signature state.")

    readiness_meta = readiness_manifest.get("static_metadata")
    if not isinstance(readiness_meta, dict):
        status = "blocked"
        notes.append("Readiness metadata is missing static hash details.")
        return status, notes

    if readiness_meta.get("hash_status") != "recorded":
        status = "blocked"
        notes.append("Readiness metadata does not have a recorded script hash.")
    else:
        notes.append("Readiness metadata has a recorded script hash.")

    if current_metadata.get("exists") is not True or current_metadata.get("is_file") is not True:
        status = "blocked"
        notes.append("Current script target is missing or not a regular file.")
        return status, notes

    expected_sha = str(readiness_meta.get("sha256", ""))
    current_sha = str(current_metadata.get("sha256", ""))
    expected_size = int(readiness_meta.get("size_bytes", 0))
    current_size = int(current_metadata.get("size_bytes", 0))
    if expected_sha != current_sha or expected_size != current_size:
        status = "blocked"
        notes.append("Current script hash/size does not match readiness metadata.")
    else:
        notes.append("Current script hash/size matches readiness metadata.")

    if request.script_review_risk in {"high", "unknown"}:
        status = "blocked"
        notes.append(
            f"Script review risk is {request.script_review_risk}; simulation remains blocked pending stronger manual review."
        )
    return status, notes


def _create_script_run_simulation_dir(output_dir: Path, request_name: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(char if char.isalnum() else "-" for char in request_name).strip("-") or "script"
    simulation_dir = output_dir / f"script-run-simulation-{safe_name}-{timestamp}"
    if simulation_dir.exists():
        simulation_dir = output_dir / f"script-run-simulation-{safe_name}-{timestamp}-{uuid4().hex[:8]}"
    simulation_dir.mkdir(parents=True, exist_ok=False)
    return simulation_dir


def _script_run_simulation_signature(manifest: dict[str, object]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "simulation_signature"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_interpreter_argv(text: str) -> tuple[str, list[str]]:
    clean = text.strip()
    if not clean:
        raise LaunchRequestError(
            "script allowlist entry simulation expects: "
            "script allowlist entry simulation <request number>: <interpreter> [args...]"
        )
    try:
        tokens = shlex.split(clean, posix=False)
    except ValueError as exc:
        raise LaunchRequestError(f"Could not parse interpreter arguments: {exc}") from exc
    if not tokens:
        raise LaunchRequestError("Interpreter command cannot be empty.")
    interpreter = tokens[0].strip()
    if not interpreter:
        raise LaunchRequestError("Interpreter command cannot be empty.")
    return interpreter, [token.strip() for token in tokens[1:] if token.strip()]


def _script_allowlist_entry_simulation_status(
    request: LaunchRequest,
    interpreter: str,
    args: list[str],
    readiness_manifest: dict[str, object] | None,
    current_metadata: dict[str, object],
) -> tuple[str, list[str]]:
    status = "simulated"
    notes = [
        "This is a read-only allowlist-entry simulation; no script execution is performed.",
        "This simulation does not create or change script allowlist entries.",
    ]

    if not isinstance(readiness_manifest, dict):
        status = "blocked"
        notes.append("No readiness bundle found for this script review request.")
        return status, notes

    readiness_status = str(readiness_manifest.get("status", "unknown"))
    if readiness_status != "ready":
        status = "blocked"
        notes.append(f"Readiness status is not ready (got: {readiness_status}).")
    else:
        notes.append("Readiness status is ready.")

    if not _script_readiness_signature_valid(readiness_manifest):
        status = "blocked"
        notes.append("Readiness signature validation failed.")
    else:
        notes.append("Readiness signature is valid.")

    if not bool(readiness_manifest.get("preflight_signature_valid", False)):
        status = "blocked"
        notes.append("Readiness record reports invalid preflight signature state.")
    else:
        notes.append("Readiness record reports valid preflight signature state.")

    if not _path_pin_ready(request, readiness_manifest):
        status = "blocked"
        notes.append("Path pinning check failed: reviewed target does not match readiness metadata path.")
    else:
        notes.append("Path pinning check passed: reviewed target matches readiness metadata path.")

    readiness_meta = readiness_manifest.get("static_metadata")
    if not isinstance(readiness_meta, dict):
        status = "blocked"
        notes.append("Readiness metadata is missing static hash details.")
        return status, notes

    if readiness_meta.get("hash_status") != "recorded":
        status = "blocked"
        notes.append("Readiness metadata does not have a recorded script hash.")

    if current_metadata.get("exists") is not True or current_metadata.get("is_file") is not True:
        status = "blocked"
        notes.append("Current script target is missing or not a regular file.")
        return status, notes

    expected_sha = str(readiness_meta.get("sha256", ""))
    current_sha = str(current_metadata.get("sha256", ""))
    expected_size = int(readiness_meta.get("size_bytes", 0))
    current_size = int(current_metadata.get("size_bytes", 0))
    if expected_sha != current_sha or expected_size != current_size:
        status = "blocked"
        notes.append("Current script hash/size does not match readiness metadata.")
    else:
        notes.append("Current script hash/size matches readiness metadata.")

    executable = Path(interpreter).name.lower()
    expected_interpreters = SCRIPT_INTERPRETER_BY_EXTENSION.get(Path(request.target).suffix.lower(), set())
    if expected_interpreters and executable not in expected_interpreters:
        status = "blocked"
        notes.append(
            f"Interpreter policy failed: {executable} is not allowed for extension {Path(request.target).suffix.lower()}."
        )
    else:
        notes.append("Interpreter extension policy check passed.")

    if executable in SCRIPT_ALLOWLIST_SIMULATION_BLOCKED_INTERPRETERS:
        status = "blocked"
        notes.append(f"Interpreter policy blocked in this build: {executable} is not eligible for execution enablement.")

    for arg in args:
        lowered = arg.lower()
        if any(char in arg for char in ("|", "&", ";", ">", "<")):
            status = "blocked"
            notes.append("Argument policy failed: shell control characters are not allowed.")
            break
        if lowered in SCRIPT_ALLOWLIST_SIMULATION_BLOCKED_ARGS:
            status = "blocked"
            notes.append(f"Argument policy failed: {arg} is blocked in allowlist-entry simulation.")
            break
    else:
        notes.append("Argument policy check passed.")

    if request.script_review_risk in {"high", "unknown"}:
        status = "blocked"
        notes.append(
            f"Script review risk is {request.script_review_risk}; simulation remains blocked pending stronger manual review."
        )
    return status, notes


def _path_pin_ready(request: LaunchRequest, readiness_manifest: dict[str, object] | None) -> bool:
    if not isinstance(readiness_manifest, dict):
        return False
    metadata = readiness_manifest.get("static_metadata")
    if not isinstance(metadata, dict):
        return False
    recorded_path = metadata.get("path")
    if not isinstance(recorded_path, str) or not recorded_path.strip():
        return False
    reviewed_path = str(Path(request.target).expanduser().resolve())
    readiness_path = str(Path(recorded_path).expanduser().resolve())
    return reviewed_path == readiness_path


def _create_script_allowlist_simulation_dir(output_dir: Path, request_name: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(char if char.isalnum() else "-" for char in request_name).strip("-") or "script"
    simulation_dir = output_dir / f"script-allowlist-simulation-{safe_name}-{timestamp}"
    if simulation_dir.exists():
        simulation_dir = output_dir / f"script-allowlist-simulation-{safe_name}-{timestamp}-{uuid4().hex[:8]}"
    simulation_dir.mkdir(parents=True, exist_ok=False)
    return simulation_dir


def _script_allowlist_simulation_signature(manifest: dict[str, object]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "simulation_signature"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_file_target(target: str) -> Path:
    _validate_review_path_text(target, "File path")
    path = Path(target).expanduser()
    if not path.exists():
        raise LaunchRequestError(f"File path does not exist: {path}")
    if not path.is_file():
        raise LaunchRequestError(f"File review target is not a file: {path}")
    return path


def _review_file_type(path: Path) -> tuple[str, str, str, str]:
    suffix = path.suffix.lower()
    if suffix in EXECUTABLE_EXTENSIONS:
        return (
            f"executable ({suffix})",
            suffix,
            "high",
            "reviewed read-only; executable opens remain blocked unless explicitly allowlisted",
        )
    if suffix in SCRIPT_EXTENSIONS:
        return (
            f"script ({suffix})",
            suffix,
            "high",
            "reviewed read-only; use script review/allowlist flow before any execution",
        )
    if suffix in SHORTCUT_EXTENSIONS:
        return (
            f"shortcut ({suffix})",
            suffix,
            "high",
            "reviewed read-only; shortcut targets must be verified before any external open",
        )
    if suffix in ARCHIVE_EXTENSIONS:
        return (
            f"archive ({suffix})",
            suffix,
            "medium",
            "reviewed read-only; inspect extracted contents before any external open",
        )
    if suffix in DOCUMENT_EXTENSIONS:
        return (
            f"document ({suffix})",
            suffix,
            "medium",
            "reviewed read-only; verify source and macros before any external open",
        )
    if suffix in MEDIA_EXTENSIONS:
        return (
            f"media ({suffix})",
            suffix,
            "low",
            "reviewed read-only; external open remains confirmation-gated",
        )
    if suffix in TEXT_EXTENSIONS:
        return (
            f"text/source ({suffix})",
            suffix,
            "low",
            "reviewed read-only; prefer in-assistant preview when possible",
        )
    if suffix:
        return (
            f"unknown ({suffix})",
            suffix,
            "medium",
            "reviewed read-only; unknown file type requires cautious manual inspection",
        )
    return (
        "unknown (no extension)",
        "(no extension)",
        "medium",
        "reviewed read-only; extensionless files require cautious manual inspection",
    )


def _validate_folder_review_target(target: str) -> None:
    _validate_review_path_text(target, "Folder path")
    path = Path(target).expanduser()
    if not path.exists():
        raise LaunchRequestError(f"Folder path does not exist: {path}")
    if not path.is_dir():
        raise LaunchRequestError(f"Folder review target is not a folder: {path}")


def _validate_review_path_text(target: str, label: str) -> None:
    if any(char in target for char in ['"', "'", "&", "|", ";", ">", "<"]):
        raise LaunchRequestError(f"{label} cannot contain shell control characters.")


def _request_to_raw(request: LaunchRequest) -> dict[str, Any]:
    raw = {
        "kind": request.kind,
        "name": request.name,
        "target": request.target,
        "reason": request.reason,
        "created_at": request.created_at,
    }
    if request.file_type_category:
        raw["file_type_category"] = request.file_type_category
    if request.file_type_extension:
        raw["file_type_extension"] = request.file_type_extension
    raw["file_type_allowed_for_launch"] = request.file_type_allowed_for_launch
    if request.file_type_risk:
        raw["file_type_risk"] = request.file_type_risk
    if request.file_type_note:
        raw["file_type_note"] = request.file_type_note
    if request.script_review_risk:
        raw["script_review_risk"] = request.script_review_risk
    if request.script_review_summary:
        raw["script_review_summary"] = request.script_review_summary
    return raw


def _request_from_raw(raw: dict[str, Any]) -> LaunchRequest | None:
    try:
        kind = str(raw["kind"])
        name = str(raw["name"])
        target = str(raw["target"])
        reason = str(raw.get("reason", ""))
        created_at = str(raw["created_at"])
        file_type_category = str(raw.get("file_type_category", ""))
        file_type_extension = str(raw.get("file_type_extension", ""))
        file_type_allowed_for_launch = bool(raw.get("file_type_allowed_for_launch", False))
        file_type_risk = str(raw.get("file_type_risk", ""))
        file_type_note = str(raw.get("file_type_note", ""))
        script_review_risk = str(raw.get("script_review_risk", ""))
        script_review_summary = str(raw.get("script_review_summary", ""))
    except KeyError:
        return None
    if kind not in {"app", "script", "file", "folder"}:
        return None
    return LaunchRequest(
        kind,
        name,
        target,
        reason,
        created_at,
        file_type_category=file_type_category,
        file_type_extension=file_type_extension,
        file_type_allowed_for_launch=file_type_allowed_for_launch,
        file_type_risk=file_type_risk,
        file_type_note=file_type_note,
        script_review_risk=script_review_risk,
        script_review_summary=script_review_summary,
    )


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
