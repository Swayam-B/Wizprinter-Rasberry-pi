"""Document (Exam) list screen."""

from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import StringProperty

import wizprinter.api_client as api


class DocumentsScreen(Screen):
    status_text = StringProperty("")

    # Map display name -> exam dict (keeps id for navigation)
    _exam_map = {}

    def on_enter(self):
        sel = api.get_selection()
        subject_id = sel.get("subject_id")
        if not subject_id:
            self.status_text = "No subject selected."
            return
        self.status_text = "Loading exams..."
        self._clear_list()
        api.run_in_thread(
            api.get_exams,
            subject_id,
            on_success=self._on_exams,
            on_error=self._on_error,
        )

    def _clear_list(self):
        if "doc_list" in self.ids:
            self.ids.doc_list.clear_widgets()

    def _on_exams(self, data):
        self.status_text = ""
        self._exam_map = {}
        container = self.ids.doc_list
        container.clear_widgets()

        if not data:
            container.add_widget(
                Label(
                    text="No exams found for this subject.",
                    color=(1, 1, 1, 0.5),
                    size_hint_y=None,
                    height=dp(40),
                )
            )
            return

        for exam in data:
            self._exam_map[exam["name"]] = exam
            date_str = exam.get("created_at", "")[:10]
            badge = f"  [{exam.get('status', '').upper()}]" if exam.get("status") else ""
            btn = Button(
                text=f"{exam['name']}{badge}\n{date_str}",
                size_hint_y=None,
                height=dp(50),
                halign="left",
                text_size=(None, None),
                font_size="13sp",
            )
            name = exam["name"]
            btn.bind(on_release=lambda b, n=name: self.select_document(n))
            container.add_widget(btn)

    def _on_error(self, exc):
        self.status_text = f"Error: {exc}"

    def select_document(self, exam_name):
        exam = self._exam_map.get(exam_name)
        if not exam:
            return
        
        api.set_selection(exam_id=exam["id"])
        
        app = App.get_running_app()
        preview_screen = self.manager.get_screen("preview")

        if preview_screen.scanned_pdf_path:
            preview_screen.show_scan_jpeg_previews()
            app.navigate("preview")
        else:
            preview_screen.load_exam_for_preview(exam)
            app.navigate("preview")

    def go_back(self):
        App.get_running_app().navigate("classes", direction="right")
