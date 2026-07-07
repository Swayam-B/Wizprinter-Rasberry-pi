"""
Grading-status mixin — the poll / download / print state machine extracted
out of PreviewScreen so it can be shared by any screen that needs to kick off
grading (PreviewScreen) or finalize output after teacher review (ReviewScreen),
without duplicating the polling/timeout/retry logic in two places.

Host class requirements
-----------------------
Any Screen using this mixin must define these Kivy properties:
    success_message = StringProperty("")
    show_success    = BooleanProperty(False)

And must implement:
    _on_grading_complete(self, sessions: list[dict]) -> None
        Called once grading finishes successfully, with a normalized list of
        session dicts (see wizprinter.grading module docstring for the
        assumed shape). Single-session exams are passed as a one-item list
        so callers only ever handle one shape.

    _on_grading_failed(self, exc: Exception, *, timed_out: bool) -> None
        Called if grading fails or times out. `timed_out` lets the caller
        show a distinct message/action for timeouts vs. other errors.
"""
from __future__ import annotations

import os
import threading

from kivy.app import App
from kivy.clock import Clock

import wizprinter.api_client as api
from wizprinter.hardware import MOCK_HARDWARE

POLL_INTERVAL_SEC     = 10.0
MAX_POLL_ATTEMPTS     = 60      # ~10 minutes at the interval above
PRINT_JOB_MAX_RETRIES = 3
PRINT_JOB_RETRY_DELAY = 4.0


class GradingTimeoutError(Exception):
    """Raised internally when polling exceeds MAX_POLL_ATTEMPTS."""


