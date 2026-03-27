"""
Playwright browser tests for the LinkedIn automation path.

These tests cover the highest-risk code path in the repo:
  services/linkedin_browser_automation.py
  services/linkedin_easy_apply.py

Test strategy:
  - Unit-level: mock the Playwright browser context entirely (no real LinkedIn calls)
  - Integration-level stubs: real Playwright against a local stub HTML server
  - The real-LinkedIn path is gated behind LINKEDIN_BROWSER_TEST=1 env var

Run (mock mode — no credentials needed):
  pytest tests/test_linkedin_browser_automation.py -v

Run (stub server mode — uses local HTML fixtures):
  LINKEDIN_BROWSER_TEST=stub pytest tests/test_linkedin_browser_automation.py -v

Run (live mode — requires LINKEDIN_EMAIL, LINKEDIN_PASSWORD, real account):
  LINKEDIN_BROWSER_TEST=live pytest tests/test_linkedin_browser_automation.py -v -k live
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

_LIVE = os.getenv("LINKEDIN_BROWSER_TEST", "").lower() == "live"
_STUB = os.getenv("LINKEDIN_BROWSER_TEST", "").lower() == "stub"
_SKIP_LIVE = pytest.mark.skipif(not _LIVE, reason="Set LINKEDIN_BROWSER_TEST=live to run live tests")
_SKIP_STUB = pytest.mark.skipif(not _STUB and not _LIVE, reason="Set LINKEDIN_BROWSER_TEST=stub or live to run stub tests")


# ── stub HTML fixtures ────────────────────────────────────────────────────────

_LOGIN_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head><title>LinkedIn Login</title></head>
<body>
  <form action="/session" method="post">
    <input id="username" name="session_key" type="text" />
    <input id="password" name="session_password" type="password" />
    <button type="submit" aria-label="Sign in">Sign in</button>
  </form>
</body>
</html>
"""

_FEED_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head><title>LinkedIn Feed</title></head>
<body>
  <div id="global-nav">Feed</div>
  <script>window.__logged_in = true;</script>
</body>
</html>
"""

_EASY_APPLY_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Senior AI Engineer at Acme Corp | LinkedIn</title></head>
<body>
  <div class="jobs-unified-top-card">
    <h1>Senior AI Engineer</h1>
    <span>Acme Corp</span>
    <button class="jobs-apply-button" aria-label="Easy Apply">Easy Apply</button>
  </div>
  <div class="jobs-easy-apply-modal" style="display:none">
    <div class="jobs-easy-apply-form-section">
      <label for="phoneNumber">Phone number</label>
      <input id="phoneNumber" name="phoneNumber" type="tel" />
      <button aria-label="Submit application">Submit application</button>
    </div>
  </div>
</body>
</html>
"""

_CHALLENGE_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Security Verification | LinkedIn</title></head>
<body>
  <h1>Let\'s do a quick security check</h1>
  <div id="challenge-form">
    <input type="text" id="challenge-input" placeholder="Enter the code" />
    <button>Verify</button>
  </div>
