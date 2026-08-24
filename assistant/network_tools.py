"""Read-only, GET-only network fetch tool with a strict domain allowlist.

This module intentionally cannot send data anywhere. It can only issue a GET
request to a URL whose host is already present in the local domain allowlist,
and it returns a truncated, size-capped text preview of the response.

It is NOT a general "send requests on your behalf" tool: there is no POST,
no PUT, no DELETE, no custom headers/body, and no way to reach a host that
was not explicitly allowlisted ahead of time.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_NETWORK_ALLOWLIST_PATH = Path("config/network_allowlist.json")
MAX_RESPONSE_CHARS = 4_000
DEFAULT_TIMEOUT_SECONDS = 10
MAX_CONTENT_BYTES = 2_000_000  # 2 MB hard cap read from the response


class NetworkToolError(RuntimeError):
    """Raised when a network fetch cannot be validated or completed safely."""


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    content_type: str
    body_preview: str
    truncated: bool

    def display_text(self) -> str:
        lines = [
            f"GET {self.url}",
            f"Status: {self.status_code}",
            f"Content-Type: {self.content_type or '(unknown)'}",
            "",
            self.body_preview,
        ]
        if self.truncated:
            lines.append(f"\n(Response truncated at {MAX_RESPONSE_CHARS} character(s).)")
        return "\n".join(lines)


def default_network_allowlist() -> list[str]:
    return []


def normalize_domain(domain: str) -> str:
    return domain.strip().lower().lstrip("www.")


def load_network_allowlist(path: str | Path = DEFAULT_NETWORK_ALLOWLIST_PATH) -> list[str]:
    allowlist_path = Path(path)
    if not allowlist_path.exists():
        return default_network_allowlist()
    try:
        raw = json.loads(allowlist_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise NetworkToolError(f"Invalid network allowlist JSON: {allowlist_path}") from exc
    except OSError as exc:
        raise NetworkToolError(f"Could not read network allowlist: {allowlist_path}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("allowed_domains"), list):
        raise NetworkToolError("Network allowlist must contain an 'allowed_domains' array.")

    domains: list[str] = []
    for item in raw["allowed_domains"]:
        if not isinstance(item, str) or not item.strip():
            raise NetworkToolError("Network allowlist domains must be non-empty strings.")
        domains.append(normalize_domain(item))
    return domains


def save_network_allowlist(domains: list[str], path: str | Path = DEFAULT_NETWORK_ALLOWLIST_PATH) -> None:
    allowlist_path = Path(path)
    allowlist_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"allowed_domains": sorted({normalize_domain(d) for d in domains})}
    allowlist_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def add_allowed_domain(domain: str, path: str | Path = DEFAULT_NETWORK_ALLOWLIST_PATH) -> list[str]:
    clean_domain = normalize_domain(domain)
    if not clean_domain:
        raise NetworkToolError("Domain cannot be empty.")
    domains = load_network_allowlist(path)
    if clean_domain not in domains:
        domains.append(clean_domain)
    save_network_allowlist(domains, path)
    return domains


def validate_fetch_url(url: str, allowlist_path: str | Path = DEFAULT_NETWORK_ALLOWLIST_PATH) -> str:
    """Validate a URL is https/http, well-formed, and on the domain allowlist.

    Returns the cleaned URL if valid, otherwise raises NetworkToolError.
    """
    clean_url = url.strip()
    if not clean_url:
        raise NetworkToolError("URL cannot be empty.")

    parsed = urlparse(clean_url)
    if parsed.scheme not in {"http", "https"}:
        raise NetworkToolError("Only http:// and https:// URLs can be fetched.")
    if not parsed.netloc:
        raise NetworkToolError("URL must include a host, e.g. https://example.com/page")

    host = normalize_domain(parsed.hostname or "")
    allowlist = load_network_allowlist(allowlist_path)
    if not allowlist:
        raise NetworkToolError(
            "No domains are allowlisted for network fetch yet. "
            "Add one first, e.g.: allow network domain example.com"
        )
    if host not in allowlist:
        raise NetworkToolError(
            f"'{host}' is not on the network allowlist. "
            f"Allowed domains: {', '.join(allowlist)}"
        )
    return clean_url


def fetch_url(
    url: str,
    allowlist_path: str | Path = DEFAULT_NETWORK_ALLOWLIST_PATH,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> FetchResult:
    """Perform a read-only GET request to an allowlisted URL.

    Raises NetworkToolError if the URL is not valid/allowlisted, or if the
    request fails.
    """
    clean_url = validate_fetch_url(url, allowlist_path)

    request = urllib.request.Request(clean_url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status_code = response.status
            content_type = response.headers.get("Content-Type", "")
            raw_body = response.read(MAX_CONTENT_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise NetworkToolError(f"Request failed with HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise NetworkToolError(f"Request failed: {exc.reason}") from exc
    except OSError as exc:
        raise NetworkToolError(f"Request failed: {exc}") from exc

    content_truncated_by_size = len(raw_body) > MAX_CONTENT_BYTES
    if content_truncated_by_size:
        raw_body = raw_body[:MAX_CONTENT_BYTES]

    try:
        text_body = raw_body.decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - decode with errors="replace" should not raise
        text_body = ""

    truncated = content_truncated_by_size or len(text_body) > MAX_RESPONSE_CHARS
    preview = text_body[:MAX_RESPONSE_CHARS]

    return FetchResult(
        url=clean_url,
        status_code=status_code,
        content_type=content_type,
        body_preview=preview,
        truncated=truncated,
    )


def network_allowlist_summary(path: str | Path = DEFAULT_NETWORK_ALLOWLIST_PATH) -> str:
    domains = load_network_allowlist(path)
    if not domains:
        return "Network fetch allowlist: empty. Add a domain with: allow network domain <domain>"
    lines = ["Network fetch allowlist (GET-only):"]
    lines.extend(f"- {domain}" for domain in domains)
    return "\n".join(lines)
