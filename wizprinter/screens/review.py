"""
Post-grading review screen.

Flow: PreviewScreen submits a grading job and, once GradingStatusMixin
reports completion, hands the graded sessions off to this screen via
load_review(). The teacher reviews each student card (tile), corrects/
overrides low-confidence responses, and approves students individually or in
bulk via the auto-grouping panel — before anything is finalized (printed
and/or sent).

Data-shape dependency
----------------------
See wizprinter.grading module docstring: per-student / per-response fields
(`responses`, `confidence`, `student_name`) are not yet a documented backend
contract. This screen degrades gracefully when they're absent — a session
with no `responses` list simply shows no confidence flags and is treated as
Pending rather than Flagged.
"""
from __future__ import annotations

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import (
    BooleanProperty, ColorProperty, DictProperty, ListProperty, StringProperty,
)
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.textinput import TextInput

from wizprinter.accessibility import a11y
from wizprinter.grading import (
    GROUP_ORDER, GradeOutputMode, ReviewState, flagged_response_count,
    group_sessions, response_needs_review, session_key, session_needs_review,
)
from wizprinter.screens.grading_status import GradingStatusMixin

_STATUS_COLOR = {
    ReviewState.APPROVED: (0.180, 0.800, 0.443, 1),
    ReviewState.FLAGGED:  (0.98, 0.74, 0.13, 1),
    ReviewState.PENDING:  (0.573, 0.678, 0.788, 1),
}
_STATUS_LABEL = {
    ReviewState.APPROVED: "APPROVED",
    ReviewState.FLAGGED:  "NEEDS REVIEW",
    ReviewState.PENDING:  "PENDING",
}


# ── Student card widget ───────────────────────────────────────────────────────

class StudentCard(ButtonBehavior, BoxLayout):
    student_name = StringProperty("")
    status_label = StringProperty("")
    status_color = ColorProperty((1, 1, 1, 1))
    flag_summary = StringProperty("")
    is_selected  = BooleanProperty(False)
    session_key  = StringProperty("")


# ── Screen ────────────────────────────────────────────────────────────────────

