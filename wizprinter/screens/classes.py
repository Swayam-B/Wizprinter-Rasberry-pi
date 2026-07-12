"""
Class-selection screen.

Three dependent dropdowns — Semester → Subject → Class — each populated from the
backend as the previous one is chosen (see api_client.get_semesters/subjects/
classes). The chosen ids are stashed in api_client's selection state and consumed
downstream by the Documents/Preview grading flow. `navigation_mode` decides
whether "select" continues to the scan flow or the documents (exam) list.
"""

import logging

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import ListProperty, StringProperty

import wizprinter.api_client as api

logger = logging.getLogger(__name__)


class ClassesScreen(Screen):
    semesters = ListProperty([])
    subjects = ListProperty([])
    classes = ListProperty([])

    selected_semester = StringProperty("")
    selected_subject = StringProperty("")
    selected_class = StringProperty("")

    navigation_mode = StringProperty("grading")

    # Internal maps: display name -> UUID
    _semester_ids = {}
    _subject_ids = {}
    _class_ids = {}

    def on_enter(self):
        self.selected_semester = ""
        self.selected_subject = ""
        self.selected_class = ""

        self.semesters = ["Loading..."]
        self.subjects = []
        self.classes = []
        api.run_in_thread(
            api.get_semesters,
            on_success=self._on_semesters,
            on_error=lambda e: self._set_error("semesters", e),
        )

    def _set_error(self, which, exc):
        logger.warning("%s load failed: %s", which, exc)
        if which == "semesters":
            self.semesters = ["Error — tap back and retry"]
        elif which == "subjects":
            self.subjects = ["Error — tap back and retry"]
        else:
            self.classes = ["Error — tap back and retry"]

    def _on_semesters(self, data):
        self._semester_ids = {s["name"]: s["id"] for s in data}
        self.semesters = (
            list(self._semester_ids.keys()) if data else ["No semesters found"]
        )

    def on_selected_semester(self, instance, value):
        sid = self._semester_ids.get(value)
        if not sid:
            return
        api.set_selection(semester_id=sid)
        self.subjects = ["Loading..."]
        self.classes = []
        api.run_in_thread(
            api.get_subjects,
            sid,
            on_success=self._on_subjects,
            on_error=lambda e: self._set_error("subjects", e),
        )

    def _on_subjects(self, data):
        self._subject_ids = {s["name"]: s["id"] for s in data}
        self.subjects = (
            list(self._subject_ids.keys()) if data else ["No subjects found"]
        )

    def on_selected_subject(self, instance, value):
        sid = self._subject_ids.get(value)
        if not sid:
            return
        api.set_selection(subject_id=sid)
        self.classes = ["Loading..."]
        api.run_in_thread(
            api.get_classes,
            sid,
            on_success=self._on_classes,
            on_error=lambda e: self._set_error("classes", e),
        )

    def _on_classes(self, data):
        self._class_ids = {c["name"]: c["id"] for c in data}
        self.classes = list(self._class_ids.keys()) if data else ["No classes found"]

    def on_selected_class(self, instance, value):
        cid = self._class_ids.get(value)
        if cid:
            api.set_selection(class_id=cid)

    def select_class(self):
        sel = api.get_selection()
        if not all([sel["semester_id"], sel["subject_id"], sel["class_id"]]):
            logger.info("Class selection incomplete; ignoring continue tap.")
            return

        app = App.get_running_app()
        
        if self.navigation_mode == "scan_flow":
            app.navigate("scan")
        else:
            app.navigate("documents")

    def go_back(self):
        App.get_running_app().navigate("dashboard", direction="right")
