"""Unit tests for wizprinter.api_client — backoff classification, rate
limiting, and path-traversal guarding around file downloads/uploads."""
import pytest
import requests

import wizprinter.api_client as api


class TestIsTransient:
    def test_timeout_is_transient(self):
        assert api._is_transient(requests.Timeout()) is True

    def test_connection_error_is_transient(self):
        assert api._is_transient(requests.ConnectionError()) is True

    def test_value_error_not_transient(self):
        assert api._is_transient(ValueError("nope")) is False

    def test_http_error_retryable_status(self):
        resp = requests.Response()
        resp.status_code = 503
        exc = requests.HTTPError(response=resp)
        assert api._is_transient(exc) is True

    def test_http_error_non_retryable_status(self):
        resp = requests.Response()
        resp.status_code = 401
        exc = requests.HTTPError(response=resp)
        assert api._is_transient(exc) is False

    def test_http_error_without_response(self):
        assert api._is_transient(requests.HTTPError()) is False


class TestRateLimiter:
    def test_allows_up_to_max_calls_then_blocks(self):
        limiter = api._RateLimiter()
        limiter.register("k", max_calls=2, window_sec=60.0)
        assert limiter.check_and_record("k") is True
        assert limiter.check_and_record("k") is True
        assert limiter.check_and_record("k") is False

    def test_unregistered_key_always_allowed(self):
        limiter = api._RateLimiter()
        assert limiter.check_and_record("unknown-key") is True

    def test_window_expiry_allows_again(self, monkeypatch):
        limiter = api._RateLimiter()
        limiter.register("k", max_calls=1, window_sec=10.0)
        t = [1000.0]
        monkeypatch.setattr(api.time, "monotonic", lambda: t[0])

        assert limiter.check_and_record("k") is True
        assert limiter.check_and_record("k") is False
        t[0] += 11.0  # past the 10s window
        assert limiter.check_and_record("k") is True

    def test_seconds_until_allowed(self, monkeypatch):
        limiter = api._RateLimiter()
        limiter.register("k", max_calls=1, window_sec=10.0)
        t = [1000.0]
        monkeypatch.setattr(api.time, "monotonic", lambda: t[0])

        limiter.check_and_record("k")
        assert limiter.seconds_until_allowed("k") == pytest.approx(10.0)

    def test_seconds_until_allowed_zero_when_capacity_free(self):
        limiter = api._RateLimiter()
        limiter.register("k", max_calls=2, window_sec=10.0)
        assert limiter.seconds_until_allowed("k") == 0.0


class TestAssertRateLimit:
    def test_raises_when_exhausted(self):
        api._limiter.register("test_key_raise_once", max_calls=1, window_sec=60.0)
        api._assert_rate_limit("test_key_raise_once")
        with pytest.raises(api.RateLimitedError):
            api._assert_rate_limit("test_key_raise_once")


class TestSafeAbspath:
    def test_allows_path_inside_prefix(self, tmp_path):
        allowed = tmp_path / "temp"
        allowed.mkdir()
        target = str(allowed / "file.pdf")
        result = api._safe_abspath(target, allowed_prefix=str(allowed))
        assert result == str(allowed / "file.pdf")

    def test_allows_prefix_itself(self, tmp_path):
        allowed = tmp_path / "temp"
        allowed.mkdir()
        result = api._safe_abspath(str(allowed), allowed_prefix=str(allowed))
        assert result == str(allowed)

    def test_rejects_path_traversal(self, tmp_path):
        allowed = tmp_path / "temp"
        allowed.mkdir()
        traversal = str(allowed / ".." / "outside.pdf")
        with pytest.raises(ValueError):
            api._safe_abspath(traversal, allowed_prefix=str(allowed))

    def test_rejects_sibling_directory_with_shared_prefix_string(self, tmp_path):
        allowed = tmp_path / "temp"
        allowed.mkdir()
        sibling = tmp_path / "temp_evil"
        sibling.mkdir()
        with pytest.raises(ValueError):
            api._safe_abspath(str(sibling / "file.pdf"), allowed_prefix=str(allowed))


class TestSelectionState:
    def test_set_and_get_selection_roundtrip(self):
        api.set_selection(semester_id="sem1", subject_id="sub1", class_id="cls1", exam_id="ex1")
        assert api.get_selection() == {
            "semester_id": "sem1", "subject_id": "sub1",
            "class_id": "cls1", "exam_id": "ex1",
        }

    def test_clear_session_resets_selection(self):
        api.set_selection(semester_id="sem1")
        api.clear_session()
        assert api.get_selection()["semester_id"] == ""

    def test_professor_id_roundtrip(self):
        api.set_professor_id("prof-123")
        assert api.get_professor_id() == "prof-123"
        api.clear_session()
        assert api.get_professor_id() == ""
