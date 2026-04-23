import glob
import os
import subprocess
import threading
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.uix.image import Image as KivyImage
from kivy.properties import BooleanProperty, StringProperty
from kivy.clock import Clock

import wizprinter.api_client as api
from wizprinter.utils.image_file import is_valid_jpeg
from wizprinter.utils.pdf_preview import pdf_to_png_paths
from wizprinter.utils.printer import PrinterManager


class PreviewScreen(Screen):
    page_info = StringProperty("DOC: 0 PGS")
    show_success = BooleanProperty(False)
    success_message = StringProperty("")

    # Student scan handoff from ScanScreen (multi-page PDF for grading)
    scanned_pdf_path = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.printer = PrinterManager()
        self._preview_mode = "none"  # "scan" | "exam"
        self._exam_row = None
        self._exam_local_pdf = ""

    def show_scan_jpeg_previews(self):
        """After hardware scan + PDF build: show JPEG tiles from temp/."""
        self._preview_mode = "scan"
        self._exam_row = None
        self._exam_local_pdf = ""
        Clock.schedule_once(self._build_scan_jpeg_preview, 0.05)

    def load_exam_for_preview(self, exam: dict):
        """From Documents list: download exam question-paper PDF and rasterize for display."""
        self._preview_mode = "exam"
        self._exam_row = dict(exam)
        self.scanned_pdf_path = ""
        self._exam_local_pdf = ""
        self.page_info = "Loading…"
        self.ids.preview_container.clear_widgets()
        api.run_in_thread(
            self._thread_fetch_exam_as_pngs,
            on_success=self._apply_exam_png_preview,
            on_error=self._exam_preview_failed,
        )

    def _thread_fetch_exam_as_pngs(self):
        exam = dict(self._exam_row)
        exam_id = exam.get("id")
        if not exam_id:
            raise ValueError("Exam has no id")

        pdf_dest = os.path.abspath(os.path.join("temp", "exam_paper_view.pdf"))
        source = f"/api/exams/{exam_id}/pdf"
        api.download_exam_question_pdf(exam_id, pdf_dest)

        with open(pdf_dest, "rb") as fh:
            head = fh.read(5)
        if head != b"%PDF-":
            raise ValueError("Download is not a PDF (wrong endpoint or permissions).")

        render_dir = os.path.abspath(os.path.join("temp", "exam_render"))
        pngs = pdf_to_png_paths(pdf_dest, render_dir)
        if not pngs:
            raise ValueError("PDF has no pages.")
        return {"pngs": pngs, "pdf": pdf_dest, "source_url": source}

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
        tw = max(self.width - dp(16), dp(200))
        container.add_widget(
            Label(
                text=str(exc),
                color=(1, 0.45, 0.45, 1),
                font_size="11sp",
                size_hint_y=None,
                height=dp(120),
                text_size=(tw, None),
                halign="left",
                valign="top",
            )
        )

    def _build_scan_jpeg_preview(self, dt):
        self._preview_mode = "scan"
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

    def _populate_image_paths(self, container, paths):
        n = 0
        for path in paths:
            if not is_valid_jpeg(path):
                continue
            abs_path = os.path.abspath(path)
            img = KivyImage(
                source=abs_path,
                size_hint_y=None,
                height=container.width * 1.41,
                allow_stretch=True,
                keep_ratio=True,
            )
            img.reload()
            container.add_widget(img)
            n += 1
        return n

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
        api.clear_session()
        self._exam_local_pdf = ""
        self._exam_row = None
        self._preview_mode = "none"
        App.get_running_app().navigate("dashboard", direction="right")

    def grade_document(self):
        """Submit scanned PDF to backend for grading, poll, download, print."""
        sel = api.get_selection()
        exam_id = sel.get("exam_id")
        class_id = sel.get("class_id")
        pdf_path = self.scanned_pdf_path

        if class_id and not exam_id:
            print("Redirecting to select exam...")
            App.get_running_app().navigate("documents")
            return

        if not exam_id:
            self.success_message = "Please select an exam first."
            self.show_success = True
            Clock.schedule_once(lambda dt: setattr(self, "show_success", False), 3.0)
            return

        if not class_id:
            self.success_message = "No class selected. Go back and select a class."
            self.show_success = True
            Clock.schedule_once(lambda dt: setattr(self, "show_success", False), 3.0)
            return

        if not pdf_path or not os.path.exists(pdf_path):
            self.success_message = (
                "No student scan PDF. Use Scan to capture pages, then Done."
            )
            self.show_success = True
            Clock.schedule_once(lambda dt: setattr(self, "show_success", False), 3.0)
            return

        self.success_message = "Submitting for grading..."
        self.show_success = True

        api.run_in_thread(
            api.submit_grading_session,
            exam_id,
            class_id,
            pdf_path,
            on_success=self._on_submitted,
            on_error=self._on_grade_error,
        )

    def _on_submitted(self, data):
        batch_id = data.get("batch_id")
        session_id = data.get("session_id")

        self.success_message = "Grading in progress..."

        if batch_id:
            self._poll_batch(batch_id)
        elif session_id:
            self._poll_session(session_id)
        else:
            self._on_grade_error(Exception(f"Unexpected response: {data}"))

    def _poll_batch(self, batch_id, attempt=0):
        """Poll GET /api/batches/{batch_id} every 10s until done."""

        def do_poll():
            try:
                status = api.get_batch_status(batch_id)
                Clock.schedule_once(
                    lambda dt: self._handle_batch_status(status, batch_id), 0
                )
            except Exception as e:
                Clock.schedule_once(
                    lambda dt, err=e: self._on_grade_error(err), 0
                )

        threading.Thread(target=do_poll, daemon=True).start()

    def _handle_batch_status(self, status, batch_id):
        total = status.get("total", 1)
        completed = status.get("completed", 0)
        failed = status.get("failed", 0)
        overall = status.get("status", "")

        self.success_message = f"Grading... {completed}/{total} done"

        if overall == "completed" or (completed + failed) >= total:
            sessions = status.get("sessions", [])
            graded_url = None
            for s in sessions:
                if s.get("status") == "completed" and s.get("graded_url"):
                    graded_url = s["graded_url"]
                    break
            if graded_url:
                self._download_and_print(graded_url)
            else:
                self.success_message = "Grading complete (no PDF returned)."
                Clock.schedule_once(self._finish, 3.0)
        else:
            Clock.schedule_once(lambda dt: self._poll_batch(batch_id), 10.0)

    def _poll_session(self, session_id, attempt=0):
        """Poll GET /api/sessions/{session_id} every 10s until done."""

        def do_poll():
            try:
                status = api.get_session_status(session_id)
                Clock.schedule_once(
                    lambda dt: self._handle_session_status(status, session_id), 0
                )
            except Exception as e:
                Clock.schedule_once(
                    lambda dt, err=e: self._on_grade_error(err), 0
                )

        threading.Thread(target=do_poll, daemon=True).start()

    def _handle_session_status(self, status, session_id):
        state = status.get("status", "")
        self.success_message = f"Grading... ({state})"

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
            Clock.schedule_once(lambda dt: self._poll_session(session_id), 10.0)

    def _download_and_print(self, graded_url):
        self.success_message = "Downloading graded PDF..."
        dest = os.path.abspath(os.path.join("temp", "graded_result.pdf"))

        def do_download():
            try:
                api.download_graded_pdf(graded_url, dest)
                # Clock.schedule_once(lambda dt: self._send_to_printer(dest), 0)
                Clock.schedule_once(lambda dt: self._preview_graded_pdf(dest), 0) # ERASE LATER
            except Exception as e:
                Clock.schedule_once(
                    lambda dt, err=e: self._on_grade_error(err), 0
                )

        threading.Thread(target=do_download, daemon=True).start()

    # ERASE ENTIRE FUNCTION LATER
    def _preview_graded_pdf(self, pdf_path):
        """Temporary test logic to see the result instead of printing"""
        self.success_message = "Rendering Test Preview..."
        self.scanned_pdf_path = pdf_path
        
        render_dir = os.path.abspath(os.path.join("temp", "exam_render"))
        pngs = pdf_to_png_paths(pdf_path, render_dir)
        
        container = self.ids.preview_container
        container.clear_widgets()
        n = self._populate_image_paths(container, pngs)
        
        self.page_info = f"TEST PREVIEW · {n} pg"
        self.show_success = False

    def _send_to_printer(self, pdf_path):
        self.success_message = "Printing..."
        success = self.printer.print_document(pdf_path)
        
        if success:
            self.success_message = "Grading complete! Printed."
        else:
            self.success_message = "Print Error: Check OfficeJet status."
            
        Clock.schedule_once(self._finish, 3.0)

    def _on_grade_error(self, exc):
        self.success_message = f"Error: {exc}"
        self.show_success = True
        Clock.schedule_once(self._finish, 4.0)

    def _finish(self, dt):
        self.show_success = False
        App.get_running_app().navigate("dashboard")

    def print_document(self):
        """Print student scan PDF or, on exam preview, the downloaded exam PDF."""
        pdf_path = self.scanned_pdf_path or self._exam_local_pdf

        if not pdf_path or not os.path.exists(pdf_path):
            print("Print attempted but path is invalid.")
            return
        
        success = self.printer.print_document(pdf_path)
        
        if success:
            self.success_message = "Sent to OfficeJet!"
            self.show_success = True
            Clock.schedule_once(lambda dt: setattr(self, "show_success", False), 3.0)
        else:
            self.success_message = "Hardware Error: Check Printer Connection"
            self.show_success = True