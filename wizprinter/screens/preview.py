"""Preview screen — scan & exam preview, grade submission, and manual print.

The poll/download/print state machine lives in GradingStatusMixin
(grading_status.py). Once grading completes, control hands off to
ReviewScreen for teacher review/approval before any output is finalized —
this screen only kicks grading off and reacts to completion/failure.
"""

import glob
import os

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
from wizprinter.grading import GradeOutputMode
from wizprinter.screens.grading_status import GradingStatusMixin
from wizprinter.utils.image_file import is_valid_jpeg
from wizprinter.utils.pdf_preview import pdf_to_png_paths


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

class PreviewScreen(GradingStatusMixin, Screen):
    page_info       = StringProperty("DOC: 0 PGS")
    show_success    = BooleanProperty(False)
    success_message = StringProperty("")

    scanned_pdf_path = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Printing is handled by GradingStatusMixin.send_to_printer (CUPS), not a
        # separate PrinterManager instance.
        self._preview_mode    = "none"   # "scan" | "exam"
        self._exam_row        = None
        self._exam_local_pdf  = ""
        self._active_exam_id  = ""
        self._active_class_id = ""
        self._pending_output_mode = GradeOutputMode.PRINT_AND_SEND
        self._grading_status_init()

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

        self._active_exam_id  = exam_id
        self._active_class_id = class_id
        self._show_grade_output_popup(exam_id, class_id, pdf_path)

    # ── Grade Output popup ────────────────────────────────────────────────────

    def _show_grade_output_popup(self, exam_id: str, class_id: str, pdf_path: str):
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
        content.add_widget(Label(
            text="Choose what happens once grading finishes.\n"
                 "You'll still review each student before anything is sent.",
            font_size="12sp", color=(0.8, 0.87, 0.95, 1),
            size_hint_y=None, height=dp(48),
            halign="center", valign="middle",
        ))

        print_send_btn = Button(
            text="Grade and Print + Send to WizPrinter",
            size_hint_y=None, height=dp(52), font_size="13sp", bold=True,
            background_color=(0.08, 0.5, 0.9, 1),
            halign="center", valign="middle",
        )
        send_only_btn = Button(
            text="Grade and Send to WizPrinter Only",
            size_hint_y=None, height=dp(52), font_size="13sp",
            halign="center", valign="middle",
        )
        cancel_btn = Button(
            text="Cancel", size_hint_y=None, height=dp(40), font_size="12sp",
        )
        for btn in (print_send_btn, send_only_btn):
            btn.bind(size=lambda w, v: setattr(w, "text_size", (v[0] - dp(16), v[1])))
        content.add_widget(print_send_btn)
        content.add_widget(send_only_btn)
        content.add_widget(cancel_btn)

        popup = Popup(
            title="Grade Output", content=content,
            size_hint=(None, None), size=(dp(380), dp(300)),
            auto_dismiss=False,
        )

        def choose(mode: GradeOutputMode):
            self._pending_output_mode = mode
            popup.dismiss()
            self.start_grading(exam_id, class_id, pdf_path)

        print_send_btn.bind(on_release=lambda *a: choose(GradeOutputMode.PRINT_AND_SEND))
        send_only_btn.bind(on_release=lambda *a: choose(GradeOutputMode.SEND_ONLY))
        cancel_btn.bind(on_release=lambda *a: popup.dismiss())
        popup.open()

    # ── GradingStatusMixin callbacks ──────────────────────────────────────────

    def _on_grading_complete(self, sessions: list):
        """Grading finished — hand off to ReviewScreen instead of auto-printing."""
        self.show_success = False
        app = App.get_running_app()
        review_screen = app.root.get_screen("review")
        review_screen.load_review(
            sessions=sessions,
            output_mode=self._pending_output_mode,
            exam=self._exam_row,
            exam_id=self._active_exam_id,
            class_id=self._active_class_id,
        )
        app.navigate("review")

    def _on_grading_failed(self, exc, *, timed_out: bool):
        self.show_success = False

        def retry_grade():
            self.grade_document()

        _show_error_popup(
            "Grading Timed Out" if timed_out else "Grading Error",
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

        def on_done(job_id):
            Clock.schedule_once(self._finish, 3.0)

        def on_error(exc):
            self.show_success = False

            def retry_print():
                self.success_message = "Retrying print…"
                self.show_success    = True
                self.send_to_printer(pdf_path, attempt=0, on_done=on_done, on_error=on_error)

            _show_error_popup(
                "Print Failed",
                f"Could not print after multiple attempts.\n{exc}\n\n"
                "Check printer connection and tap Retry.",
                on_retry=retry_print,
            )

        self.send_to_printer(pdf_path, attempt=0, on_done=on_done, on_error=on_error)

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
