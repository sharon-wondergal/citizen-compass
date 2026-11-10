"""Stage 14 tests: security headers, safe page code and production settings."""

import re
from pathlib import Path

import pytest

from app import create_app
from app.config import ProductionConfig

PROJECT = Path(__file__).resolve().parent.parent
TEMPLATES = sorted((PROJECT / "app" / "templates").rglob("*.html"))
SCRIPTS = sorted((PROJECT / "app" / "static" / "js").glob("*.js"))


@pytest.mark.parametrize("address", ["/", "/services", "/admin/login", "/api/v1", "/health"])
def test_every_response_has_security_headers(client, database, address):
    headers = client.get(address).headers
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in headers["Permissions-Policy"]


def test_scripts_cannot_run_inline(client, database):
    policy = client.get("/").headers["Content-Security-Policy"]
    script_rule = next(part for part in policy.split(";") if "script-src" in part)
    assert "unsafe-inline" not in script_rule
    assert "unsafe-eval" not in script_rule


def test_error_pages_have_headers_too(client, database):
    assert "Content-Security-Policy" in client.get("/no-such-page").headers


def test_https_only_header_is_production_only(client, database, monkeypatch):
    assert "Strict-Transport-Security" not in client.get("/health").headers

    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "a" * 40)
    monkeypatch.setenv("FLASK_DEBUG", "0")
    production = create_app("production")
    assert "max-age=31536000" in production.test_client().get(
        "/no-such-page"
    ).headers["Strict-Transport-Security"]


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda path: path.name)
def test_templates_have_no_inline_scripts(template):
    """Inline code would be blocked by the policy, and is a common attack route."""
    text = template.read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", text), "inline <script>"
    assert not re.search(r"\son[a-z]+\s*=", text, re.IGNORECASE), "inline event handler"
    assert "javascript:" not in text


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda path: path.name)
def test_templates_never_switch_off_escaping(template):
    text = template.read_text(encoding="utf-8")
    assert "|safe" not in text
    assert "autoescape false" not in text


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: path.name)
def test_scripts_never_insert_raw_html(script):
    text = script.read_text(encoding="utf-8")
    assert "innerHTML" not in text
    assert "insertAdjacentHTML" not in text
    assert "eval(" not in text


def test_external_links_cannot_control_this_page():
    """Links that open a new tab must not give that tab access back to this one."""
    for template in TEMPLATES:
        for tag in re.findall(r"<a [^>]*target=\"_blank\"[^>]*>", template.read_text(encoding="utf-8")):
            assert 'rel="noopener noreferrer"' in tag, template.name


def test_proxy_support_is_off_unless_asked_for(app):
    assert app.config["TRUST_PROXY"] is False
    assert "ProxyFix" not in type(app.wsgi_app).__name__


def test_proxy_support_can_be_switched_on(monkeypatch):
    from app.config import TestingConfig

    monkeypatch.setattr(TestingConfig, "TRUST_PROXY", True)
    proxied = create_app("testing")
    assert type(proxied.wsgi_app).__name__ == "ProxyFix"
