"""Shared API client for WizPrinter Pi."""
from __future__ import annotations

import os
import threading
import time
import collections
import logging

import requests

logger = logging.getLogger(__name__)

# ── Retry policy (env overrides) ──────────────────────────────────────────────
_RETRY_MAX = max(1, int(os.environ.get("API_RETRY_MAX_ATTEMPTS", "5")))
_RETRY_BASE_SEC = float(os.environ.get("API_RETRY_BASE_SEC", "0.5"))
_RETRY_CAP_SEC = float(os.environ.get("API_RETRY_MAX_SLEEP_SEC", "30"))


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError):
        resp = getattr(exc, "response", None)
        if resp is not None:
            return resp.status_code in (408, 429, 500, 502, 503, 504)
    return False


def _call_with_backoff(fn):
    """Run fn() with exponential backoff between attempts on transient errors."""
    last: BaseException | None = None
    for attempt in range(_RETRY_MAX):
        try:
            return fn()
        except Exception as e:
            last = e
            if attempt >= _RETRY_MAX - 1 or not _is_transient(e):
                raise
            sleep_s = min(_RETRY_BASE_SEC * (2 ** attempt), _RETRY_CAP_SEC)
            time.sleep(sleep_s)
    assert last is not None
    raise last


def _request_with_backoff(method: str, url: str, **kwargs) -> requests.Response:
    """Perform an HTTP request with exponential backoff between retries."""

    def once():
        r = requests.request(method, url, **kwargs)
        r.raise_for_status()
        return r

    return _call_with_backoff(once)


# ── Per-endpoint rate limiter ──────────────────────────────────────────────────
# Tracks call timestamps per (method, endpoint-category) to enforce
# minimum intervals and prevent runaway polling/update-check loops.

class _RateLimiter:
    """Thread-safe sliding-window rate limiter."""

    def __init__(self):
        self._lock = threading.Lock()
        # Maps key -> deque of timestamps (float, epoch seconds)
        self._windows: dict[str, collections.deque] = {}
        # key -> (max_calls, window_seconds)
        self._rules: dict[str, tuple[int, float]] = {}

    def register(self, key: str, max_calls: int, window_sec: float):
        """Register a rate-limit rule for a named key."""
        with self._lock:
            self._rules[key] = (max_calls, window_sec)
            self._windows.setdefault(key, collections.deque())

    def check_and_record(self, key: str) -> bool:
        """Return True if the call is allowed; record it. False = throttled."""
        with self._lock:
            if key not in self._rules:
                return True  # unregistered keys are not limited
            max_calls, window_sec = self._rules[key]
            now = time.monotonic()
            dq = self._windows[key]
            # Prune expired entries
            while dq and now - dq[0] > window_sec:
                dq.popleft()
            if len(dq) >= max_calls:
                return False
            dq.append(now)
            return True

    def seconds_until_allowed(self, key: str) -> float:
        """How many seconds until the next call is allowed (0 if allowed now)."""
        with self._lock:
            if key not in self._rules:
                return 0.0
            max_calls, window_sec = self._rules[key]
            now = time.monotonic()
            dq = self._windows[key]
            while dq and now - dq[0] > window_sec:
                dq.popleft()
            if len(dq) < max_calls:
                return 0.0
            return window_sec - (now - dq[0])


_limiter = _RateLimiter()

# Rate-limit rules
# grading endpoint: max 3 submissions per 60 s (prevent accidental rapid resubmit)
_limiter.register("grade_submit",    max_calls=3,   window_sec=60.0)
# polling loop: poll at most once every 8 s per batch/session
_limiter.register("poll_batch",      max_calls=1,   window_sec=8.0)
_limiter.register("poll_session",    max_calls=1,   window_sec=8.0)
# update checks / remote-config: at most 1 per 5 minutes
_limiter.register("update_check",    max_calls=1,   window_sec=300.0)
_limiter.register("remote_config",   max_calls=1,   window_sec=300.0)


class RateLimitedError(Exception):
    """Raised when a call is blocked by the local rate limiter."""


def _assert_rate_limit(key: str):
    """Raise RateLimitedError if the call is not allowed right now."""
    if not _limiter.check_and_record(key):
        wait = _limiter.seconds_until_allowed(key)
        raise RateLimitedError(
            f"Rate limit reached for '{key}'. Retry in {wait:.1f}s."
        )