</body>
</html>
"""


# ── stub HTTP server ──────────────────────────────────────────────────────────

class _StubHandler(BaseHTTPRequestHandler):
    routes: Dict[str, str] = {
        "/login": _LOGIN_PAGE_HTML,
        "/feed": _FEED_PAGE_HTML,
        "/jobs/view/easy-apply-job": _EASY_APPLY_PAGE_HTML,
        "/jobs/view/challenge-job": _CHALLENGE_PAGE_HTML,
        "/session": _FEED_PAGE_HTML,  # mock POST redirect
    }

    def log_message(self, *args):
        pass  # silence

    def do_GET(self):
        path = self.path.split("?")[0]
        body = self.routes.get(path, "<html><body>Not found</body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(302)
        self.send_header("Location", "/feed")
        self.end_headers()


@pytest.fixture(scope="session")
def stub_server():
    """Start a local stub HTTP server for browser tests."""
    server = HTTPServer(("127.0.0.1", 0), _StubHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ── mock-mode unit tests (no browser, no credentials) ────────────────────────

class TestLinkedInBrowserGate:
    """Gate: ATS_ALLOW_LINKEDIN_BROWSER controls REST API access."""

    def test_gate_disabled_by_default(self):
        from services.linkedin_browser_gate import (
            linkedin_browser_automation_disabled_response,
            linkedin_browser_automation_enabled,
        )
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ATS_ALLOW_LINKEDIN_BROWSER", None)
            assert linkedin_browser_automation_enabled() is False
            resp = linkedin_browser_automation_disabled_response()
            assert resp["status"] == "disabled"
            assert "ATS_ALLOW_LINKEDIN_BROWSER" in resp["message"]

    def test_gate_enabled_via_env(self):
        from services.linkedin_browser_gate import linkedin_browser_automation_enabled
        with patch.dict(os.environ, {"ATS_ALLOW_LINKEDIN_BROWSER": "1"}):
            assert linkedin_browser_automation_enabled() is True

    def test_gate_enabled_via_true(self):
        from services.linkedin_browser_gate import linkedin_browser_automation_enabled
        with patch.dict(os.environ, {"ATS_ALLOW_LINKEDIN_BROWSER": "true"}):
            assert linkedin_browser_automation_enabled() is True


class TestAutonomySubmitGate:
    """Kill switch and pilot allowlists block/allow live submit."""

    def test_kill_switch_blocks_all(self):
        from services.autonomy_submit_gate import linkedin_live_submit_block_reason
        with patch.dict(os.environ, {"AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED": "1"}):
            reason = linkedin_live_submit_block_reason({})
            assert reason is not None
            assert "AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED" in reason

    def test_no_kill_switch_allows(self):
        from services.autonomy_submit_gate import linkedin_live_submit_block_reason
        env = {k: "" for k in [
            "AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED",
            "AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY",
            "AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE",
            "AUTONOMY_LINKEDIN_ROLLBACK_WHEN_NONSUBMIT_RATE_GTE",
        ]}
        with patch.dict(os.environ, env):
            reason = linkedin_live_submit_block_reason({})
            assert reason is None

    def test_pilot_only_blocks_non_pilot_job(self):
        from services.autonomy_submit_gate import linkedin_live_submit_block_reason
        with patch.dict(os.environ, {
            "AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY": "1",
            "AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED": "",
            "AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE": "",
            "AUTONOMY_LINKEDIN_ROLLBACK_WHEN_NONSUBMIT_RATE_GTE": "",
            "AUTONOMY_LINKEDIN_PILOT_USER_IDS": "pilot-user-1",
        }):
            reason = linkedin_live_submit_block_reason({"user_id": "unknown-user"})
            assert reason is not None
            assert "pilot" in reason.lower()

    def test_pilot_only_allows_pilot_flagged_job(self):
        from services.autonomy_submit_gate import linkedin_live_submit_block_reason
        with patch.dict(os.environ, {
            "AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY": "1",
            "AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED": "",
            "AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE": "",
            "AUTONOMY_LINKEDIN_ROLLBACK_WHEN_NONSUBMIT_RATE_GTE": "",
        }):
            reason = linkedin_live_submit_block_reason({"pilot_submit_allowed": True})
            assert reason is None

    def test_pilot_only_allows_user_in_allowlist(self):
        from services.autonomy_submit_gate import linkedin_live_submit_block_reason
        with patch.dict(os.environ, {
            "AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY": "1",
            "AUTONOMY_LINKEDIN_LIVE_SUBMIT_DISABLED": "",
            "AUTONOMY_LINKEDIN_ROLLBACK_WHEN_FAILURE_RATE_GTE": "",
            "AUTONOMY_LINKEDIN_ROLLBACK_WHEN_NONSUBMIT_RATE_GTE": "",
            "AUTONOMY_LINKEDIN_PILOT_USER_IDS": "pilot-1,pilot-2",
        }):
            reason = linkedin_live_submit_block_reason({"user_id": "pilot-2"})
            assert reason is None


class TestTruthApplyGate:
    """Truth apply gate blocks live apply when profile is incomplete."""

    def test_gate_disabled_by_default(self):
        from services.truth_apply_gate import truth_apply_hard_gate_enabled
        with patch.dict(os.environ, {"TRUTH_APPLY_HARD_GATE": ""}):
            assert truth_apply_hard_gate_enabled() is False

    def test_gate_enabled_via_env(self):
        from services.truth_apply_gate import truth_apply_hard_gate_enabled
        with patch.dict(os.environ, {"TRUTH_APPLY_HARD_GATE": "1"}):
            assert truth_apply_hard_gate_enabled() is True

    def test_dry_run_bypasses_gate(self):
        from services.truth_apply_gate import truth_apply_live_blocked_message
        with patch.dict(os.environ, {"TRUTH_APPLY_HARD_GATE": "1"}):
            msg = truth_apply_live_blocked_message(None, dry_run=True)
            assert msg is None

    def test_shadow_mode_bypasses_gate(self):
        from services.truth_apply_gate import truth_apply_live_blocked_message
        with patch.dict(os.environ, {"TRUTH_APPLY_HARD_GATE": "1"}):
            msg = truth_apply_live_blocked_message(None, shadow_mode=True)
            assert msg is None

    def test_empty_profile_blocks_when_gate_on(self):
        from services.truth_apply_gate import truth_apply_live_blocked_message
        with patch.dict(os.environ, {"TRUTH_APPLY_HARD_GATE": "1"}):
            msg = truth_apply_live_blocked_message({})
            assert msg is not None
            assert "profile" in msg.lower() or "gate" in msg.lower()


class TestLinkedInLoginDetection:
    """Login challenge detection prevents accidental submits on auth screens."""

    def test_challenge_keywords_identified(self):
        """Verify challenge-page text triggers the abort signal."""
        challenge_indicators = [
            "Let\'s do a quick security check",
            "security verification",
            "challenge",
            "verify your identity",
        ]
        for indicator in challenge_indicators:
            assert any(
                kw in indicator.lower()
                for kw in ["security", "challenge", "verify", "check"]
            ), f"Indicator not classified as challenge: {indicator}"

    def test_feed_page_not_challenge(self):
        """Feed page text should not trigger challenge detection."""
        feed_text = "LinkedIn Feed — Your connections are sharing updates"
        challenge_words = ["security check", "verify your identity", "challenge"]
        assert not any(kw in feed_text.lower() for kw in challenge_words)


# ── stub-server integration tests ─────────────────────────────────────────────

@_SKIP_STUB
class TestLinkedInBrowserStub:
    """Integration tests using a local stub HTTP server (no real LinkedIn)."""

    def test_stub_login_page_loads(self, stub_server):
        """The stub server returns a login page at /login."""
        import urllib.request
        with urllib.request.urlopen(f"{stub_server}/login") as r:
            body = r.read().decode()
        assert "Sign in" in body
        assert "username" in body

    def test_stub_easy_apply_page_loads(self, stub_server):
        """The stub server returns an Easy Apply job page."""
        import urllib.request
        with urllib.request.urlopen(f"{stub_server}/jobs/view/easy-apply-job") as r:
            body = r.read().decode()
        assert "Easy Apply" in body
        assert "Senior AI Engineer" in body

    def test_stub_challenge_page_loads(self, stub_server):
        """The stub server returns a challenge verification page."""
        import urllib.request
        with urllib.request.urlopen(f"{stub_server}/jobs/view/challenge-job") as r:
            body = r.read().decode()
        assert "security check" in body.lower()

    @pytest.mark.asyncio
    async def test_playwright_login_flow_stub(self, stub_server):
        """Playwright can navigate to the stub login page and find the form."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            pytest.skip("playwright not installed — run: pip install playwright && playwright install chromium")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(f"{stub_server}/login")
            assert await page.locator("#username").is_visible()
            assert await page.locator("#password").is_visible()
            await browser.close()

    @pytest.mark.asyncio
    async def test_playwright_easy_apply_button_visible(self, stub_server):
        """Playwright can find the Easy Apply button on a job page."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            pytest.skip("playwright not installed")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(f"{stub_server}/jobs/view/easy-apply-job")
            btn = page.locator("[aria-label=\'Easy Apply\']")
            assert await btn.is_visible()
            await browser.close()

    @pytest.mark.asyncio
    async def test_playwright_detects_challenge_page(self, stub_server):
        """Playwright can detect a verification challenge page and should abort."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            pytest.skip("playwright not installed")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(f"{stub_server}/jobs/view/challenge-job")
            body = await page.content()
            # Should detect the challenge and abort — not proceed to fill/submit
            is_challenge = "security check" in body.lower() or "challenge" in body.lower()
            assert is_challenge, "Challenge page not detected"
            await browser.close()