class ReviewScreen(GradingStatusMixin, Screen):
    sessions        = ListProperty([])
    approvals       = DictProperty({})   # session_key -> ReviewState.value (str)
    selected        = ListProperty([])   # session_keys currently multi-selected
    summary_text    = StringProperty("")
    show_success    = BooleanProperty(False)
    success_message = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._grading_status_init()
        self._output_mode = GradeOutputMode.PRINT_AND_SEND
        self._exam_id  = ""
        self._class_id = ""
        self._print_queue: list[str] = []

    # ── Load ──────────────────────────────────────────────────────────────────

    def load_review(self, sessions: list, output_mode: GradeOutputMode,
                     exam: dict | None, exam_id: str, class_id: str):
        self._output_mode = output_mode
        self._exam_id  = exam_id
        self._class_id = class_id
        self.sessions  = list(sessions)
        self.selected  = []
        self.approvals = {
            session_key(s): (
                ReviewState.FLAGGED.value if session_needs_review(s)
                else ReviewState.PENDING.value
            )
            for s in self.sessions
        }
        self._rebuild()

    def on_enter(self, *args):
        flagged = sum(1 for v in self.approvals.values() if v == ReviewState.FLAGGED.value)
        total = len(self.sessions)
        a11y.speak(
            f"Review screen. {total} student{'s' if total != 1 else ''} graded, "
            f"{flagged} flagged for review."
        )

    # ── Card grid + grouping panel ────────────────────────────────────────────

    def _rebuild(self):
        total    = len(self.sessions)
        approved = sum(1 for v in self.approvals.values() if v == ReviewState.APPROVED.value)
        self.summary_text = f"{approved}/{total} students approved"

        if "card_grid" not in self.ids:
            return
        grid = self.ids.card_grid
        grid.clear_widgets()
        for s in self.sessions:
            key   = session_key(s)
            state = ReviewState(self.approvals.get(key, ReviewState.PENDING.value))
            card = StudentCard(
                student_name = s.get("student_name") or key or "Unknown",
                status_label = _STATUS_LABEL[state],
                status_color = _STATUS_COLOR[state],
                flag_summary = self._flag_summary(s),
                is_selected  = key in self.selected,
                session_key  = key,
            )
            card.bind(on_release=lambda inst, k=key: self.open_student_detail(k))
            grid.add_widget(card)

        self._rebuild_group_chips()

    @staticmethod
    def _flag_summary(session: dict) -> str:
        n = flagged_response_count(session)
        if session.get("status") == "failed":
            return "Grading failed"
        if n:
            return f"{n} low-confidence response{'s' if n != 1 else ''}"
        return "All responses confident"

    def _rebuild_group_chips(self):
        if "group_chip_row" not in self.ids:
            return
        row = self.ids.group_chip_row
        row.clear_widgets()
        groups = group_sessions(self.sessions)
        for name in GROUP_ORDER:
            members = groups[name]
            if not members:
                continue
            chip = Button(
                text=f"{name} ({len(members)})",
                size_hint_x=None, width=dp(160), font_size="11sp", bold=True,
            )
            chip.bind(on_release=lambda inst, m=members: self.select_group(m))
            row.add_widget(chip)

    # ── Selection ──────────────────────────────────────────────────────────────

    def select_group(self, members: list):
        keys = [session_key(s) for s in members]
        self.selected = keys
        a11y.speak(f"{len(keys)} student{'s' if len(keys) != 1 else ''} selected.")
        self._rebuild()

    def select_all(self):
        self.selected = [session_key(s) for s in self.sessions]
        self._rebuild()

    def clear_selection(self):
        self.selected = []
        self._rebuild()

    def approve_selected(self):
        if not self.selected:
            return
        approvals = dict(self.approvals)
        for key in self.selected:
            approvals[key] = ReviewState.APPROVED.value
        self.approvals = approvals
        a11y.speak(f"{len(self.selected)} student{'s' if len(self.selected) != 1 else ''} approved.")
        self._rebuild()

    # ── Per-student detail: review, correction, override, approval ──────────

    def open_student_detail(self, key: str):
        session = next((s for s in self.sessions if session_key(s) == key), None)
        if session is None:
            return

        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        name = session.get("student_name") or key
        root.add_widget(Label(
            text=name, font_size="16sp", bold=True, color=(1, 1, 1, 1),
            size_hint_y=None, height=dp(26),
        ))

        responses = session.get("responses", [])
        overrides: dict[int, TextInput] = {}

        if not responses:
            root.add_widget(Label(
                text="No per-response detail available for this student.",
                font_size="12sp", color=(0.573, 0.678, 0.788, 1),
                size_hint_y=None, height=dp(40),
            ))
        else:
            for i, resp in enumerate(responses):
                flagged = response_needs_review(resp)
                row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(70),
                                 spacing=dp(2))
                conf = resp.get("confidence")
                conf_txt = f"confidence {conf:.0%}" if isinstance(conf, (int, float)) else "confidence n/a"
                header = Label(
                    text=f"Q{i + 1}: {resp.get('question', '')}  [{conf_txt}]",
                    font_size="11sp", bold=flagged,
                    color=(1, 0.75, 0.3, 1) if flagged else (0.85, 0.9, 0.95, 1),
                    size_hint_y=None, height=dp(20),
                    text_size=(dp(360), None), halign="left",
                )
                row.add_widget(header)
                override_input = TextInput(
                    text=resp.get("override") or resp.get("answer", ""),
                    multiline=False, font_size="12sp", size_hint_y=None, height=dp(36),
                )
                overrides[i] = override_input
                row.add_widget(override_input)
                root.add_widget(row)

        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8))
        cancel_btn  = Button(text="Close")
        approve_btn = Button(text="Approve", background_color=(0.18, 0.8, 0.44, 1))
        btn_row.add_widget(cancel_btn)
        btn_row.add_widget(approve_btn)
        root.add_widget(btn_row)

        popup = Popup(title="Review Student", content=root,
                       size_hint=(None, None), size=(dp(420), dp(min(480, 140 + 80 * max(1, len(responses))))),
                       auto_dismiss=False)

        def do_approve(*a):
            for i, inp in overrides.items():
                new_text = inp.text.strip()
                if new_text and new_text != responses[i].get("answer", ""):
                    responses[i]["override"] = new_text
            approvals = dict(self.approvals)
            approvals[key] = ReviewState.APPROVED.value
            self.approvals = approvals
            a11y.speak(f"{name} approved.")
            popup.dismiss()
            self._rebuild()

        cancel_btn.bind(on_release=lambda *a: popup.dismiss())
        approve_btn.bind(on_release=do_approve)
        popup.open()

    # ── Finalize ──────────────────────────────────────────────────────────────

    def finalize(self):
        unresolved = [
            s for s in self.sessions
            if self.approvals.get(session_key(s)) != ReviewState.APPROVED.value
        ]
        if unresolved:
            self._show_unresolved_popup(unresolved)
            return
        self._do_finalize()

    def _show_unresolved_popup(self, unresolved: list):
        names = ", ".join((s.get("student_name") or session_key(s)) for s in unresolved[:5])
        if len(unresolved) > 5:
            names += f", and {len(unresolved) - 5} more"

        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        content.add_widget(Label(
            text=f"{len(unresolved)} student(s) still need review:\n{names}",
            font_size="12sp", halign="center", valign="middle",
            text_size=(dp(340), None), color=(1, 0.9, 0.6, 1),
        ))
        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8))
        back_btn        = Button(text="Back to Review")
        approve_all_btn = Button(text="Approve All & Send", background_color=(0.9, 0.5, 0.1, 1))
        btn_row.add_widget(back_btn)
        btn_row.add_widget(approve_all_btn)
        content.add_widget(btn_row)

        popup = Popup(title="Students Still Need Review", content=content,
                       size_hint=(None, None), size=(dp(400), dp(200)), auto_dismiss=True)

        def approve_all_and_send(*a):
            popup.dismiss()
            approvals = dict(self.approvals)
            for s in unresolved:
                approvals[session_key(s)] = ReviewState.APPROVED.value
            self.approvals = approvals
            a11y.speak("All remaining students approved by override.")
            self._do_finalize()

        back_btn.bind(on_release=lambda *a: popup.dismiss())
        approve_all_btn.bind(on_release=approve_all_and_send)
        popup.open()

    def _do_finalize(self):
        self.show_success = True
        self.success_message = "Finalizing…"

        if self._output_mode == GradeOutputMode.PRINT_AND_SEND:
            self._print_queue = [
                s.get("graded_url") for s in self.sessions if s.get("graded_url")
            ]
            self._print_next()
        else:
            # SEND_ONLY: the grading submission already delivered results to
            # WizPrinter; skip the local print queue entirely.
            self._finalize_done()

    def _print_next(self):
        if not self._print_queue:
            self._finalize_done()
            return
        url = self._print_queue.pop(0)
        self.download_and_print(url, on_done=lambda job_id: self._print_next(),
                                 on_error=self._on_print_queue_error)

    def _on_print_queue_error(self, exc):
        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        content.add_widget(Label(
            text=f"A print job failed:\n{exc}",
            font_size="12sp", halign="center", text_size=(dp(340), None),
            color=(1, 0.7, 0.7, 1),
        ))
        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8))
        skip_btn  = Button(text="Skip Remaining")
        retry_btn = Button(text="Retry", background_color=(0.08, 0.5, 0.9, 1))
        btn_row.add_widget(skip_btn)
        btn_row.add_widget(retry_btn)
        content.add_widget(btn_row)
        popup = Popup(title="Print Failed", content=content,
                       size_hint=(None, None), size=(dp(400), dp(200)), auto_dismiss=False)

        def skip(*a):
            popup.dismiss()
            self._print_queue = []
            self._finalize_done()

        def retry(*a):
            popup.dismiss()
            self._print_next()

        skip_btn.bind(on_release=skip)
        retry_btn.bind(on_release=retry)
        popup.open()

    def _finalize_done(self):
        self.show_success = False
        app = App.get_running_app()
        dashboard = app.root.get_screen("dashboard")
        # Dashboard sync happens regardless of which output mode was chosen.
        dashboard.sync_after_grading()
        a11y.speak("Grading finalized.")
        app.navigate("dashboard", push_history=False)

    def _on_grading_failed(self, exc, *, timed_out: bool):
        # GradingStatusMixin requires this hook; ReviewScreen only reuses the
        # mixin's download/print helpers, not its polling, so failures here
        # are surfaced through the print-queue error popup instead.
        self._on_print_queue_error(exc)

    def _on_grading_complete(self, sessions):
        pass  # not used on this screen; polling is owned by PreviewScreen

    # ── Navigation ─────────────────────────────────────────────────────────────

    def go_back(self):
        unresolved = any(
            self.approvals.get(session_key(s)) != ReviewState.APPROVED.value
            for s in self.sessions
        )
        if not unresolved:
            App.get_running_app().navigate("dashboard", direction="right")
            return

        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        content.add_widget(Label(
            text="Some students haven't been approved yet.\nLeave anyway? Results will not be sent.",
            font_size="12sp", halign="center", text_size=(dp(320), None),
        ))
        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8))
        stay_btn  = Button(text="Stay")
        leave_btn = Button(text="Leave Without Sending", background_color=(0.9, 0.3, 0.2, 1))
        btn_row.add_widget(stay_btn)
        btn_row.add_widget(leave_btn)
        content.add_widget(btn_row)
        popup = Popup(title="Unfinished Review", content=content,
                       size_hint=(None, None), size=(dp(380), dp(190)), auto_dismiss=True)
        stay_btn.bind(on_release=lambda *a: popup.dismiss())
        leave_btn.bind(on_release=lambda *a: (popup.dismiss(),
                       App.get_running_app().navigate("dashboard", direction="right")))
        popup.open()
