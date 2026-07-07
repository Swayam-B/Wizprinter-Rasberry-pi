"""
Unit tests for wizprinter.session — token lifecycle and, specifically, the
"Firebase token expiry mid-session" scenario requested for test coverage.

The real _SessionManager schedules a background threading.Timer to silently
refresh the token before expiry. If left un-patched, that timer would fire in
a background thread during these tests and hit the real network. Every test
here disables the timer (it isn't what we're testing — _do_refresh() is
called explicitly instead) so runs stay deterministic and fully offline.
"""
import pytest
import requests

from wizprinter.session import _SessionManager


class _NoopTimer:
    """Stand-in for threading.Timer that never actually fires."""

    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass

    def cancel(self):
        pass


@pytest.fixture
def mgr(monkeypatch):
    monkeypatch.setattr("wizprinter.session.threading.Timer", _NoopTimer)
    m = _SessionManager()
    yield m
    m.clear()


class TestSessionLifecycle:
    def test_start_sets_valid_token(self, mgr):
        mgr.start("id-token-1", "refresh-token-1", expires_in=3600)
        assert mgr.token == "id-token-1"
        assert mgr.is_valid is True

    def test_clear_wipes_token(self, mgr):
        mgr.start("id-token-1", "refresh-token-1", expires_in=3600)
        mgr.clear()
        assert mgr.token == ""
        assert mgr.is_valid is False

    def test_no_token_is_invalid(self, mgr):
        assert mgr.token == ""
        assert mgr.is_valid is False


class TestTokenExpiryMidSession:
    """Token must report invalid the instant `expires_in` has elapsed —
    without requiring a real wait for Firebase's 1-hour expiry."""

    def test_expired_token_reports_invalid(self, mgr):
        mgr.start("id-token-1", "refresh-token-1", expires_in=-1)
        assert mgr.is_valid is False
        # The token string itself is still readable even though it's expired.
        assert mgr.token == "id-token-1"

    def test_zero_ttl_expires_immediately(self, mgr):
        mgr.start("id-token-1", "refresh-token-1", expires_in=0)
        assert mgr.is_valid is False

    def test_valid_token_stays_valid_before_expiry(self, mgr):
        mgr.start("id-token-1", "refresh-token-1", expires_in=3600)
        assert mgr.is_valid is True


class TestSilentRefresh:
    def test_refresh_failure_does_not_raise(self, mgr, monkeypatch):
        """Network drops mid-session refresh — must not crash the app."""
        monkeypatch.setattr("wizprinter.session.FIREBASE_API_KEY", "fake-key")
        mgr.start("id-token-1", "refresh-token-1", expires_in=-1)

        def boom(*a, **kw):
            raise requests.ConnectionError("network down")

        monkeypatch.setattr("wizprinter.session.requests.post", boom)

        mgr._do_refresh()  # should not raise
        assert mgr.is_valid is False

    def test_refresh_success_updates_token(self, mgr, monkeypatch):
        monkeypatch.setattr("wizprinter.session.FIREBASE_API_KEY", "fake-key")
        mgr.start("old-token", "refresh-token-1", expires_in=-1)

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"id_token": "new-token", "refresh_token": "new-refresh",
                         "expires_in": 3600}

        monkeypatch.setattr("wizprinter.session.requests.post", lambda *a, **kw: FakeResponse())

        mgr._do_refresh()
        assert mgr.token == "new-token"
        assert mgr.is_valid is True

    def test_refresh_without_api_key_leaves_token_untouched(self, mgr, monkeypatch):
        monkeypatch.setattr("wizprinter.session.FIREBASE_API_KEY", "")
        mgr.start("id-token-1", "refresh-token-1", expires_in=-1)

        mgr._do_refresh()  # should not raise
        assert mgr.token == "id-token-1"  # unchanged; refresh never attempted

    def test_refresh_invokes_callbacks_on_success(self, mgr, monkeypatch):
        monkeypatch.setattr("wizprinter.session.FIREBASE_API_KEY", "fake-key")
        mgr.start("old-token", "refresh-token-1", expires_in=-1)

        seen = []
        mgr.on_refreshed(lambda new_token: seen.append(new_token))

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"id_token": "new-token", "expires_in": 3600}

        monkeypatch.setattr("wizprinter.session.requests.post", lambda *a, **kw: FakeResponse())
        mgr._do_refresh()

        assert seen == ["new-token"]