class GradingStatusMixin:
    """Shared poll/download/print state machine. Mix into a Kivy Screen."""

    def _grading_status_init(self):
        """Call once from the host screen's __init__."""
        self._poll_attempts = 0

    # ── Submit ────────────────────────────────────────────────────────────────

    def start_grading(self, exam_id: str, class_id: str, pdf_path: str):
        self._poll_attempts  = 0
        self.success_message = "Submitting for grading…"
        self.show_success    = True
        api.run_in_thread(
            api.submit_grading_session,
            exam_id, class_id, pdf_path,
            on_success=self._on_submitted,
            on_error=lambda e: self._on_grading_failed(e, timed_out=False),
        )

    def _on_submitted(self, data):
        batch_id   = data.get("batch_id")
        session_id = data.get("session_id")
        self.success_message = "Grading in progress…"

        if batch_id:
            Clock.schedule_once(lambda dt: self._schedule_poll_batch(batch_id), POLL_INTERVAL_SEC)
        elif session_id:
            Clock.schedule_once(lambda dt: self._schedule_poll_session(session_id), POLL_INTERVAL_SEC)
        else:
            self._on_grading_failed(Exception(f"Unexpected response: {data}"), timed_out=False)

    # ── Batch polling ─────────────────────────────────────────────────────────

    def _schedule_poll_batch(self, batch_id):
        self._poll_attempts += 1
        if self._poll_attempts > MAX_POLL_ATTEMPTS:
            self._fail_timeout()
            return
        threading.Thread(target=self._poll_batch_bg, args=(batch_id,), daemon=True).start()

    def _poll_batch_bg(self, batch_id):
        try:
            status = api.get_batch_status(batch_id)
            Clock.schedule_once(lambda dt: self._handle_batch_status(status, batch_id), 0)
        except api.RateLimitedError:
            Clock.schedule_once(lambda dt: self._schedule_poll_batch(batch_id), POLL_INTERVAL_SEC * 2)
        except Exception as e:
            Clock.schedule_once(lambda dt, err=e: self._on_grading_failed(err, timed_out=False), 0)

    def _handle_batch_status(self, status, batch_id):
        total     = status.get("total", 1)
        completed = status.get("completed", 0)
        failed    = status.get("failed", 0)
        overall   = status.get("status", "")

        self.success_message = f"Grading… {completed}/{total} complete"

        if overall == "completed" or (completed + failed) >= total:
            self._on_grading_complete(status.get("sessions", []))
        else:
            Clock.schedule_once(lambda dt: self._schedule_poll_batch(batch_id), POLL_INTERVAL_SEC)

    # ── Session polling (single-session exams) ───────────────────────────────

    def _schedule_poll_session(self, session_id):
        self._poll_attempts += 1
        if self._poll_attempts > MAX_POLL_ATTEMPTS:
            self._fail_timeout()
            return
        threading.Thread(target=self._poll_session_bg, args=(session_id,), daemon=True).start()

    def _poll_session_bg(self, session_id):
        try:
            status = api.get_session_status(session_id)
            Clock.schedule_once(lambda dt: self._handle_session_status(status, session_id), 0)
        except api.RateLimitedError:
            Clock.schedule_once(lambda dt: self._schedule_poll_session(session_id), POLL_INTERVAL_SEC * 2)
        except Exception as e:
            Clock.schedule_once(lambda dt, err=e: self._on_grading_failed(err, timed_out=False), 0)

    def _handle_session_status(self, status, session_id):
        state = status.get("status", "")
        self.success_message = f"Grading… ({state})"

        if state == "completed":
            # Normalize to the same list-of-sessions shape batch polling uses.
            self._on_grading_complete([status])
        elif state == "failed":
            self._on_grading_failed(Exception(status.get("error", "Grading failed")), timed_out=False)
        else:
            Clock.schedule_once(lambda dt: self._schedule_poll_session(session_id), POLL_INTERVAL_SEC)

    def _fail_timeout(self):
        minutes = int(MAX_POLL_ATTEMPTS * POLL_INTERVAL_SEC // 60)
        self._on_grading_failed(
            GradingTimeoutError(f"Grading timed out after ~{minutes} minutes. Please try again."),
            timed_out=True,
        )

    # ── Download + print with retry (used at finalize time) ──────────────────

    def download_and_print(self, graded_url, on_done=None, on_error=None):
        self.success_message = "Downloading graded PDF…"
        dest = os.path.abspath(os.path.join("temp", "graded_result.pdf"))

        def do_download():
            try:
                api.download_graded_pdf(graded_url, dest)
                Clock.schedule_once(
                    lambda dt: self.send_to_printer(dest, on_done=on_done, on_error=on_error), 0
                )
            except Exception as e:
                Clock.schedule_once(
                    lambda dt, err=e: (on_error(err) if on_error
                                       else self._on_grading_failed(err, timed_out=False)), 0
                )

        threading.Thread(target=do_download, daemon=True).start()

    def send_to_printer(self, pdf_path: str, attempt: int = 0, on_done=None, on_error=None):
        self.success_message = f"Printing… (attempt {attempt + 1})"
        printer_name = getattr(App.get_running_app(), "selected_printer", None)

        def bg():
            try:
                if MOCK_HARDWARE:
                    job_id = "mock-job"
                else:
                    import cups
                    conn = cups.Connection()
                    if not printer_name or printer_name not in conn.getPrinters():
                        raise RuntimeError(f"Printer '{printer_name}' not available.")
                    options = {"media": "na_letter_8.5x11in", "scaling": "100"}
                    job_id = conn.printFile(printer_name, pdf_path, "WizPrinter_Job", options)
                Clock.schedule_once(lambda dt: self._on_print_success(job_id, on_done), 0)
            except Exception as e:
                Clock.schedule_once(
                    lambda dt, err=e: self._on_print_error(err, pdf_path, attempt, on_done, on_error), 0
                )

        threading.Thread(target=bg, daemon=True).start()

    def _on_print_success(self, job_id, on_done):
        self.success_message = f"✓ Printed (job #{job_id})"
        if on_done:
            on_done(job_id)

    def _on_print_error(self, exc, pdf_path, attempt, on_done, on_error):
        if attempt < PRINT_JOB_MAX_RETRIES - 1:
            self.success_message = f"Print error — retrying ({attempt + 2}/{PRINT_JOB_MAX_RETRIES})…"
            Clock.schedule_once(
                lambda dt: self.send_to_printer(pdf_path, attempt + 1, on_done, on_error),
                PRINT_JOB_RETRY_DELAY,
            )
        elif on_error:
            on_error(exc)
