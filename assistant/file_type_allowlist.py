"""Persistent per-file-type allowlist for future file launch workflows."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_FILE_TYPE_ALLOWLIST_PATH = Path("config/file_types.json")
_EXTENSION_PATTERN = re.compile(r"^\.[a-z0-9]+$")


class FileTypeAllowlistError(RuntimeError):
    """Raised when file-type allowlist data cannot be read or written."""


@dataclass(frozen=True)
class FileTypeTrustPolicy:
    trusted_sources: tuple[str, ...] = ()
    trusted_signers: tuple[str, ...] = ()
    pinned_thumbprints: tuple[str, ...] = ()
    trusted_issuers: tuple[str, ...] = ()
    require_valid_certificate: bool = False
    require_revocation_check: bool = False
    revocation_mode: str = "online"


@dataclass(frozen=True)
class FileTypeTrustEvaluation:
    passed: bool
    notes: tuple[str, ...]


@dataclass(frozen=True)
class FileSignerInfo:
    subject: str | None = None
    thumbprint: str | None = None
    issuer: str | None = None
    not_before: datetime | None = None
    not_after: datetime | None = None


def normalize_file_extension(value: str) -> str:
    """Normalize extension text (for example, 'PDF' -> '.pdf')."""
    cleaned = value.strip().lower()
    if not cleaned:
        raise FileTypeAllowlistError("File type extension cannot be empty.")
    if not cleaned.startswith("."):
        cleaned = f".{cleaned}"
    if not _EXTENSION_PATTERN.fullmatch(cleaned):
        raise FileTypeAllowlistError(
            "File type extension must be alphanumeric, like .pdf or .txt."
        )
    return cleaned


def normalize_thumbprint(value: str) -> str:
    cleaned = "".join(char for char in value.strip().upper() if char in "0123456789ABCDEF")
    if len(cleaned) != 40:
        raise FileTypeAllowlistError(
            "Certificate thumbprint must contain exactly 40 hexadecimal characters."
        )
    return cleaned


def normalize_revocation_mode(value: str) -> str:
    cleaned = value.strip().lower()
    mapping = {
        "online": "online",
        "default": "online",
        "required": "online",
        "strict": "online",
        "ocsp": "ocsp",
        "crl": "crl",
        "both": "both",
        "ocsp+crl": "both",
        "crl+ocsp": "both",
    }
    mode = mapping.get(cleaned)
    if mode is None:
        raise FileTypeAllowlistError("Revocation mode must be online, ocsp, crl, or both.")
    return mode


class FileTypeAllowlistStore:
    """Local JSON-backed store of launch-allowlisted file extensions."""

    def __init__(self, path: str | Path = DEFAULT_FILE_TYPE_ALLOWLIST_PATH) -> None:
        self.path = Path(path)

    def list_extensions(self) -> list[str]:
        raw = self._read_raw()
        values = raw.get("allowed_extensions", [])
        if not isinstance(values, list):
            raise FileTypeAllowlistError("File type allowlist must contain an 'allowed_extensions' list.")

        normalized: set[str] = set()
        for item in values:
            if isinstance(item, str):
                normalized.add(normalize_file_extension(item))
        return sorted(normalized)

    def trust_policy(self, extension: str) -> FileTypeTrustPolicy:
        clean_extension = normalize_file_extension(extension)
        raw = self._read_raw().get("trust_policies", {})
        if not isinstance(raw, dict):
            raise FileTypeAllowlistError("File type allowlist trust_policies must be an object.")

        policy_raw = raw.get(clean_extension, {})
        if not isinstance(policy_raw, dict):
            policy_raw = {}

        sources = _normalize_distinct_text_list(policy_raw.get("trusted_sources", []), label="trusted source")
        signers = _normalize_distinct_text_list(policy_raw.get("trusted_signers", []), label="trusted signer")
        thumbprints = _normalize_thumbprint_list(policy_raw.get("pinned_thumbprints", []))
        issuers = _normalize_distinct_text_list(policy_raw.get("trusted_issuers", []), label="trusted issuer")
        require_valid_certificate = bool(policy_raw.get("require_valid_certificate", False))
        require_revocation_check = bool(policy_raw.get("require_revocation_check", False))
        revocation_mode = normalize_revocation_mode(str(policy_raw.get("revocation_mode", "online")))
        return FileTypeTrustPolicy(
            tuple(sources),
            tuple(signers),
            tuple(thumbprints),
            tuple(issuers),
            require_valid_certificate,
            require_revocation_check,
            revocation_mode,
        )

    def is_allowed_extension(self, extension: str) -> bool:
        clean_extension = normalize_file_extension(extension)
        return clean_extension in set(self.list_extensions())

    def allow_extension(self, extension: str) -> str:
        clean_extension = normalize_file_extension(extension)
        current = set(self.list_extensions())
        current.add(clean_extension)
        self._write_all(sorted(current))
        return clean_extension

    def disallow_extension(self, extension: str) -> str:
        clean_extension = normalize_file_extension(extension)
        current = set(self.list_extensions())
        if clean_extension not in current:
            raise FileTypeAllowlistError(f"File type is not allowlisted: {clean_extension}")
        current.remove(clean_extension)
        self._write_all(sorted(current), self._trust_policies_raw_without_extension(clean_extension))
        return clean_extension

    def set_trusted_sources(self, extension: str, sources: list[str]) -> FileTypeTrustPolicy:
        clean_extension = normalize_file_extension(extension)
        normalized_sources = _normalize_distinct_text_list(sources, label="trusted source")
        policies = self._trust_policies_raw()
        policy_raw = policies.get(clean_extension, {})
        if not isinstance(policy_raw, dict):
            policy_raw = {}
        policy_raw["trusted_sources"] = normalized_sources
        policies[clean_extension] = policy_raw
        self._write_all(self.list_extensions(), policies)
        return self.trust_policy(clean_extension)

    def set_trusted_signers(self, extension: str, signers: list[str]) -> FileTypeTrustPolicy:
        clean_extension = normalize_file_extension(extension)
        normalized_signers = _normalize_distinct_text_list(signers, label="trusted signer")
        policies = self._trust_policies_raw()
        policy_raw = policies.get(clean_extension, {})
        if not isinstance(policy_raw, dict):
            policy_raw = {}
        policy_raw["trusted_signers"] = normalized_signers
        policies[clean_extension] = policy_raw
        self._write_all(self.list_extensions(), policies)
        return self.trust_policy(clean_extension)

    def set_pinned_thumbprints(self, extension: str, thumbprints: list[str]) -> FileTypeTrustPolicy:
        clean_extension = normalize_file_extension(extension)
        normalized_thumbprints = _normalize_thumbprint_list(thumbprints)
        policies = self._trust_policies_raw()
        policy_raw = policies.get(clean_extension, {})
        if not isinstance(policy_raw, dict):
            policy_raw = {}
        policy_raw["pinned_thumbprints"] = normalized_thumbprints
        policies[clean_extension] = policy_raw
        self._write_all(self.list_extensions(), policies)
        return self.trust_policy(clean_extension)

    def set_trusted_issuers(self, extension: str, issuers: list[str]) -> FileTypeTrustPolicy:
        clean_extension = normalize_file_extension(extension)
        normalized_issuers = _normalize_distinct_text_list(issuers, label="trusted issuer")
        policies = self._trust_policies_raw()
        policy_raw = policies.get(clean_extension, {})
        if not isinstance(policy_raw, dict):
            policy_raw = {}
        policy_raw["trusted_issuers"] = normalized_issuers
        policies[clean_extension] = policy_raw
        self._write_all(self.list_extensions(), policies)
        return self.trust_policy(clean_extension)

    def set_validity_requirement(self, extension: str, require_valid_certificate: bool) -> FileTypeTrustPolicy:
        clean_extension = normalize_file_extension(extension)
        policies = self._trust_policies_raw()
        policy_raw = policies.get(clean_extension, {})
        if not isinstance(policy_raw, dict):
            policy_raw = {}
        policy_raw["require_valid_certificate"] = bool(require_valid_certificate)
        policies[clean_extension] = policy_raw
        self._write_all(self.list_extensions(), policies)
        return self.trust_policy(clean_extension)

    def set_revocation_requirement(
        self,
        extension: str,
        require_revocation_check: bool,
        revocation_mode: str = "online",
    ) -> FileTypeTrustPolicy:
        clean_extension = normalize_file_extension(extension)
        normalized_mode = normalize_revocation_mode(revocation_mode)
        policies = self._trust_policies_raw()
        policy_raw = policies.get(clean_extension, {})
        if not isinstance(policy_raw, dict):
            policy_raw = {}
        policy_raw["require_revocation_check"] = bool(require_revocation_check)
        policy_raw["revocation_mode"] = normalized_mode
        policies[clean_extension] = policy_raw
        self._write_all(self.list_extensions(), policies)
        return self.trust_policy(clean_extension)

    def clear_trust_policy(self, extension: str) -> str:
        clean_extension = normalize_file_extension(extension)
        policies = self._trust_policies_raw()
        if clean_extension in policies:
            policies.pop(clean_extension)
            self._write_all(self.list_extensions(), policies)
        return clean_extension

    def trust_policy_summary(self, extension: str) -> str:
        clean_extension = normalize_file_extension(extension)
        policy = self.trust_policy(clean_extension)
        if (
            not policy.trusted_sources
            and not policy.trusted_signers
            and not policy.pinned_thumbprints
            and not policy.trusted_issuers
            and not policy.require_valid_certificate
            and not policy.require_revocation_check
        ):
            return (
                f"Trust policy for {clean_extension}: none. "
                "No extra source/signer trust signals are required."
            )

        lines = [f"Trust policy for {clean_extension}:"]
        if policy.trusted_sources:
            lines.append("Trusted sources:")
            lines.extend(f"- {item}" for item in policy.trusted_sources)
        else:
            lines.append("Trusted sources: none")

        if policy.trusted_signers:
            lines.append("Trusted signer tokens:")
            lines.extend(f"- {item}" for item in policy.trusted_signers)
        else:
            lines.append("Trusted signer tokens: none")

        if policy.pinned_thumbprints:
            lines.append("Pinned certificate thumbprints:")
            lines.extend(f"- {item}" for item in policy.pinned_thumbprints)
        else:
            lines.append("Pinned certificate thumbprints: none")

        if policy.trusted_issuers:
            lines.append("Trusted issuer tokens:")
            lines.extend(f"- {item}" for item in policy.trusted_issuers)
        else:
            lines.append("Trusted issuer tokens: none")

        lines.append(
            "Certificate validity requirement: "
            + ("required" if policy.require_valid_certificate else "not required")
        )
        lines.append(
            "Certificate revocation check: "
            + (
                f"required (mode: {policy.revocation_mode})"
                if policy.require_revocation_check
                else "not required"
            )
        )
        return "\n".join(lines)

    def evaluate_trust_signals(self, extension: str, file_path: Path) -> FileTypeTrustEvaluation:
        clean_extension = normalize_file_extension(extension)
        policy = self.trust_policy(clean_extension)
        notes: list[str] = []

        if policy.trusted_sources:
            resolved = file_path.resolve()
            allowed = False
            for source in policy.trusted_sources:
                source_path = Path(source).expanduser().resolve()
                if source_path.exists() and resolved.is_relative_to(source_path):
                    allowed = True
                    break
            if not allowed:
                notes.append("BLOCKED: file path is outside configured trusted source roots.")

        signer_info: FileSignerInfo | None = None
        if (
            policy.trusted_signers
            or policy.pinned_thumbprints
            or policy.trusted_issuers
            or policy.require_valid_certificate
            or policy.require_revocation_check
        ):
            signer_info = _authenticode_signer_info(file_path)

        if policy.trusted_signers:
            subject = signer_info.subject if signer_info is not None else None
            if not subject:
                notes.append("BLOCKED: file does not have a readable Authenticode signer subject.")
            else:
                lowered = subject.casefold()
                if not any(token.casefold() in lowered for token in policy.trusted_signers):
                    notes.append("BLOCKED: file signer subject does not match trusted signer tokens.")

        if policy.pinned_thumbprints:
            thumbprint = signer_info.thumbprint if signer_info is not None else None
            if not thumbprint:
                notes.append("BLOCKED: file does not have a readable Authenticode signer thumbprint.")
            elif thumbprint not in set(policy.pinned_thumbprints):
                notes.append("BLOCKED: file signer thumbprint does not match any pinned thumbprint.")

        if policy.trusted_issuers:
            issuer = signer_info.issuer if signer_info is not None else None
            if not issuer:
                notes.append("BLOCKED: file does not have a readable certificate issuer.")
            else:
                lowered = issuer.casefold()
                if not any(token.casefold() in lowered for token in policy.trusted_issuers):
                    notes.append("BLOCKED: certificate issuer does not match trusted issuer tokens.")

        if policy.require_valid_certificate:
            not_before = signer_info.not_before if signer_info is not None else None
            not_after = signer_info.not_after if signer_info is not None else None
            if not not_before or not not_after:
                notes.append("BLOCKED: certificate validity window could not be read.")
            else:
                now = datetime.now(UTC)
                if now < not_before or now > not_after:
                    notes.append("BLOCKED: certificate is not currently valid.")

        if policy.require_revocation_check:
            revocation_ok, status_text = _authenticode_revocation_status(file_path, policy.revocation_mode)
            if revocation_ok is None:
                notes.append(_revocation_review_note(policy.revocation_mode, status_text, passed=None))
            elif not revocation_ok:
                notes.append(_revocation_review_note(policy.revocation_mode, status_text, passed=False))
            else:
                notes.append(_revocation_review_note(policy.revocation_mode, status_text, passed=True))

        if not notes:
            if (
                policy.trusted_sources
                or policy.trusted_signers
                or policy.pinned_thumbprints
                or policy.trusted_issuers
                or policy.require_valid_certificate
                or policy.require_revocation_check
            ):
                notes.append("Trust checks passed.")
            else:
                notes.append("No extra trust checks configured.")
        return FileTypeTrustEvaluation(not any(item.startswith("BLOCKED:") for item in notes), tuple(notes))

    def summary(self) -> str:
        extensions = self.list_extensions()
        if not extensions:
            return (
                "File type allowlist: none."
                " Any future file launch workflow stays blocked until a file type is explicitly allowlisted."
            )
        lines = [
            "File type allowlist: " + ", ".join(extensions) + ".",
            "Only these file types are eligible for future file launch workflows.",
        ]
        for extension in extensions:
            policy = self.trust_policy(extension)
            if (
                policy.trusted_sources
                or policy.trusted_signers
                or policy.pinned_thumbprints
                or policy.trusted_issuers
                or policy.require_valid_certificate
                or policy.require_revocation_check
            ):
                lines.append(
                    f"- {extension} trust signals: "
                    f"sources={len(policy.trusted_sources)}, signers={len(policy.trusted_signers)}, "
                    f"thumbprints={len(policy.pinned_thumbprints)}, issuers={len(policy.trusted_issuers)}, "
                    f"validity={'required' if policy.require_valid_certificate else 'optional'}, "
                    f"revocation={('required/' + policy.revocation_mode) if policy.require_revocation_check else 'optional'}"
                )
        return "\n".join(lines)

    def _read_raw(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"allowed_extensions": []}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise FileTypeAllowlistError(f"Invalid file type allowlist JSON: {self.path}") from exc
        except OSError as exc:
            raise FileTypeAllowlistError(f"Could not read file type allowlist: {self.path}") from exc

        if not isinstance(raw, dict):
            raise FileTypeAllowlistError("File type allowlist file must contain a JSON object.")
        return raw

    def _trust_policies_raw(self) -> dict[str, dict[str, object]]:
        raw = self._read_raw().get("trust_policies", {})
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise FileTypeAllowlistError("File type allowlist trust_policies must be an object.")

        cleaned: dict[str, dict[str, object]] = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            extension = normalize_file_extension(key)
            cleaned[extension] = {
                "trusted_sources": _normalize_distinct_text_list(value.get("trusted_sources", []), label="trusted source"),
                "trusted_signers": _normalize_distinct_text_list(value.get("trusted_signers", []), label="trusted signer"),
                "pinned_thumbprints": _normalize_thumbprint_list(value.get("pinned_thumbprints", [])),
                "trusted_issuers": _normalize_distinct_text_list(value.get("trusted_issuers", []), label="trusted issuer"),
                "require_valid_certificate": bool(value.get("require_valid_certificate", False)),
                "require_revocation_check": bool(value.get("require_revocation_check", False)),
                "revocation_mode": normalize_revocation_mode(str(value.get("revocation_mode", "online"))),
            }
        return cleaned

    def _trust_policies_raw_without_extension(self, extension: str) -> dict[str, dict[str, object]]:
        policies = self._trust_policies_raw()
        policies.pop(extension, None)
        return policies

    def _write_all(
        self,
        extensions: list[str],
        trust_policies: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        policies = trust_policies if trust_policies is not None else self._trust_policies_raw()
        data: dict[str, object] = {"allowed_extensions": extensions}
        if policies:
            data["trust_policies"] = policies
        try:
            self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            raise FileTypeAllowlistError(f"Could not write file type allowlist: {self.path}") from exc


def _normalize_distinct_text_list(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list):
        raise FileTypeAllowlistError(f"{label} list must be a JSON array.")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise FileTypeAllowlistError(f"Each {label} entry must be text.")
        normalized = " ".join(item.strip().split())
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)
    return cleaned


def _normalize_thumbprint_list(value: object) -> list[str]:
    if not isinstance(value, list):
        raise FileTypeAllowlistError("pinned thumbprint list must be a JSON array.")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise FileTypeAllowlistError("Each pinned thumbprint entry must be text.")
        normalized = normalize_thumbprint(item)
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def _authenticode_signer_info(path: Path) -> FileSignerInfo:
    command = (
        "$sig = Get-AuthenticodeSignature -FilePath $args[0];"
        " if ($null -eq $sig.SignerCertificate) { '' }"
        " else {"
        "   $c = $sig.SignerCertificate;"
        "   $c.Subject + '\\n' + $c.Thumbprint + '\\n' + $c.Issuer + '\\n' + "
        "   $c.NotBefore.ToUniversalTime().ToString('o') + '\\n' + $c.NotAfter.ToUniversalTime().ToString('o')"
        " }"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command, str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return FileSignerInfo(subject=None, thumbprint=None)
    if result.returncode != 0:
        return FileSignerInfo(subject=None, thumbprint=None)

    output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not output_lines:
        return FileSignerInfo(subject=None, thumbprint=None)

    subject = " ".join(output_lines[0].split())
    if len(output_lines) > 1:
        try:
            thumbprint = normalize_thumbprint(output_lines[1])
        except FileTypeAllowlistError:
            thumbprint = None
    else:
        thumbprint = None

    issuer = " ".join(output_lines[2].split()) if len(output_lines) > 2 else None
    not_before = _parse_certificate_datetime(output_lines[3]) if len(output_lines) > 3 else None
    not_after = _parse_certificate_datetime(output_lines[4]) if len(output_lines) > 4 else None
    return FileSignerInfo(
        subject=subject or None,
        thumbprint=thumbprint,
        issuer=issuer or None,
        not_before=not_before,
        not_after=not_after,
    )


def _revocation_mode_requirement_text(mode: str) -> str:
    normalized_mode = normalize_revocation_mode(mode)
    requirements = {
        "online": "Windows online chain revocation must succeed",
        "ocsp": "Windows online chain revocation must succeed and an OCSP endpoint must be advertised",
        "crl": "Windows online chain revocation must succeed and a CRL distribution point must be advertised",
        "both": "Windows online chain revocation must succeed, and both OCSP and CRL endpoint metadata must be advertised",
    }
    return requirements[normalized_mode]


def _revocation_review_note(mode: str, status_text: str | None, passed: bool | None) -> str:
    normalized_mode = normalize_revocation_mode(mode)
    requirement = _revocation_mode_requirement_text(normalized_mode)
    status = status_text or "no status detail"
    if passed is True:
        return (
            f"Revocation mode {normalized_mode} allowed launch (mode: {normalized_mode}): "
            f"{requirement}; status: {status}."
        )
    if passed is False:
        return (
            f"BLOCKED: revocation mode {normalized_mode} blocked launch (mode: {normalized_mode}): "
            f"{requirement}; status: {status}."
        )
    return (
        f"BLOCKED: revocation mode {normalized_mode} could not determine launch safety (mode: {normalized_mode}): "
        f"{requirement}; status: {status}."
    )


def _authenticode_revocation_status(path: Path, mode: str = "online") -> tuple[bool | None, str | None]:
    command = (
        "$sig = Get-AuthenticodeSignature -FilePath $args[0];"
        " if ($null -eq $sig.SignerCertificate) { 'NOSIGNER' }"
        " else {"
        "   $c = $sig.SignerCertificate;"
        "   $hasOcsp = $false;"
        "   $hasCrl = $false;"
        "   foreach ($ext in $c.Extensions) {"
        "     if ($ext.Oid.Value -eq '1.3.6.1.5.5.7.1.1') {"
        "       $aia = $ext.Format($true);"
        "       if ($aia -match 'OCSP|1\\.3\\.6\\.1\\.5\\.5\\.7\\.48\\.1') { $hasOcsp = $true }"
        "     }"
        "     if ($ext.Oid.Value -eq '2.5.29.31') { $hasCrl = $true }"
        "   }"
        "   $chain = New-Object System.Security.Cryptography.X509Certificates.X509Chain;"
        "   $chain.ChainPolicy.RevocationMode = [System.Security.Cryptography.X509Certificates.X509RevocationMode]::Online;"
        "   $chain.ChainPolicy.RevocationFlag = [System.Security.Cryptography.X509Certificates.X509RevocationFlag]::EntireChain;"
        "   $chain.ChainPolicy.UrlRetrievalTimeout = [TimeSpan]::FromSeconds(5);"
        "   $chain.ChainPolicy.VerificationFlags = [System.Security.Cryptography.X509Certificates.X509VerificationFlags]::NoFlag;"
        "   [void]$chain.Build($c);"
        "   $statuses = @($chain.ChainStatus | ForEach-Object { $_.Status.ToString() } | Where-Object { $_ -and $_ -ne 'NoError' });"
        "   $status = if ($statuses.Count -eq 0) { 'GOOD' } else { $statuses -join ',' };"
        "   $status + '|' + ($(if ($hasOcsp) { '1' } else { '0' })) + '|' + ($(if ($hasCrl) { '1' } else { '0' }))"
        " }"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command, str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return (None, "revocation checker unavailable")
    if result.returncode != 0:
        return (None, "revocation command failed")

    status_text = result.stdout.strip()
    if not status_text:
        return (None, "no revocation status returned")
    if status_text == "NOSIGNER":
        return (False, "no signer certificate")

    parts = status_text.split("|", 2)
    if len(parts) == 3:
        status, ocsp_flag, crl_flag = parts
        has_ocsp = ocsp_flag == "1"
        has_crl = crl_flag == "1"
    else:
        status = status_text
        has_ocsp = False
        has_crl = False

    normalized_mode = normalize_revocation_mode(mode)
    if status == "GOOD":
        if normalized_mode == "ocsp" and not has_ocsp:
            return (False, "certificate does not advertise an OCSP endpoint")
        if normalized_mode == "crl" and not has_crl:
            return (False, "certificate does not advertise a CRL distribution point")
        if normalized_mode == "both":
            missing: list[str] = []
            if not has_ocsp:
                missing.append("OCSP")
            if not has_crl:
                missing.append("CRL")
            if missing:
                return (False, "certificate is missing " + " and ".join(missing) + " endpoint metadata")
        return (True, f"good ({normalized_mode})")
    return (False, status)


def _parse_certificate_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
