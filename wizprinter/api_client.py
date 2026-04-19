"""Shared API client for WizPrinter Pi."""
from __future__ import annotations

import os
import threading
import time

import requests

# ── Retry policy (env overrides) ───────────────────────────────────────────────
# Retries only on transient failures (timeouts, connection errors, 429 / 5xx).
# Does not retry 4xx auth/validation errors (wastes time on wrong password, etc.).
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
    """
    Run fn() with exponential backoff between attempts on transient errors.
    Use for any API-shaped callable (HTTP or otherwise).
    """
    last: BaseException | None = None
    for attempt in range(_RETRY_MAX):
        try:
            return fn()
        except Exception as e:
            last = e
            if attempt >= _RETRY_MAX - 1 or not _is_transient(e):
                raise
            sleep_s = min(_RETRY_BASE_SEC * (2**attempt), _RETRY_CAP_SEC)
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


# ── Session state (in-memory, cleared on logout) ──────────────────────────────
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


def set_selection(semester_id="", subject_id="", class_id="", exam_id=""):
    global _selected_semester_id, _selected_subject_id, _selected_class_id, _selected_exam_id
    if semester_id:
        _selected_semester_id = semester_id
    if subject_id:
        _selected_subject_id = subject_id
    if class_id:
        _selected_class_id = class_id
    if exam_id:
        _selected_exam_id = exam_id


def get_selection():
    return {
        "semester_id": _selected_semester_id,
        "subject_id": _selected_subject_id,
        "class_id": _selected_class_id,
        "exam_id": _selected_exam_id,
    }


def clear_session():
    global _token, _professor_id
    global _selected_semester_id, _selected_subject_id, _selected_class_id, _selected_exam_id
    _token = _professor_id = ""
    _selected_semester_id = _selected_subject_id = _selected_class_id = _selected_exam_id = ""


def _headers():
    return {"Authorization": f"Bearer {_token}"}


def firebase_sign_in(email: str, password: str) -> dict:
    """Returns Firebase JSON (idToken, refreshToken) or raises on failure."""
    url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={FIREBASE_API_KEY}"
    )
    resp = _request_with_backoff(
        "post",
        url,
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=200,
    )
    return resp.json()


def onboard_professor() -> dict:
    """POST /api/professors/onboard — call after firebase_sign_in."""
    return _request_with_backoff(
        "post",
        f"{BASE_URL}/api/professors/onboard",
        headers=_headers(),
        timeout=200,
    ).json()


def get_semesters() -> list:
    """GET /api/semesters"""
    return _request_with_backoff(
        "get", f"{BASE_URL}/api/semesters", headers=_headers(), timeout=10
    ).json()


def get_subjects(semester_id: str) -> list:
    """GET /api/subjects?semester_id=<uuid>"""
    return _request_with_backoff(
        "get",
        f"{BASE_URL}/api/subjects",
        headers=_headers(),
        params={"semester_id": semester_id},
        timeout=10,
    ).json()


def get_classes(subject_id: str) -> list:
    """GET /api/classes/by-subject/<uuid>"""
    return _request_with_backoff(
        "get",
        f"{BASE_URL}/api/classes/by-subject/{subject_id}",
        headers=_headers(),
        timeout=10,
    ).json()


def get_exams(subject_id: str) -> list:
    """GET /api/exams/by-subject/<uuid>"""
    return _request_with_backoff(
        "get",
        f"{BASE_URL}/api/exams/by-subject/{subject_id}",
        headers=_headers(),
        timeout=10,
    ).json()


def get_exam(exam_id: str) -> dict:
    """GET /api/exams/{exam_id} — full exam row (often includes paper PDF URL)."""
    return _request_with_backoff(
        "get",
        f"{BASE_URL}/api/exams/{exam_id}",
        headers=_headers(),
        timeout=15,
    ).json()


def download_exam_question_pdf(exam_id: str, dest_path: str) -> None:
    """GET /api/exams/{exam_id}/pdf — question paper bytes (Bearer auth)."""
    dest_abs = os.path.abspath(dest_path)
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
    """
    POST /api/exams/{exam_id}/grade
    Multipart: class_id (form field), file (PDF, field name must be 'file').
    Returns { batch_id, count, sessions[] } for batch
         or { session_id, status, batch_id } for single.
    """

    def once():
        with open(pdf_path, "rb") as f:
            resp = requests.post(
                f"{BASE_URL}/api/exams/{exam_id}/grade",
                headers=_headers(),
                data={"class_id": class_id},
                files={"file": (os.path.basename(pdf_path), f, "application/pdf")},
                timeout=60,
            )
        resp.raise_for_status()
        return resp.json()

    return _call_with_backoff(once)


def get_batch_status(batch_id: str) -> dict:
    """GET /api/batches/{batch_id}"""
    return _request_with_backoff(
        "get",
        f"{BASE_URL}/api/batches/{batch_id}",
        headers=_headers(),
        timeout=10,
    ).json()


def get_session_status(session_id: str) -> dict:
    """GET /api/sessions/{session_id}"""
    return _request_with_backoff(
        "get",
        f"{BASE_URL}/api/sessions/{session_id}",
        headers=_headers(),
        timeout=10,
    ).json()


def download_graded_pdf(url: str, dest_path: str):
    """Download SAS URL to a local file. No auth header — URL is self-authenticating."""
    dest_abs = os.path.abspath(dest_path)
    parent = os.path.dirname(dest_abs)
    if parent:
        os.makedirs(parent, exist_ok=True)
    resp = _request_with_backoff("get", url, timeout=60)
    with open(dest_abs, "wb") as f:
        f.write(resp.content)


def run_in_thread(fn, *args, on_success=None, on_error=None):
    """
    Run fn(*args) in a daemon thread.
    on_success(result) and on_error(exc) are called back on the Kivy main thread.
    """
    from kivy.clock import Clock

    def _run():
        try:
            result = fn(*args)
            if on_success:
                # Default-arg binds now; avoids late-binding bugs with `result`.
                Clock.schedule_once(lambda dt, r=result: on_success(r), 0)
        except Exception as e:
            if on_error:
                # Exception name `e` is cleared after `except`; bind for the callback.
                Clock.schedule_once(lambda dt, err=e: on_error(err), 0)

    threading.Thread(target=_run, daemon=True).start()
