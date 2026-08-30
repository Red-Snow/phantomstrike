"""
Security regression tests.

Each test here corresponds to a defect that was present in the codebase and
exploitable. They exist so the protections cannot be quietly removed: if a test
in this file fails, a real vulnerability has been reintroduced.

  test_execute_requires_api_key          unauthenticated RCE
  test_browser_origin_is_rejected        drive-by RCE from any visited website
  test_wildcard_cors_is_refused          wildcard origin config
  test_auth_enabled_without_keys_fails   auth that looks on but accepts anyone
  test_raw_shell_disabled_by_default     arbitrary command execution by default
  test_error_response_hides_internals    exception text leaked to the caller
  test_scope_* / test_engagement_*       unscoped scanning of arbitrary hosts
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from phantomstrike import config as config_module


API_KEY = "test-key-do-not-use-in-production"


def _build_app(monkeypatch, **env):
    """Rebuild settings and the app under a given environment."""
    defaults = {
        "PHANTOMSTRIKE_AUTH_ENABLED": "true",
        "PHANTOMSTRIKE_API_KEYS": API_KEY,
    }
    defaults.update(env)
    for key in (
        "PHANTOMSTRIKE_CORS_ORIGINS",
        "PHANTOMSTRIKE_ALLOW_RAW_SHELL",
        "PHANTOMSTRIKE_ENGAGEMENT",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in defaults.items():
        monkeypatch.setenv(key, value)

    importlib.reload(config_module)

    from phantomstrike.server import auth as auth_module
    from phantomstrike.server import app as app_module
    from phantomstrike.server.routes import jobs as jobs_routes
    from phantomstrike.server.routes import tools as tools_routes
    from phantomstrike.plugins import registry as registry_module
    from phantomstrike.execution import runner as runner_module

    # Order matters. registry.py rebinds its module-level singleton on reload,
    # and every module that did `from ...registry import registry` keeps its own
    # reference. The route modules must be reloaded after it, or they answer
    # requests from the previous test's registry.
    for module in (
        auth_module,
        registry_module,
        runner_module,
        tools_routes,
        jobs_routes,
        app_module,
    ):
        importlib.reload(module)

    return app_module.create_app()


# ── Authentication ────────────────────────────────────────────────────


def test_execute_requires_api_key(monkeypatch):
    """
    Unauthenticated execution must be refused.

    Previously: POST /api/tools/execute with no credentials returned 200 and ran
    the command. `AuthConfig` existed but no route consulted it.
    """
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/api/tools/execute",
            json={"tool": "kali_shell", "params": {"command": "id"}},
        )
    assert response.status_code == 401, (
        f"Unauthenticated execution returned {response.status_code} — "
        "authentication is not being enforced"
    )


def test_valid_api_key_is_accepted(monkeypatch):
    """A correct key must still get through — the control has to be usable."""
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/api/tools", headers={"X-API-Key": API_KEY})
    assert response.status_code == 200


def test_wrong_api_key_is_rejected(monkeypatch):
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/api/tools", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401


def test_auth_enabled_without_keys_fails_closed(monkeypatch):
    """
    Auth switched on with no keys must refuse to start.

    Otherwise the deployment reads as protected while accepting every caller.
    """
    monkeypatch.setenv("PHANTOMSTRIKE_AUTH_ENABLED", "true")
    monkeypatch.delenv("PHANTOMSTRIKE_API_KEYS", raising=False)
    importlib.reload(config_module)

    with pytest.raises(RuntimeError, match="no API keys are configured"):
        config_module.settings.auth.validate()


# ── Cross-origin protection ────────────────────────────────────────────


def test_browser_origin_is_rejected(monkeypatch):
    """
    A request carrying an unlisted browser Origin must be refused.

    Previously: CORS was allow_origins=["*"] with credentials, so the middleware
    reflected any origin. Combined with missing auth, any website the operator
    visited could execute commands on their host via 127.0.0.1.
    """
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/api/tools/execute",
            json={"tool": "nmap", "params": {"target": "127.0.0.1"}},
            headers={"X-API-Key": API_KEY, "Origin": "https://evil.example.com"},
        )
    assert response.status_code == 403, (
        f"Cross-origin request returned {response.status_code} — "
        "drive-by requests from web pages are not being blocked"
    )
    assert response.headers.get("access-control-allow-origin") != "https://evil.example.com"


def test_non_browser_client_has_no_origin_and_passes(monkeypatch):
    """CLI and MCP callers send no Origin and must be unaffected by the guard."""
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/api/tools", headers={"X-API-Key": API_KEY})
    assert response.status_code == 200


def test_wildcard_cors_is_refused(monkeypatch):
    """A wildcard origin must be rejected at config load, not silently honoured."""
    monkeypatch.setenv("PHANTOMSTRIKE_CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="not permitted"):
        importlib.reload(config_module)
    monkeypatch.delenv("PHANTOMSTRIKE_CORS_ORIGINS", raising=False)
    importlib.reload(config_module)


# ── Raw shell gating ──────────────────────────────────────────────────


def test_raw_shell_disabled_by_default(monkeypatch):
    """
    kali_shell must not be registered without an explicit opt-in.

    It accepts an arbitrary command string and bypasses every validator in
    utils.validation.
    """
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/api/tools", headers={"X-API-Key": API_KEY})
    names = [p["name"] for p in response.json().get("plugins", [])]
    assert "kali_shell" not in names, (
        "kali_shell is exposed without PHANTOMSTRIKE_ALLOW_RAW_SHELL — "
        "arbitrary command execution is available by default"
    )


def test_raw_shell_available_when_opted_in(monkeypatch):
    """The opt-in must actually work, or operators will disable auth instead."""
    app = _build_app(monkeypatch, PHANTOMSTRIKE_ALLOW_RAW_SHELL="true")
    with TestClient(app) as client:
        response = client.get("/api/tools", headers={"X-API-Key": API_KEY})
    names = [p["name"] for p in response.json().get("plugins", [])]
    assert "kali_shell" in names


@pytest.mark.asyncio
async def test_runner_refuses_shell_plugin_when_disabled(monkeypatch):
    """
    Defence in depth: even holding a plugin instance directly, the runner must
    refuse to execute it while the opt-in is off.
    """
    monkeypatch.delenv("PHANTOMSTRIKE_ALLOW_RAW_SHELL", raising=False)
    importlib.reload(config_module)

    from phantomstrike.execution import runner as runner_module
    from phantomstrike.plugins.generic.shell import KaliShellPlugin

    importlib.reload(runner_module)

    result = await runner_module.ToolRunner().run(
        KaliShellPlugin(), {"command": "id", "target": "localhost"}
    )
    assert not result.success
    assert "disabled" in (result.error_message or "").lower()


# ── Information disclosure ─────────────────────────────────────────────


def test_error_response_hides_internals(monkeypatch):
    """
    Unhandled errors must return a reference id, not the exception text.

    Raw messages leak filesystem paths, database URLs and internal structure.
    """
    app = _build_app(monkeypatch)

    @app.get("/api/_boom")
    async def boom():
        raise ValueError("secret path /home/operator/.phantomstrike/creds.db")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/_boom", headers={"X-API-Key": API_KEY})

    body = response.text
    assert "secret path" not in body
    assert "creds.db" not in body
    assert "reference" in body


# ── Engagement scope ──────────────────────────────────────────────────


def _engagement(tmp_path, in_scope, out_of_scope=()):
    path = tmp_path / "engagement.yaml"
    lines = ["client: Test Client", "in_scope:"]
    lines += [f"  - {entry}" for entry in in_scope]
    if out_of_scope:
        lines.append("out_of_scope:")
        lines += [f"  - {entry}" for entry in out_of_scope]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_scope_allows_in_scope_target(tmp_path):
    from phantomstrike.engagement import Engagement

    engagement = Engagement.load(_engagement(tmp_path, ["10.0.0.0/24", "*.example.com"]))
    engagement.check("10.0.0.5")
    engagement.check("https://app.example.com/login")


def test_scope_blocks_out_of_scope_target(tmp_path):
    """The core control: a host outside the engagement must be refused."""
    from phantomstrike.engagement import Engagement, ScopeViolation

    engagement = Engagement.load(_engagement(tmp_path, ["10.0.0.0/24"]))
    with pytest.raises(ScopeViolation):
        engagement.check("8.8.8.8")


def test_scope_exclusion_beats_inclusion(tmp_path):
    """An explicit exclusion must win over a broad inclusion."""
    from phantomstrike.engagement import Engagement, ScopeViolation

    engagement = Engagement.load(
        _engagement(tmp_path, ["10.0.0.0/8"], ["10.1.1.1"])
    )
    engagement.check("10.2.2.2")
    with pytest.raises(ScopeViolation, match="excluded"):
        engagement.check("10.1.1.1")


def test_scope_rejects_empty_engagement(tmp_path):
    """An engagement authorising nothing is a mistake, not a lockdown."""
    from phantomstrike.engagement import Engagement

    path = tmp_path / "empty.yaml"
    path.write_text("client: Test\nin_scope:\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no in_scope"):
        Engagement.load(path)


@pytest.mark.asyncio
async def test_runner_blocks_out_of_scope_execution(tmp_path, monkeypatch):
    """
    Enforcement must live in the execution path.

    An agent talked into a new target by hostile scan output still cannot reach
    a host outside the engagement.
    """
    monkeypatch.setenv("PHANTOMSTRIKE_ENFORCE_SCOPE", "true")
    importlib.reload(config_module)

    from phantomstrike import engagement as engagement_module
    from phantomstrike.execution import runner as runner_module
    from phantomstrike.plugins.network.nmap import NmapPlugin

    importlib.reload(runner_module)
    engagement_module.load_active(str(_engagement(tmp_path, ["10.0.0.0/24"])))

    try:
        result = await runner_module.ToolRunner().run(
            NmapPlugin(), {"target": "8.8.8.8"}
        )
        assert not result.success
        assert "out of scope" in (result.error_message or "").lower()
    finally:
        engagement_module.load_active(None)
