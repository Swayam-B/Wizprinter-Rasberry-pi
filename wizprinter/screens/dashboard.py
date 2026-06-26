"""Main dashboard — live clock, live printer status checks."""

import threading
from datetime import datetime

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.clock import Clock
from kivy.properties import StringProperty, BooleanProperty

# Printer status refresh interval (seconds)
PRINTER_STATUS_INTERVAL = 30


def _live_printer_status(printer_name: str) -> tuple[bool, str]:
    """
    Query CUPS for the real-time state of *printer_name*.
    Returns (is_ready: bool, display_label: str).
    """
    try:
        import cups
        conn = cups.Connection()
        printers = conn.getPrinters()
        if printer_name not in printers:
            return False, f"{printer_name} (not found)"
        attrs = printers[printer_name]
        state = attrs.get("printer-state", 0)
        if state == 3:
            return True, printer_name
        elif state == 4:
            return False, f"{printer_name} (printing)"
        elif state == 5:
            msg = attrs.get("printer-state-message", "stopped")
            return False, f"{printer_name} ({msg})"
        else:
            return False, f"{printer_name} (unknown)"
    except Exception as e:
        return False, f"{printer_name} (error)"


class DashboardScreen(Screen):
    """Home dashboard with Grade, Scan, and Settings navigation."""

    current_time = StringProperty("12:00 PM")
    printer_connected = BooleanProperty(False)
    connected_printer_name = StringProperty("")

    def on_enter(self):
        self._update_time()
        self._clock_event = Clock.schedule_interval(
            lambda dt: self._update_time(), 30
        )
        # Kick off a live status check if a printer is already selected
        if self.connected_printer_name:
            self._refresh_printer_status()
        self._status_event = Clock.schedule_interval(
            lambda dt: self._refresh_printer_status(), PRINTER_STATUS_INTERVAL
        )

    def on_leave(self):
        if hasattr(self, "_clock_event"):
            self._clock_event.cancel()
        if hasattr(self, "_status_event"):
            self._status_event.cancel()

    def _update_time(self):
        self.current_time = datetime.now().strftime("%I:%M %p")

    # ── Printer status ─────────────────────────────────────────────────────────

    def set_printer(self, printer_name: str):
        """Called by PrinterListScreen when the user selects a printer."""
        self.connected_printer_name = printer_name
        self.printer_connected = bool(printer_name)
        if printer_name:
            self._refresh_printer_status()

    def _refresh_printer_status(self):
        """Run a background CUPS probe to update the live printer status."""
        name = self.connected_printer_name
        if not name:
            return
        threading.Thread(
            target=self._probe_printer_bg,
            args=(name,),
            daemon=True,
        ).start()

    def _probe_printer_bg(self, name: str):
        ready, label = _live_printer_status(name)
        Clock.schedule_once(
            lambda dt: self._apply_printer_status(ready, label), 0
        )

    def _apply_printer_status(self, ready: bool, label: str):
        self.printer_connected = ready
        self.connected_printer_name = label

    # ── Navigation ─────────────────────────────────────────────────────────────

    def nav_scan(self):
        app = App.get_running_app()
        app._printer_list_origin = "scan"
        app.navigate("printer_list")

    def nav_classes(self):
        app = App.get_running_app()
        app._printer_list_origin = "grade"
        app.navigate("printer_list")

    def nav_settings(self):
        App.get_running_app().navigate("settings")
