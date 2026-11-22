"""Fail-closed public-https URL admission.

Untrusted URLs (model arguments, media sources, redirect locations) are
validated here. This module does not fetch unless a caller passes an explicit
transport; unit tests inject a fake transport so adversarial hosts are never
contacted.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Callable, Iterable, Sequence
from urllib.parse import urlparse, urlunparse

MAX_URL_CHARS = 2048
MAX_REDIRECTS = 3
ALLOWED_SCHEME = "https"

# CGNAT is not always "private" in ipaddress, and IPv4-mapped CGNAT can
# report is_global=True. Multicast IPv4 can also report is_global=True.
_CGNAT_V4 = ipaddress.ip_network("100.64.0.0/10")

Resolver = Callable[[str], Sequence[str]]
# transport(method, url, timeout) -> (status, location_or_none)
Transport = Callable[[str, str, float], tuple[int, str | None]]


class UrlPolicyError(ValueError):
    def __init__(self, code: str, error: str, fix: str) -> None:
        super().__init__(error)
        self.code = code
        self.error = error
        self.fix = fix


def _strip(url: str) -> str:
    if not isinstance(url, str):
        raise UrlPolicyError(
            "invalid_media_url",
            "Media URL must be a string.",
            "Pass a public https URL, or omit the image.",
        )
    # A2UI: trim whitespace and control characters first.
    cleaned = "".join(ch for ch in url.strip() if ord(ch) >= 32 and ch not in "")
    return cleaned.strip()


def _ip_from_literal(host: str) -> ipaddress._BaseAddress | None:
    raw = host.strip("[]")
    try:
        return ipaddress.ip_address(raw)
    except ValueError:
        return None


def is_public_ip(value: str | ipaddress._BaseAddress) -> bool:
    """Return True only if the address is safe to contact as a public HTTPS origin."""
    ip = value if isinstance(value, ipaddress._BaseAddress) else ipaddress.ip_address(value)
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return is_public_ip(mapped)
    if ip.version == 4 and ip in _CGNAT_V4:
        return False
    if (
        ip.is_multicast
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    ):
        return False
    return True


def default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    seen: list[str] = []
    for info in infos:
        addr = info[4][0]
        if addr not in seen:
            seen.append(addr)
    return seen


def _reject_host(host: str) -> None:
    if not host or host != host.strip():
        raise UrlPolicyError(
            "invalid_media_url",
            "Media URL host is missing or malformed.",
            "Use a public https URL with a normal hostname.",
        )
    if any(ord(ch) < 32 or ch == "" for ch in host):
        raise UrlPolicyError(
            "invalid_media_url",
            "Media URL host contains control characters.",
            "Use a public https URL with a normal hostname.",
        )
    if host.lower() in {"localhost", "localhost."} or host.lower().endswith(".localhost"):
        raise UrlPolicyError(
            "invalid_media_url",
            "Media URL must not point at localhost.",
            "Use a public https URL, or omit the image.",
        )


def validate_https_public_url(
    url: str,
    *,
    resolver: Resolver | None = None,
) -> str:
    """Admit a URL for later host-side load. Does not open a connection."""
    cleaned = _strip(url)
    if not cleaned or len(cleaned) > MAX_URL_CHARS:
        raise UrlPolicyError(
            "invalid_media_url",
            "Media URL is empty or too long.",
            "Use a public https URL under 2048 characters, or omit the image.",
        )
    if "\\" in cleaned:
        raise UrlPolicyError(
            "invalid_media_url",
            "Media URL must not contain backslashes.",
            "Use a public https URL, or omit the image.",
        )
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() != ALLOWED_SCHEME:
        raise UrlPolicyError(
            "invalid_media_url",
            "Media URL must be https.",
            "Use a public https URL. http, data, file, and relative URLs are rejected.",
        )
    if parsed.username is not None or parsed.password is not None:
        raise UrlPolicyError(
            "invalid_media_url",
            "Media URL must not contain credentials.",
            "Remove userinfo from the URL, or omit the image.",
        )
    if not parsed.hostname or parsed.scheme != "https" or not cleaned.lower().startswith("https://"):
        raise UrlPolicyError(
            "invalid_media_url",
            "Media URL must be a full https://host/... URL.",
            "Use a public https URL with a host, written as https://host/...",
        )
    host = parsed.hostname
    _reject_host(host)
    literal = _ip_from_literal(host)
    if literal is not None:
        if not is_public_ip(literal):
            raise UrlPolicyError(
                "invalid_media_url",
                "Media URL must not point at a private or non-public address.",
                "Use a public https URL, or omit the image.",
            )
        return cleaned

    resolve = resolver or default_resolver
    try:
        answers = list(resolve(host))
    except OSError:
        raise UrlPolicyError(
            "invalid_media_url",
            "Media URL host could not be resolved.",
            "Use a public https URL that resolves, or omit the image.",
        ) from None
    if not answers:
        raise UrlPolicyError(
            "invalid_media_url",
            "Media URL host resolved to no addresses.",
            "Use a public https URL, or omit the image.",
        )
    for addr in answers:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise UrlPolicyError(
                "invalid_media_url",
                "Media URL host resolved to an unreadable address.",
                "Use a public https URL, or omit the image.",
            ) from None
        if not is_public_ip(ip):
            raise UrlPolicyError(
                "invalid_media_url",
                "Media URL must not resolve to a private or non-public address.",
                "Use a public https URL, or omit the image.",
            )
    return cleaned


def follow_and_validate(
    url: str,
    *,
    resolver: Resolver | None = None,
    transport: Transport,
    timeout: float = 5.0,
) -> str:
    """Validate url, then every redirect hop, without using ambient proxies.

    The transport must not follow redirects itself. Tests inject a fake
    transport so reserved hosts are never contacted.
    """
    current = validate_https_public_url(url, resolver=resolver)
    for _ in range(MAX_REDIRECTS + 1):
        status, location = transport("HEAD", current, timeout)
        if status in {301, 302, 303, 307, 308}:
            if not location:
                raise UrlPolicyError(
                    "invalid_media_url",
                    "Media URL redirected without a Location.",
                    "Use a public https URL that does not bounce to a private host.",
                )
            current = validate_https_public_url(location, resolver=resolver)
            continue
        if 200 <= status < 300:
            return current
        raise UrlPolicyError(
            "invalid_media_url",
            "Media URL could not be fetched.",
            "Use a reachable public https URL, or omit the image.",
        )
    raise UrlPolicyError(
        "invalid_media_url",
        "Media URL followed too many redirects.",
        "Use a public https URL with at most 3 redirects, or omit the image.",
    )