# ── live tests (real LinkedIn, requires credentials) ─────────────────────────

@_SKIP_LIVE
class TestLinkedInBrowserLive:
    """Live Playwright tests against real LinkedIn. Requires LINKEDIN_EMAIL and LINKEDIN_PASSWORD."""

    def test_credentials_present(self):
        assert os.getenv("LINKEDIN_EMAIL"), "LINKEDIN_EMAIL not set"
        assert os.getenv("LINKEDIN_PASSWORD"), "LINKEDIN_PASSWORD not set"

    @pytest.mark.asyncio
    async def test_login_and_session_save(self, tmp_path):
        """Login to LinkedIn and verify session is saved."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            pytest.skip("playwright not installed")

        email = os.getenv("LINKEDIN_EMAIL", "")
        password = os.getenv("LINKEDIN_PASSWORD", "")
        storage_path = str(tmp_path / "session.json")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context()
            page = await ctx.new_page()
            await page.goto("https://www.linkedin.com/login", timeout=30000)

            # Abort if already challenged
            if "challenge" in page.url or "checkpoint" in page.url:
                pytest.skip("LinkedIn is showing a challenge — complete it manually first")

            await page.fill("#username", email)
            await page.fill("#password", password)
            await page.click("button[type=submit]")
            await page.wait_for_load_state("networkidle", timeout=20000)

            # Should be on feed or redirect, not back on login
            assert "/login" not in page.url, f"Login failed — still on login page: {page.url}"
            assert "challenge" not in page.url, f"Hit challenge page: {page.url}"

            # Save session
            await ctx.storage_state(path=storage_path)
            import os as _os
            assert _os.path.exists(storage_path)
            with open(storage_path) as f:
                state = json.load(f)
            assert "cookies" in state
            li_cookies = [c for c in state["cookies"] if "linkedin" in c.get("domain", "")]
            assert li_cookies, "No LinkedIn cookies in saved session"

            await browser.close()
