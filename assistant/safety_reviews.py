"""Local signed safety review export helpers."""

from __future__ import annotations

import json
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from assistant.launch_requests import (
    DEFAULT_LAUNCH_REQUESTS_PATH,
    DEFAULT_SCRIPT_CHECKLIST_DIR,
    DEFAULT_SCRIPT_PREFLIGHT_DIR,
)
from assistant.shell_tools import DEFAULT_SHELL_COMMANDS_PATH


DEFAULT_SAFETY_REVIEW_EXPORT_DIR = Path("exports/safety-review-exports")
DEFAULT_BULK_PREFLIGHT_DIR = Path("exports/bulk-write-preflights")


class SafetyReviewExportError(RuntimeError):
    """Raised when signed safety review records cannot be exported."""


def export_safety_reviews(
    shell_commands_path: str | Path = DEFAULT_SHELL_COMMANDS_PATH,
    bulk_preflight_dir: str | Path = DEFAULT_BULK_PREFLIGHT_DIR,
    launch_requests_path: str | Path = DEFAULT_LAUNCH_REQUESTS_PATH,
    script_checklist_dir: str | Path = DEFAULT_SCRIPT_CHECKLIST_DIR,
    script_preflight_dir: str | Path = DEFAULT_SCRIPT_PREFLIGHT_DIR,
    output_dir: str | Path = DEFAULT_SAFETY_REVIEW_EXPORT_DIR,
) -> Path:
    """Export signed shell, bulk, and script review records without executing actions."""
    export_root = Path(output_dir)
    timestamp = _utc_timestamp()
    export_dir = export_root / f"safety-review-{timestamp}"
    if export_dir.exists():
        export_dir = export_root / f"safety-review-{timestamp}-{uuid4().hex[:8]}"
    export_dir.mkdir(parents=True, exist_ok=False)

    shell_reviews = _load_shell_reviews(Path(shell_commands_path))
    bulk_reviews = _load_bulk_preflight_reviews(Path(bulk_preflight_dir))
    script_reviews = _load_script_review_requests(Path(launch_requests_path))
    script_checklists = _load_script_checklist_reviews(Path(script_checklist_dir))
    script_preflights = _load_script_preflight_reviews(Path(script_preflight_dir))
    manifest = {
        "kind": "safety_review_export",
        "created_at": _utc_now_iso(),
        "shell_commands_path": str(shell_commands_path),
        "bulk_preflight_dir": str(bulk_preflight_dir),
        "launch_requests_path": str(launch_requests_path),
        "script_checklist_dir": str(script_checklist_dir),
        "script_preflight_dir": str(script_preflight_dir),
        "shell_review_count": len(shell_reviews),
        "bulk_preflight_review_count": len(bulk_reviews),
        "script_review_count": len(script_reviews),
        "script_checklist_review_count": len(script_checklists),
        "script_preflight_review_count": len(script_preflights),
        "records": {
            "shell_reviews": shell_reviews,
            "bulk_preflight_reviews": bulk_reviews,
            "script_reviews": script_reviews,
            "script_checklist_reviews": script_checklists,
            "script_preflight_reviews": script_preflights,
        },
        "notes": [
            "Export is local-only and read-only with respect to safety actions.",
            "Exporting records does not run shell commands, run scripts, apply bulk writes, or restore files.",
            "Exporting records does not add app, file, shell, or script allowlist entries.",
            "Each record includes signature status for manual audit.",
        ],
    }
    manifest["export_signature"] = _record_signature(manifest, signature_field="export_signature")
    (export_dir / "safety_reviews.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return export_dir


def safety_review_export_summary(export_dir: Path) -> str:
    manifest_path = export_dir / "safety_reviews.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SafetyReviewExportError(f"Could not read safety review export: {manifest_path}") from exc

    return "\n".join(
        [
            "Signed safety review export created",
            "No commands were run. No files were applied, restored, sent, or opened.",
            f"Export folder: {export_dir}",
            f"Shell review records: {manifest.get('shell_review_count', 0)}",
            f"Bulk preflight review records: {manifest.get('bulk_preflight_review_count', 0)}",
            f"Script review records: {manifest.get('script_review_count', 0)}",
            f"Script checklist review records: {manifest.get('script_checklist_review_count', 0)}",
            f"Script preflight review records: {manifest.get('script_preflight_review_count', 0)}",
            f"Export signature: {manifest.get('export_signature', 'missing')}",
            "Manifest: safety_reviews.json",
        ]
    )


def _load_shell_reviews(commands_path: Path) -> list[dict[str, object]]:
    if not commands_path.exists():
        return []
    try:
        raw = json.loads(commands_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SafetyReviewExportError(f"Could not read shell review metadata: {commands_path}") from exc

    raw_reviews = raw.get("reviews") if isinstance(raw, dict) else None
    if not isinstance(raw_reviews, list):
        return []

    reviews: list[dict[str, object]] = []
    for index, raw_review in enumerate(raw_reviews, start=1):
        if not isinstance(raw_review, dict):
            continue
        review = dict(raw_review)
        review["source"] = str(commands_path)
        review["source_index"] = index
        review["signature_valid"] = _signature_is_valid(review)
        reviews.append(review)
    return reviews


def _load_bulk_preflight_reviews(preflight_root: Path) -> list[dict[str, object]]:
    if not preflight_root.exists():
        return []

    reviews: list[dict[str, object]] = []
    for manifest_path in sorted(preflight_root.glob("bulk-*/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(manifest, dict):
            continue
        metadata = manifest.get("signed_review_metadata")
        if not isinstance(metadata, dict):
            continue
        review = dict(metadata)
        review["source"] = str(manifest_path)
        review["preflight_status"] = manifest.get("status")
        review["preflight_manifest_sha256"] = manifest.get("manifest_sha256")
        review["signature_valid"] = _signature_is_valid(review)
        reviews.append(review)
    return reviews


def _load_script_review_requests(launch_requests_path: Path) -> list[dict[str, object]]:
    if not launch_requests_path.exists():
        return []
    try:
        raw = json.loads(launch_requests_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SafetyReviewExportError(f"Could not read script review requests: {launch_requests_path}") from exc

    raw_requests = raw.get("requests") if isinstance(raw, dict) else None
    if not isinstance(raw_requests, list):
        return []

    reviews: list[dict[str, object]] = []
    script_index = 0
    for source_index, raw_request in enumerate(raw_requests, start=1):
        if not isinstance(raw_request, dict) or raw_request.get("kind") != "script":
            continue
        script_index += 1
        review: dict[str, object] = {
            "schema": "script_review_request_export_v1",
            "source": str(launch_requests_path),
            "source_index": source_index,
            "script_review_number": script_index,
            "created_at": raw_request.get("created_at", ""),
            "script_name": raw_request.get("name", ""),
            "script_target": raw_request.get("target", ""),
            "script_review_risk": raw_request.get("script_review_risk", "unknown"),
            "script_review_summary": raw_request.get("script_review_summary", ""),
            "execution_enabled": False,
            "runs_script": False,
            "allowlist_enabled": False,
            "review_notes": [
                "Script review request export only; script was not run.",
                "Exporting this record does not create a script allowlist entry.",
            ],
        }
        review["review_signature"] = _record_signature(review)
        review["signature_valid"] = _signature_is_valid(review)
        reviews.append(review)
    return reviews


def _load_script_checklist_reviews(checklist_root: Path) -> list[dict[str, object]]:
    if not checklist_root.exists():
        return []

    reviews: list[dict[str, object]] = []
    for manifest_path in sorted(checklist_root.glob("script-checklist-*/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(manifest, dict):
            continue
        review = dict(manifest)
        review["source"] = str(manifest_path)
        review["checklist_signature_valid"] = _checklist_signature_is_valid(review)
        review["signature_valid"] = bool(review["checklist_signature_valid"])
        reviews.append(review)
    return reviews


def _load_script_preflight_reviews(preflight_root: Path) -> list[dict[str, object]]:
    if not preflight_root.exists():
        return []

    reviews: list[dict[str, object]] = []
    for manifest_path in sorted(preflight_root.glob("script-allowlist-preflight-*/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(manifest, dict):
            continue
        review = dict(manifest)
        review["source"] = str(manifest_path)
        review["preflight_signature_valid"] = _preflight_signature_is_valid(review)
        review["signature_valid"] = bool(review["preflight_signature_valid"])
        reviews.append(review)
    return reviews


def _checklist_signature_is_valid(record: dict[str, object]) -> bool:
    signature = record.get("checklist_signature")
    return isinstance(signature, str) and signature == _record_signature(record, signature_field="checklist_signature")


def _preflight_signature_is_valid(record: dict[str, object]) -> bool:
    signature = record.get("preflight_signature")
    return isinstance(signature, str) and signature == _record_signature(record, signature_field="preflight_signature")


def _signature_is_valid(record: dict[str, object]) -> bool:
    signature = record.get("review_signature")
    return isinstance(signature, str) and signature == _record_signature(record)


def _record_signature(record: dict[str, object], signature_field: str = "review_signature") -> str:
    payload = {
        key: value
        for key, value in record.items()
        if key
        not in {
            signature_field,
            "source",
            "source_index",
            "signature_valid",
            "checklist_signature_valid",
            "preflight_signature_valid",
            "preflight_status",
            "preflight_manifest_sha256",
        }
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
