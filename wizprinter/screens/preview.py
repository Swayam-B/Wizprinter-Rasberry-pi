"""Preview screen — scan & exam preview, grading, polling, print with retry."""

import glob
import os
import threading

from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.uix.image import Image as KivyImage
from kivy.properties import BooleanProperty, StringProperty
from kivy.clock import Clock

import wizprinter.api_client as api
from wizprinter.utils.image_file import is_valid_jpeg
from wizprinter.utils.pdf_preview import pdf_to_png_paths
from wizprinter.utils.printer import PrinterManager

# ── Constants ─────────────────────────────────────────────────────────────────
PRINT_JOB_MAX_RETRIES = 3
PRINT_JOB_RETRY_DELAY = 4.0   # seconds between print retries
POLL_INTERVAL_SEC = 10.0       # seconds between batch/session polls
MAX_POLL_ATTEMPTS = 60         # give up after ~10 minutes


# ── Popup helper ──────────────────────────────────────────────────────────────

def _show_error_popup(title: str, message: str, on_retry=None):
    content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
    content.add_widget(Label(
        text=message,
        text_size=(dp(340), None),
        halign="center",
        valign="middle",
        font_size="13sp",
        color=(1, 0.88, 0.88, 1),
    ))
    btn_row = BoxLayout(orientation="horizontal", size_hint_y=None,
                        height=dp(44), spacing=dp(8))
    ok_btn = Button(text="OK", font_size="13sp")
    btn_row.add_widget(ok_btn)
    if on_retry:
        retry_btn = Button(text="Retry", font_size="13sp",
                           background_color=(0.08, 0.5, 0.9, 1))
        btn_row.add_widget(retry_btn)
    content.add_widget(btn_row)
    popup = Popup(
        title=title, content=content,
        size_hint=(None, None), size=(dp(400), dp(210)),
        auto_dismiss=True,
    )
    ok_btn.bind(on_release=lambda *a: popup.dismiss())
    if on_retry:
        retry_btn.bind(on_release=lambda *a: (popup.dismiss(), on_retry()))
    popup.open()
    return popup


# ── Screen ────────────────────────────────────────────────────────────────────