# ── Session state ──────────────────────────────────────────────────────────────
# Credentials are NEVER stored on disk or logged.
# Token lives only in process memory and is cleared on logout.

_token: str = ""
_professor_id: str = ""
_selected_semester_id: str = ""
_selected_subject_id: str = ""
_selected_class_id: str = ""
_selected_exam_id: str = ""

BASE_URL = os.environ.get("WIZPRINTER_API_URL", "http://localhost:8000")
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "")


def set_token(token: str):
    global _token
    _token = token


def get_token() -> str:
    return _token


def set_professor_id(pid: str):
    global _professor_id
    _professor_id = pid


def get_professor_id() -> str:
    return _professor_id


def set_selection(semester_id=None, subject_id=None, class_id=None, exam_id=None):
    global _selected_semester_id, _selected_subject_id, _selected_class_id, _selected_exam_id
    if semester_id is not None:
        _selected_semester_id = semester_id
    if subject_id is not None:
        _selected_subject_id = subject_id
    if class_id is not None:
        _selected_class_id = class_id
    if exam_id is not None:
        _selected_exam_id = exam_id


def get_selection():
    return {
        "semester_id": _selected_semester_id,
        "subject_id": _selected_subject_id,
        "class_id": _selected_class_id,
        "exam_id": _selected_exam_id,
    }


def clear_session():
    """Wipe all in-memory credentials and selections. Called on logout."""
    global _token, _professor_id
    global _selected_semester_id, _selected_subject_id, _selected_class_id, _selected_exam_id
    # Overwrite before clearing so the string object can't linger in memory
    _token = ""
    _professor_id = ""
    _selected_semester_id = _selected_subject_id = _selected_class_id = _selected_exam_id = ""


def _headers():
    """Return auth headers. Token is sourced from memory only, never disk."""
    if not _token:
        raise RuntimeError("No auth token. Please log in first.")
    return {"Authorization": f"Bearer {_token}"}


# ── API calls ─────────────────────────────────────────────────────────────────

def firebase_sign_in(email: str, password: str) -> dict:
    """Returns Firebase JSON (idToken, refreshToken) or raises on failure.
    Credentials are passed directly to Firebase and never written to disk.
    """
    if not FIREBASE_API_KEY:
        raise RuntimeError("FIREBASE_API_KEY not set in environment.")
    url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={FIREBASE_API_KEY}"
    )
    # NOTE: password is sent over HTTPS only; never logged here.
    resp = _request_with_backoff(
        "post",
        url,
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=20,
    )
    return resp.json()


def onboard_professor() -> dict:
    """POST /api/professors/onboard — call after firebase_sign_in."""
    return _request_with_backoff(
        "post",
        f"{BASE_URL}/api/professors/onboard",
        headers=_headers(),
        timeout=20,
    ).json()


def get_semesters() -> list:
    return _request_with_backoff(
        "get", f"{BASE_URL}/api/semesters", headers=_headers(), timeout=10
    ).json()


def get_subjects(semester_id: str) -> list:
    return _request_with_backoff(
        "get",
        f"{BASE_URL}/api/subjects",
        headers=_headers(),
        params={"semester_id": semester_id},
        timeout=10,
    ).json()


def get_classes(subject_id: str) -> list:
    return _request_with_backoff(
        "get",
        f"{BASE_URL}/api/classes/by-subject/{subject_id}",
        headers=_headers(),
        timeout=10,
    ).json()


def get_exams(subject_id: str) -> list:
    return _request_with_backoff(
        "get",
        f"{BASE_URL}/api/exams/by-subject/{subject_id}",
        headers=_headers(),
        timeout=10,
    ).json()


def get_exam(exam_id: str) -> dict:
    return _request_with_backoff(
        "get",
        f"{BASE_URL}/api/exams/{exam_id}",
        headers=_headers(),
        timeout=15,
    ).json()


