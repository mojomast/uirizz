"""Adversarial media URL tests. Reserved and private hosts are never contacted."""

from __future__ import annotations

import ipaddress

import pytest

from uirizz_plugin.urls import (
    UrlPolicyError,
    follow_and_validate,
    is_public_ip,
    validate_https_public_url,
)


def _public_resolver(_host: str) -> list[str]:
    return ["8.8.8.8"]  # documentation? 203.0.113.0/24 is TEST-NET-3, is_global?


def _mixed_resolver(_host: str) -> list[str]:
    return ["8.8.8.8", "10.0.0.1"]


def _rebinding_resolver(calls: list[int]):
    def resolve(_host: str) -> list[str]:
        calls.append(1)
        # First look public, second look private — the guard must re-resolve
        # at each hop / call, never cache a previous public answer only.
        if len(calls) == 1:
            return ["8.8.8.8"]
        return ["127.0.0.1"]

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/pic.png",
        "data:image/png;base64,AAAA",
        "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg'></svg>",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "/relative/path.png",
        "https://user:pass@example.com/x.png",
        "https://127.0.0.1/x.png",
        "https://localhost/x.png",
        "https://10.0.0.1/x.png",
        "https://192.168.1.4/x.png",
        "https://169.254.169.254/latest/meta-data/",
        "https://[::1]/x.png",
        "https://[::ffff:127.0.0.1]/x.png",
        "https://[::ffff:169.254.169.254]/x.png",
        "https://100.64.0.1/x.png",
        "https://[::ffff:100.64.0.1]/x.png",
        "https://224.0.0.1/x.png",
        "https://0.0.0.0/x.png",
        "https:example.com/x.png",
        "//example.com/x.png",
        "https://example.com\\@127.0.0.1/x.png",
    ],
)
def test_rejects_disallowed_schemes_and_literal_private_hosts(url):
    with pytest.raises(UrlPolicyError) as exc:
        validate_https_public_url(url, resolver=lambda h: [_ for _ in ()])
    assert exc.value.code == "invalid_media_url"


def test_accepts_public_https_with_injected_resolver():
    url = validate_https_public_url(
        "https://images.example.com/a.png",
        resolver=_public_resolver,
    )
    assert url.startswith("https://")


def test_rejects_mixed_public_and_private_dns_answers():
    with pytest.raises(UrlPolicyError):
        validate_https_public_url(
            "https://evil.example/a.png",
            resolver=_mixed_resolver,
        )


def test_rejects_localhost_and_metadata_hostnames_without_contacting_them():
    def explode(_host: str) -> list[str]:
        raise AssertionError("resolver must not be called for localhost literals / names")

    for url in (
        "https://localhost/x.png",
        "https://127.0.0.1/x.png",
        "https://169.254.169.254/x.png",
    ):
        with pytest.raises(UrlPolicyError):
            validate_https_public_url(url, resolver=explode)


def test_rebinding_second_lookup_is_checked():
    calls: list[int] = []
    resolve = _rebinding_resolver(calls)
    first = validate_https_public_url("https://rebind.example/a.png", resolver=resolve)
    assert first.startswith("https://")
    with pytest.raises(UrlPolicyError):
        validate_https_public_url("https://rebind.example/a.png", resolver=resolve)


def test_public_to_private_redirect_rejected_without_contacting_hosts():
    hops = {"https://cdn.example/start.png": (302, "https://127.0.0.1/secret.png")}

    def transport(_method: str, url: str, _timeout: float) -> tuple[int, str | None]:
        return hops[url]

    def resolve(host: str) -> list[str]:
        if host == "cdn.example":
            return ["8.8.8.8"]
        raise AssertionError(f"must not resolve or contact {host}")

    with pytest.raises(UrlPolicyError):
        follow_and_validate(
            "https://cdn.example/start.png",
            resolver=resolve,
            transport=transport,
        )


def test_cgnat_and_multicast_are_not_public():
    assert is_public_ip("8.8.8.8") is True
    assert is_public_ip("100.64.0.1") is False
    assert is_public_ip("224.0.0.1") is False
    assert is_public_ip(ipaddress.ip_address("::ffff:100.64.0.1")) is False
    assert is_public_ip(ipaddress.ip_address("::ffff:8.8.8.8")) is True