class PreviewScreen(Screen):
    page_info       = StringProperty("DOC: 0 PGS")
    show_success    = BooleanProperty(False)
    success_message = StringProperty("")

    scanned_pdf_path = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.printer = PrinterManager()
        self._preview_mode   = "none"   # "scan" | "exam"
        self._exam_row       = None
        self._exam_local_pdf = ""
        self._poll_attempts  = 0

    # ── Scan preview ──────────────────────────────────────────────────────────

    def show_scan_jpeg_previews(self):
        self._preview_mode   = "scan"
        self._exam_row       = None
        self._exam_local_pdf = ""
        Clock.schedule_once(self._build_scan_jpeg_preview, 0.05)

    def _build_scan_jpeg_preview(self, dt):
        container = self.ids.preview_container
        container.clear_widgets()
        temp_dir = "temp"
        if not os.path.exists(temp_dir):
            self.page_info = "Scan: 0 pg"
            return
        files = sorted(
            os.path.join(temp_dir, f)
            for f in os.listdir(temp_dir)
            if f.lower().endswith((".jpg", ".jpeg"))
            and is_valid_jpeg(os.path.join(temp_dir, f))
        )
        n = self._populate_image_paths(container, files)
        self.page_info = f"Scan · {n} pg"

    # ── Exam preview ─────────────────────────────────────────────────────────

    def load_exam_for_preview(self, exam: dict):
        self._preview_mode   = "exam"
        self._exam_row       = dict(exam)
        self.scanned_pdf_path = ""
        self._exam_local_pdf  = ""
        self.page_info        = "Loading…"
        self.ids.preview_container.clear_widgets()
        api.run_in_thread(
            self._thread_fetch_exam_as_pngs,
            on_success=self._apply_exam_png_preview,
            on_error=self._exam_preview_failed,
        )

    def _thread_fetch_exam_as_pngs(self):
        exam    = dict(self._exam_row)
        exam_id = exam.get("id")
        if not exam_id:
            raise ValueError("Exam has no id")

        pdf_dest = os.path.abspath(os.path.join("temp", "exam_paper_view.pdf"))
        api.download_exam_question_pdf(exam_id, pdf_dest)

        with open(pdf_dest, "rb") as fh:
            head = fh.read(5)
        if head != b"%PDF-":
            raise ValueError("Downloaded file is not a PDF.")

        render_dir = os.path.abspath(os.path.join("temp", "exam_render"))
        pngs = pdf_to_png_paths(pdf_dest, render_dir)
        if not pngs:
            raise ValueError("PDF has no renderable pages.")
        return {"pngs": pngs, "pdf": pdf_dest}

    def _apply_exam_png_preview(self, data):
        self._exam_local_pdf = data.get("pdf", "")
        container = self.ids.preview_container
        container.clear_widgets()
        n = self._populate_image_paths(container, data["pngs"])
        self.page_info = f"Exam PDF · {n} pg"

    def _exam_preview_failed(self, exc):
        self._exam_local_pdf = ""
        self.page_info = "Preview error"
        container = self.ids.preview_container
        container.clear_widgets()
        container.add_widget(Label(
            text=str(exc),
            color=(1, 0.45, 0.45, 1),
            font_size="11sp",
            size_hint_y=None,
            height=dp(120),
            text_size=(max(self.width - dp(16), dp(200)), None),
            halign="left",
            valign="top",
        ))
        _show_error_popup("Preview Error", str(exc))

    # ── Image grid ────────────────────────────────────────────────────────────

    def _populate_image_paths(self, container, paths) -> int:
        n = 0
        for path in paths:
            if not is_valid_jpeg(path):
                continue
            abs_path = os.path.abspath(path)
            img = KivyImage(
                source=abs_path,
                size_hint=(1, None),
                allow_stretch=True,
                keep_ratio=True,
            )
            img.height = container.width * 1.294
            container.bind(width=lambda c, w, i=img: setattr(i, "height", w * 1.294))
            img.reload()
            container.add_widget(img)
            n += 1
        return n

    # ── Grade document ────────────────────────────────────────────────────────

    def grade_document(self):
        sel      = api.get_selection()
        exam_id  = sel.get("exam_id")
        class_id = sel.get("class_id")
        pdf_path = self.scanned_pdf_path

        if class_id and not exam_id:
            App.get_running_app().navigate("documents")
            return

        if not exam_id:
            _show_error_popup("Selection Missing", "Please select an exam first.")
            return
        if not class_id:
            _show_error_popup("Selection Missing", "No class selected. Go back and select a class.")
            return
        if not pdf_path or not os.path.exists(pdf_path):
            _show_error_popup("No Scan", "No student scan found.\nUse Scan to capture pages first.")
            return

        self.success_message = "Submitting for grading…"
        self.show_success    = True
        self._poll_attempts  = 0

        api.run_in_thread(
            api.submit_grading_session,
            exam_id, class_id, pdf_path,
            on_success=self._on_submitted,
            on_error=self._on_grade_error,
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
            self._on_grade_error(Exception(f"Unexpected response: {data}"))

    # ── Batch polling ─────────────────────────────────────────────────────────

    def _schedule_poll_batch(self, batch_id):
        self._poll_attempts += 1
        if self._poll_attempts > MAX_POLL_ATTEMPTS:
            self._on_grade_error(Exception("Grading timed out. Please try again."))
            return
        threading.Thread(
            target=self._poll_batch_bg,
            args=(batch_id,),
            daemon=True,
        ).start()

    def _poll_batch_bg(self, batch_id):
        try:
            status = api.get_batch_status(batch_id)
            Clock.schedule_once(lambda dt: self._handle_batch_status(status, batch_id), 0)
        except api.RateLimitedError as e:
            # Respect the limiter — back off and retry
            Clock.schedule_once(
                lambda dt: self._schedule_poll_batch(batch_id),
                POLL_INTERVAL_SEC * 2,
            )
        except Exception as e:
            Clock.schedule_once(lambda dt, err=e: self._on_grade_error(err), 0)

    def _handle_batch_status(self, status, batch_id):
        total     = status.get("total", 1)
        completed = status.get("completed", 0)
        failed    = status.get("failed", 0)
        overall   = status.get("status", "")

        self.success_message = f"Grading… {completed}/{total} complete"

        if overall == "completed" or (completed + failed) >= total:
            graded_url = next(
                (s["graded_url"] for s in status.get("sessions", [])
                 if s.get("status") == "completed" and s.get("graded_url")),
                None,
            )
            if graded_url:
                self._download_and_print(graded_url)
            else:
                self.success_message = "Grading complete (no PDF returned)."
                Clock.schedule_once(self._finish, 3.0)
        else:
            Clock.schedule_once(
                lambda dt: self._schedule_poll_batch(batch_id), POLL_INTERVAL_SEC
            )

    # ── Session polling ───────────────────────────────────────────────────────

    def _schedule_poll_session(self, session_id):
        self._poll_attempts += 1
        if self._poll_attempts > MAX_POLL_ATTEMPTS:
            self._on_grade_error(Exception("Grading timed out. Please try again."))
            return
        threading.Thread(
            target=self._poll_session_bg,
            args=(session_id,),
            daemon=True,
        ).start()

    def _poll_session_bg(self, session_id):
        try:
            status = api.get_session_status(session_id)
            Clock.schedule_once(lambda dt: self._handle_session_status(status, session_id), 0)
        except api.RateLimitedError:
            Clock.schedule_once(
                lambda dt: self._schedule_poll_session(session_id),
                POLL_INTERVAL_SEC * 2,
            )
        except Exception as e:
            Clock.schedule_once(lambda dt, err=e: self._on_grade_error(err), 0)

    def _handle_session_status(self, status, session_id):
        state = status.get("status", "")
        self.success_message = f"Grading… ({state})"

        if state == "completed":
            graded_url = status.get("graded_url")
            if graded_url:
                self._download_and_print(graded_url)
            else:
                self.success_message = "Grading complete (no PDF returned)."
                Clock.schedule_once(self._finish, 3.0)
        elif state == "failed":
            self._on_grade_error(Exception(status.get("error", "Grading failed")))
        else:
            Clock.schedule_once(
                lambda dt: self._schedule_poll_session(session_id), POLL_INTERVAL_SEC
            )

    # ── Download + print with retry ───────────────────────────────────────────

    def _download_and_print(self, graded_url):
        self.success_message = "Downloading graded PDF…"
        dest = os.path.abspath(os.path.join("temp", "graded_result.pdf"))

        def do_download():
            try:
                api.download_graded_pdf(graded_url, dest)
                Clock.schedule_once(lambda dt: self._send_to_printer(dest, attempt=0), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt, err=e: self._on_grade_error(err), 0)

        threading.Thread(target=do_download, daemon=True).start()

    def _send_to_printer(self, pdf_path: str, attempt: int = 0):
        self.success_message = f"Printing… (attempt {attempt + 1})"
        printer_name = getattr(App.get_running_app(), "selected_printer", None)

        def bg():
            try:
                import cups
                conn = cups.Connection()
                if not printer_name or printer_name not in conn.getPrinters():
                    raise RuntimeError(f"Printer '{printer_name}' not available.")
                options = {"media": "na_letter_8.5x11in", "scaling": "100"}
                job_id = conn.printFile(printer_name, pdf_path, "WizPrinter_Job", options)
                Clock.schedule_once(lambda dt: self._on_print_success(job_id), 0)
            except Exception as e:
                Clock.schedule_once(
                    lambda dt, err=e: self._on_print_error(err, pdf_path, attempt), 0
                )

        threading.Thread(target=bg, daemon=True).start()

    def _on_print_success(self, job_id):
        self.success_message = f"✓ Printed (job #{job_id})"
        Clock.schedule_once(self._finish, 3.0)

    def _on_print_error(self, exc, pdf_path, attempt):
        if attempt < PRINT_JOB_MAX_RETRIES - 1:
            self.success_message = f"Print error — retrying ({attempt + 2}/{PRINT_JOB_MAX_RETRIES})…"
            Clock.schedule_once(
                lambda dt: self._send_to_printer(pdf_path, attempt + 1),
                PRINT_JOB_RETRY_DELAY,
            )
        else:
            self.show_success = False

            def retry_print():
                self.success_message = "Retrying print…"
                self.show_success    = True
                self._send_to_printer(pdf_path, attempt=0)

            _show_error_popup(
                "Print Failed",
                f"Could not print after {PRINT_JOB_MAX_RETRIES} attempts.\n{exc}\n\n"
                "Check printer connection and tap Retry.",
                on_retry=retry_print,
            )

    # ── Grade error ───────────────────────────────────────────────────────────

    def _on_grade_error(self, exc):
        self.show_success = False

        def retry_grade():
            self.grade_document()

        _show_error_popup(
            "Grading Error",
            str(exc),
            on_retry=retry_grade,
        )

    def _finish(self, dt):
        self.show_success = False
        App.get_running_app().navigate("dashboard")

    # ── Manual print ─────────────────────────────────────────────────────────

    def print_document(self):
        pdf_path = self.scanned_pdf_path or self._exam_local_pdf
        if not pdf_path or not os.path.exists(pdf_path):
            _show_error_popup("No Document", "No document to print.")
            return
        self.success_message = "Sending to printer…"
        self.show_success    = True
        self._send_to_printer(pdf_path, attempt=0)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def go_back(self):
        App.get_running_app().navigate("dashboard", direction="right")

    def delete_document(self):
        temp_dir = "temp"
        if os.path.isdir(temp_dir):
            for f in os.listdir(temp_dir):
                if f.lower().endswith((".jpg", ".jpeg")):
                    try:
                        os.remove(os.path.join(temp_dir, f))
                    except OSError:
                        pass
            for pattern in ("exam_paper_view.pdf",):
                p = os.path.join(temp_dir, pattern)
                if os.path.isfile(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        for old in glob.glob(os.path.join("temp", "exam_render", "exam_page_*.png")):
            try:
                os.remove(old)
            except OSError:
                pass
        self.scanned_pdf_path = ""
        self._exam_local_pdf  = ""
        self._exam_row        = None
        self._preview_mode    = "none"
        App.get_running_app().navigate("dashboard", direction="right")