def download_exam_question_pdf(exam_id: str, dest_path: str) -> None:
    """GET /api/exams/{exam_id}/pdf — question paper bytes (Bearer auth).
    dest_path is sanitized to prevent path traversal.
    """
    dest_abs = _safe_abspath(dest_path, allowed_prefix=os.path.abspath("temp"))
    parent = os.path.dirname(dest_abs)
    if parent:
        os.makedirs(parent, exist_ok=True)
    r = _request_with_backoff(
        "get",
        f"{BASE_URL}/api/exams/{exam_id}/pdf",
        headers=_headers(),
        timeout=120,
    )
    with open(dest_abs, "wb") as f:
        f.write(r.content)


def submit_grading_session(exam_id: str, class_id: str, pdf_path: str) -> dict:
    """POST /api/exams/{exam_id}/grade — rate limited to 3/60s."""
    _assert_rate_limit("grade_submit")

    # Sanitize the PDF path before opening it
    safe_pdf = _safe_abspath(pdf_path, allowed_prefix=os.path.abspath("temp"))

    def once():
        with open(safe_pdf, "rb") as f:
            resp = requests.post(
                f"{BASE_URL}/api/exams/{exam_id}/grade",
                headers=_headers(),
                data={"class_id": class_id},
                files={"file": (os.path.basename(safe_pdf), f, "application/pdf")},
                timeout=60,
            )
        resp.raise_for_status()
        return resp.json()

    return _call_with_backoff(once)


def get_batch_status(batch_id: str) -> dict:
    """GET /api/batches/{batch_id} — rate limited to 1/8s."""
    _assert_rate_limit("poll_batch")
    return _request_with_backoff(
        "get",
        f"{BASE_URL}/api/batches/{batch_id}",
        headers=_headers(),
        timeout=10,
    ).json()


def get_session_status(session_id: str) -> dict:
    """GET /api/sessions/{session_id} — rate limited to 1/8s."""
    _assert_rate_limit("poll_session")
    return _request_with_backoff(
        "get",
        f"{BASE_URL}/api/sessions/{session_id}",
        headers=_headers(),
        timeout=10,
    ).json()


def download_graded_pdf(url: str, dest_path: str):
    """Download SAS URL to a local file. No auth header — URL is self-authenticating."""
    dest_abs = _safe_abspath(dest_path, allowed_prefix=os.path.abspath("temp"))
    parent = os.path.dirname(dest_abs)
    if parent:
        os.makedirs(parent, exist_ok=True)
    resp = _request_with_backoff("get", url, timeout=60)
    with open(dest_abs, "wb") as f:
        f.write(resp.content)


def check_for_update() -> dict:
    """Remote update check — rate limited to once per 5 minutes."""
    _assert_rate_limit("update_check")
    return _request_with_backoff(
        "get",
        f"{BASE_URL}/api/updates/latest",
        headers=_headers(),
        timeout=10,
    ).json()


def fetch_remote_config() -> dict:
    """Remote config fetch — rate limited to once per 5 minutes."""
    _assert_rate_limit("remote_config")
    return _request_with_backoff(
        "get",
        f"{BASE_URL}/api/config",
        headers=_headers(),
        timeout=10,
    ).json()


# ── Path sanitization ─────────────────────────────────────────────────────────

def _safe_abspath(path: str, allowed_prefix: str) -> str:
    """Resolve path and ensure it stays within allowed_prefix.
    Raises ValueError on path-traversal attempts.
    """
    resolved = os.path.realpath(os.path.abspath(path))
    prefix = os.path.realpath(os.path.abspath(allowed_prefix))
    if not resolved.startswith(prefix + os.sep) and resolved != prefix:
        raise ValueError(
            f"Path traversal rejected: '{path}' resolves outside allowed dir."
        )
    return resolved


# ── Threading helper ──────────────────────────────────────────────────────────

def run_in_thread(fn, *args, on_success=None, on_error=None):
    """Run fn(*args) in a daemon thread.
    on_success(result) and on_error(exc) are called back on the Kivy main thread.
    """
    from kivy.clock import Clock

    def _run():
        try:
            result = fn(*args)
            if on_success:
                Clock.schedule_once(lambda dt, r=result: on_success(r), 0)
        except Exception as e:
            if on_error:
                Clock.schedule_once(lambda dt, err=e: on_error(err), 0)

    threading.Thread(target=_run, daemon=True).start()