"""Read-only safety snapshots for launch, shell, and script review records."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

from assistant.launch_requests import (
    DEFAULT_SCRIPT_ALLOWLIST_SIMULATION_DIR,
    DEFAULT_SCRIPT_CHECKLIST_DIR,
    DEFAULT_SCRIPT_EXECUTION_READINESS_DIR,
    DEFAULT_SCRIPT_PREFLIGHT_DIR,
    DEFAULT_SCRIPT_RUN_SIMULATION_DIR,
    LaunchRequest,
    LaunchRequestError,
    LaunchRequestStore,
)
from assistant.shell_tools import ShellToolError, shell_review_records, shell_review_signature_valid


def safety_snapshot_text(
    launch_request_store: LaunchRequestStore,
    shell_commands_path: str | Path,
    limit: int = 5,
    review_type: str = "all",
    script_checklist_dir: str | Path = DEFAULT_SCRIPT_CHECKLIST_DIR,
    script_preflight_dir: str | Path = DEFAULT_SCRIPT_PREFLIGHT_DIR,
    script_execution_readiness_dir: str | Path = DEFAULT_SCRIPT_EXECUTION_READINESS_DIR,
    script_run_simulation_dir: str | Path = DEFAULT_SCRIPT_RUN_SIMULATION_DIR,
    script_allowlist_simulation_dir: str | Path = DEFAULT_SCRIPT_ALLOWLIST_SIMULATION_DIR,
    drift_warning_threshold: int | None = None,
) -> str:
    """Return a read-only snapshot of recent local safety review artifacts."""
    clean_type = review_type.strip().lower()
    if clean_type not in {
        "all",
        "launch",
        "shell",
        "scripts",
        "scripts-drift",
        "scripts-drift-signature",
        "scripts-drift-hash",
        "scripts-drift-path",
    }:
        clean_type = "all"

    lines = [
        _snapshot_title(clean_type),
        "Read-only. No apps, scripts, files, folders, or shell commands were opened or run.",
        "",
    ]
    if clean_type in {"all", "launch"}:
        lines.extend(_launch_request_lines(launch_request_store, limit))
    if clean_type == "all":
        lines.append("")
    if clean_type == "scripts":
        lines.extend(
            _script_review_lines(
                launch_request_store,
                limit,
                Path(script_checklist_dir),
                Path(script_preflight_dir),
                Path(script_execution_readiness_dir),
                Path(script_run_simulation_dir),
                Path(script_allowlist_simulation_dir),
            )
        )
    if clean_type in {"scripts-drift", "scripts-drift-signature", "scripts-drift-hash", "scripts-drift-path"}:
        warning_filter = {
            "scripts-drift-signature": "signature",
            "scripts-drift-hash": "hash",
            "scripts-drift-path": "path",
        }.get(clean_type)
        lines.extend(
            _script_drift_lines(
                launch_request_store,
                limit,
                Path(script_execution_readiness_dir),
                Path(script_run_simulation_dir),
                Path(script_allowlist_simulation_dir),
                warning_filter=warning_filter,
                warning_threshold=drift_warning_threshold,
            )
        )
    if clean_type in {"all", "shell"}:
        lines.extend(_shell_review_lines(shell_commands_path, limit))
    lines.extend(
        [
            "",
            "Current gates:",
            "- Launch requests are local review notes only; they do not update allowlists or open targets.",
            "- Script review snapshots are local review notes only; they do not run or allowlist scripts.",
            "- File review requests include read-only file-type risk notes before any external open workflow.",
            "- Shell review records are tamper-evident notes only; running still requires run shell <name> and confirmation.",
            "- Raw shell text, scripts, command chaining, and destructive commands remain blocked.",
        ]
    )
    return "\n".join(lines)


def _snapshot_title(review_type: str) -> str:
    if review_type == "launch":
        return "Safety snapshot: launch requests"
    if review_type == "shell":
        return "Safety snapshot: shell reviews"
    if review_type == "scripts":
        return "Safety snapshot: script reviews"
    if review_type == "scripts-drift":
        return "Safety snapshot: script drift warnings"
    if review_type == "scripts-drift-signature":
        return "Safety snapshot: script drift warnings (signature)"
    if review_type == "scripts-drift-hash":
        return "Safety snapshot: script drift warnings (hash)"
    if review_type == "scripts-drift-path":
        return "Safety snapshot: script drift warnings (path)"
    return "Safety snapshot"


def _launch_request_lines(store: LaunchRequestStore, limit: int) -> list[str]:
    try:
        requests = store.list_requests()
    except LaunchRequestError as exc:
        return ["Launch review requests: unavailable", f"- Error: {exc}"]

    lines = [f"Launch review requests: {len(requests)}"]
    if not requests:
        lines.append("- None saved.")
        return lines

    for index, request in enumerate(requests[-limit:], start=1):
        lines.append(f"{index}. {request.display_text()} ({request.created_at})")
    if len(requests) > limit:
        lines.append(f"Showing latest {limit} of {len(requests)} request(s).")
    return lines


def _script_review_lines(
    store: LaunchRequestStore,
    limit: int,
    script_checklist_dir: Path,
    script_preflight_dir: Path,
    script_execution_readiness_dir: Path,
    script_run_simulation_dir: Path,
    script_allowlist_simulation_dir: Path,
) -> list[str]:
    try:
        requests = [request for request in store.list_requests() if request.kind == "script"]
    except LaunchRequestError as exc:
        return ["Script review requests: unavailable", f"- Error: {exc}"]

    lines = [f"Script review requests: {len(requests)}"]
    if not requests:
        lines.append("- None saved.")
        return lines

    start_number = max(1, len(requests) - limit + 1)
    for script_number, request in enumerate(requests[-limit:], start=start_number):
        risk = request.script_review_risk or "unknown"
        summary = request.script_review_summary or "no static review summary recorded"
        checklist_status = _script_checklist_status(store, script_number, script_checklist_dir)
        preflight_status = _script_preflight_status(request, script_number, script_preflight_dir)
        readiness_status = _script_readiness_status(request, script_number, script_execution_readiness_dir)
        run_simulation_status = _script_run_simulation_status(request, script_number, script_run_simulation_dir)
        allowlist_simulation_status = _script_allowlist_simulation_status(
            request,
            script_number,
            script_allowlist_simulation_dir,
        )
        lines.append(
            f"{script_number}. {request.name} -> {request.target} "
            f"({request.created_at}; risk {risk}; {summary}; {checklist_status}; {preflight_status}; "
            f"{readiness_status}; {run_simulation_status}; {allowlist_simulation_status})"
        )
    if len(requests) > limit:
        lines.append(f"Showing latest {limit} of {len(requests)} script review request(s).")
    lines.append("Use script review checklist <number> for the matching script review number.")
    return lines


def _script_drift_lines(
    store: LaunchRequestStore,
    limit: int,
    script_execution_readiness_dir: Path,
    script_run_simulation_dir: Path,
    script_allowlist_simulation_dir: Path,
    warning_filter: str | None = None,
    warning_threshold: int | None = None,
) -> list[str]:
    try:
        requests = [request for request in store.list_requests() if request.kind == "script"]
    except LaunchRequestError as exc:
        return ["Script drift warnings: unavailable", f"- Error: {exc}"]

    total_scripts = len(requests)
    filter_parts = []
    if warning_filter:
        filter_parts.append(f"filter: {warning_filter}")
    if warning_threshold:
        filter_parts.append(f"threshold: >= {warning_threshold} warning type(s)")
    filter_text = f" ({', '.join(filter_parts)})" if filter_parts else ""
    lines = [f"Script drift warnings: scanning {total_scripts} script request(s){filter_text}"]
    if not requests:
        lines.append("- None saved.")
        return lines

    drift_entries: list[str] = []
    breakdown_counts = {"signature": 0, "hash": 0, "path": 0}
    start_number = max(1, total_scripts - limit + 1)
    for script_number, request in enumerate(requests[-limit:], start=start_number):
        request_signature = _launch_request_signature(request)
        drift_reasons: list[str] = []

        readiness_match = _latest_script_manifest(
            script_number,
            request_signature,
            script_execution_readiness_dir,
            "script-execution-readiness-*/manifest.json",
        )
        if readiness_match is not None:
            _, readiness_manifest = readiness_match
            if not _signature_field_valid(readiness_manifest, "readiness_signature"):
                drift_reasons.append("readiness-signature mismatch")
            if not bool(readiness_manifest.get("preflight_signature_valid", False)):
                drift_reasons.append("preflight-signature mismatch")

        run_match = _latest_script_manifest(
            script_number,
            request_signature,
            script_run_simulation_dir,
            "script-run-simulation-*/manifest.json",
        )
        if run_match is not None:
            _, run_manifest = run_match
            if not _signature_field_valid(run_manifest, "simulation_signature"):
                drift_reasons.append("simulation-signature mismatch")
            if not bool(run_manifest.get("readiness_signature_valid", False)):
                drift_reasons.append("readiness-signature mismatch")
            if not _metadata_hash_matches(run_manifest):
                drift_reasons.append("script-hash mismatch")

        allowlist_match = _latest_script_manifest(
            script_number,
            request_signature,
            script_allowlist_simulation_dir,
            "script-allowlist-simulation-*/manifest.json",
        )
        if allowlist_match is not None:
            _, allowlist_manifest = allowlist_match
            if not _signature_field_valid(allowlist_manifest, "simulation_signature"):
                drift_reasons.append("simulation-signature mismatch")
            if not bool(allowlist_manifest.get("readiness_signature_valid", False)):
                drift_reasons.append("readiness-signature mismatch")
            if not _metadata_hash_matches(allowlist_manifest):
                drift_reasons.append("script-hash mismatch")
            path_pinning = allowlist_manifest.get("path_pinning")
            if not isinstance(path_pinning, dict) or not bool(path_pinning.get("pinned_ready", False)):
                drift_reasons.append("path mismatch")

        if drift_reasons:
            unique_reason_list = list(dict.fromkeys(drift_reasons))
            active_types = _warning_types(unique_reason_list)
            if warning_filter and warning_filter not in active_types:
                continue
            if warning_threshold and len(active_types) < warning_threshold:
                continue
            for warning_type in active_types:
                breakdown_counts[warning_type] += 1
            unique_reasons = ", ".join(unique_reason_list)
            drift_entries.append(
                f"{script_number}. {request.name} -> {request.target} ({request.created_at}; drift warning: {unique_reasons})"
            )

    if warning_filter:
        lines.append(f"Script requests with drift warnings ({warning_filter}): {len(drift_entries)}")
    elif warning_threshold:
        lines.append(f"Script requests with drift warnings (>= {warning_threshold} warning type(s)): {len(drift_entries)}")
    else:
        lines.append(f"Script requests with drift warnings: {len(drift_entries)}")
    lines.append(
        "Drift warning breakdown: "
        f"signature={breakdown_counts['signature']}, "
        f"hash={breakdown_counts['hash']}, "
        f"path={breakdown_counts['path']}"
    )
    if not drift_entries:
        lines.append("- No active drift warnings found in latest readiness/simulation records.")
        return lines
    lines.extend(drift_entries)
    lines.append("Use safety snapshot scripts for full per-request gate details.")
    return lines


def _warning_types(reasons: list[str]) -> set[str]:
    warning_types: set[str] = set()
    for reason in reasons:
        if "signature" in reason:
            warning_types.add("signature")
        elif "script-hash" in reason:
            warning_types.add("hash")
        elif "path mismatch" in reason:
            warning_types.add("path")
    return warning_types


def _script_checklist_status(store: LaunchRequestStore, script_number: int, script_checklist_dir: Path) -> str:
    try:
        verification = store.verify_script_review_checklist(script_number, output_dir=script_checklist_dir)
    except LaunchRequestError as exc:
        return f"checklist: unavailable ({exc})"
    if verification.checklist_dir is None:
        return "checklist: missing; verification: blocked"
    return f"checklist: {verification.status}; folder: {verification.checklist_dir}"


def _script_preflight_status(request: LaunchRequest, script_number: int, script_preflight_dir: Path) -> str:
    if not script_preflight_dir.exists():
        return "preflight: missing"

    request_signature = _launch_request_signature(request)
    match = _latest_script_preflight_manifest(script_number, request_signature, script_preflight_dir)
    if match is None:
        return "preflight: missing"

    preflight_dir, manifest = match
    status = str(manifest.get("status", "unknown"))
    checklist_status = str(manifest.get("checklist_status", "unknown"))
    signature_valid = _script_preflight_signature_valid(manifest)
    signature_text = "valid" if signature_valid else "invalid"
    return (
        f"preflight: {status}; checklist: {checklist_status}; "
        f"signature {signature_text}; folder: {preflight_dir}"
    )


def _script_readiness_status(request: LaunchRequest, script_number: int, script_execution_readiness_dir: Path) -> str:
    if not script_execution_readiness_dir.exists():
        return "readiness: missing"

    request_signature = _launch_request_signature(request)
    match = _latest_script_manifest(
        script_number,
        request_signature,
        script_execution_readiness_dir,
        "script-execution-readiness-*/manifest.json",
    )
    if match is None:
        return "readiness: missing"

    readiness_dir, manifest = match
    status = str(manifest.get("status", "unknown"))
    signature_valid = _signature_field_valid(manifest, "readiness_signature")
    signature_text = "valid" if signature_valid else "invalid"
    preflight_sig_valid = bool(manifest.get("preflight_signature_valid", False))
    preflight_sig_text = "valid" if preflight_sig_valid else "invalid"
    drift_reasons: list[str] = []
    if not signature_valid:
        drift_reasons.append("readiness-signature mismatch")
    if not preflight_sig_valid:
        drift_reasons.append("preflight-signature mismatch")
    drift_text = _drift_warning_text(drift_reasons)
    return (
        f"readiness: {status}; signature {signature_text}; preflight-signature {preflight_sig_text}; "
        f"folder: {readiness_dir}{drift_text}"
    )


def _script_run_simulation_status(request: LaunchRequest, script_number: int, script_run_simulation_dir: Path) -> str:
    if not script_run_simulation_dir.exists():
        return "run-simulation: missing"

    request_signature = _launch_request_signature(request)
    match = _latest_script_manifest(
        script_number,
        request_signature,
        script_run_simulation_dir,
        "script-run-simulation-*/manifest.json",
    )
    if match is None:
        return "run-simulation: missing"

    simulation_dir, manifest = match
    status = str(manifest.get("status", "unknown"))
    signature_valid = _signature_field_valid(manifest, "simulation_signature")
    signature_text = "valid" if signature_valid else "invalid"
    readiness_sig_valid = bool(manifest.get("readiness_signature_valid", False))
    readiness_sig_text = "valid" if readiness_sig_valid else "invalid"
    hash_matches = _metadata_hash_matches(manifest)
    hash_text = "match" if hash_matches else "mismatch"
    drift_reasons: list[str] = []
    if not signature_valid:
        drift_reasons.append("simulation-signature mismatch")
    if not readiness_sig_valid:
        drift_reasons.append("readiness-signature mismatch")
    if hash_matches is False:
        drift_reasons.append("script-hash mismatch")
    drift_text = _drift_warning_text(drift_reasons)
    return (
        f"run-simulation: {status}; signature {signature_text}; readiness-signature {readiness_sig_text}; "
        f"script-hash {hash_text}; folder: {simulation_dir}{drift_text}"
    )


def _script_allowlist_simulation_status(
    request: LaunchRequest,
    script_number: int,
    script_allowlist_simulation_dir: Path,
) -> str:
    if not script_allowlist_simulation_dir.exists():
        return "allowlist-simulation: missing"

    request_signature = _launch_request_signature(request)
    match = _latest_script_manifest(
        script_number,
        request_signature,
        script_allowlist_simulation_dir,
        "script-allowlist-simulation-*/manifest.json",
    )
    if match is None:
        return "allowlist-simulation: missing"

    simulation_dir, manifest = match
    status = str(manifest.get("status", "unknown"))
    signature_valid = _signature_field_valid(manifest, "simulation_signature")
    signature_text = "valid" if signature_valid else "invalid"
    path_pin_ready = bool(manifest.get("path_pinning", {}).get("pinned_ready", False)) if isinstance(manifest.get("path_pinning"), dict) else False
    path_pin_text = "ready" if path_pin_ready else "blocked"
    readiness_sig_valid = bool(manifest.get("readiness_signature_valid", False))
    readiness_sig_text = "valid" if readiness_sig_valid else "invalid"
    hash_matches = _metadata_hash_matches(manifest)
    hash_text = "match" if hash_matches else "mismatch"
    drift_reasons: list[str] = []
    if not signature_valid:
        drift_reasons.append("simulation-signature mismatch")
    if not readiness_sig_valid:
        drift_reasons.append("readiness-signature mismatch")
    if not path_pin_ready:
        drift_reasons.append("path mismatch")
    if hash_matches is False:
        drift_reasons.append("script-hash mismatch")
    drift_text = _drift_warning_text(drift_reasons)
    return (
        f"allowlist-simulation: {status}; signature {signature_text}; readiness-signature {readiness_sig_text}; "
        f"path-pin {path_pin_text}; script-hash {hash_text}; folder: {simulation_dir}{drift_text}"
    )


def _latest_script_preflight_manifest(
    script_number: int,
    request_signature: str,
    preflight_dir: Path,
) -> tuple[Path, dict[str, object]] | None:
    matches: list[tuple[Path, dict[str, object]]] = []
    for manifest_path in sorted(preflight_dir.glob("script-allowlist-preflight-*/manifest.json")):
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(raw, dict):
            continue
        if int(raw.get("request_number", -1)) != script_number:
            continue
        if str(raw.get("request_signature", "")) != request_signature:
            continue
        matches.append((manifest_path.parent, raw))
    if not matches:
        return None
    return matches[-1]


def _latest_script_manifest(
    script_number: int,
    request_signature: str,
    manifest_root: Path,
    pattern: str,
) -> tuple[Path, dict[str, object]] | None:
    matches: list[tuple[Path, dict[str, object]]] = []
    for manifest_path in sorted(manifest_root.glob(pattern)):
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(raw, dict):
            continue
        if int(raw.get("request_number", -1)) != script_number:
            continue
        if str(raw.get("request_signature", "")) != request_signature:
            continue
        matches.append((manifest_path.parent, raw))
    if not matches:
        return None
    return matches[-1]


def _script_preflight_signature_valid(manifest: dict[str, object]) -> bool:
    return _signature_field_valid(manifest, "preflight_signature")


def _signature_field_valid(manifest: dict[str, object], signature_field: str) -> bool:
    signature = manifest.get(signature_field)
    if not isinstance(signature, str):
        return False
    payload = {key: value for key, value in manifest.items() if key != signature_field}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return signature == hashlib.sha256(encoded).hexdigest()


def _metadata_hash_matches(manifest: dict[str, object]) -> bool:
    readiness_meta = manifest.get("readiness_static_metadata")
    current_meta = manifest.get("current_static_metadata")
    if not isinstance(readiness_meta, dict) or not isinstance(current_meta, dict):
        return False
    return (
        str(readiness_meta.get("sha256", "")) == str(current_meta.get("sha256", ""))
        and int(readiness_meta.get("size_bytes", 0)) == int(current_meta.get("size_bytes", 0))
    )


def _drift_warning_text(reasons: list[str]) -> str:
    if not reasons:
        return ""
    unique_reasons = ", ".join(dict.fromkeys(reasons))
    return f"; drift warning: {unique_reasons}"


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


def _shell_review_lines(shell_commands_path: str | Path, limit: int) -> list[str]:
    try:
        reviews = shell_review_records(shell_commands_path)
    except ShellToolError as exc:
        return ["Shell allowlist review records: unavailable", f"- Error: {exc}"]

    lines = [f"Shell allowlist review records: {len(reviews)}"]
    if not reviews:
        lines.append("- None saved.")
        return lines

    for index, review in enumerate(reviews[-limit:], start=1):
        command_name = review.get("command_name", "unknown")
        action = review.get("action", "unknown")
        created_at = review.get("created_at", "unknown time")
        argv = review.get("argv")
        argv_text = " ".join(str(item) for item in argv) if isinstance(argv, list) else "unknown argv"
        signature_status = "valid" if shell_review_signature_valid(review) else "invalid"
        risk_text = _risk_text(review)
        lines.append(
            f"{index}. {action} '{command_name}' -> {argv_text} "
            f"({created_at}; signature {signature_status}; risk {risk_text})"
        )
    if len(reviews) > limit:
        lines.append(f"Showing latest {limit} of {len(reviews)} review record(s).")
    return lines


def _risk_text(review: dict[str, object]) -> str:
    risk = review.get("static_risk")
    if not isinstance(risk, dict):
        return "not recorded"
    level = risk.get("level")
    score = risk.get("score")
    if isinstance(level, str) and isinstance(score, int):
        return f"{level} ({score}/10)"
    return "not recorded"
