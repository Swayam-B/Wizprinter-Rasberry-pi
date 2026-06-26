"""Printer discovery and selection screen — with no-device state and recovery."""

import threading

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import ListProperty, StringProperty, ColorProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.metrics import dp

_C = {
    "background":        (0.063, 0.098, 0.133, 1),
    "surface_low":       (0.098, 0.149, 0.200, 1),
    "primary":           (0.075, 0.498, 0.925, 1),
    "primary_container": (0.137, 0.267, 0.388, 1),
    "success":           (0.180, 0.800, 0.443, 1),
    "warning":           (0.98,  0.74,  0.13,  1),
    "on_surface":        (0.88,  0.89,  0.93,  1),
    "outline":           (0.196, 0.302, 0.404, 1),
    "text_muted":        (0.573, 0.678, 0.788, 1),
}

# How many times to auto-retry a failed job before surfacing an error popup
PRINT_JOB_MAX_RETRIES = 3
PRINT_JOB_RETRY_INTERVAL = 5.0   # seconds between retries


def _show_error_popup(title: str, message: str, on_retry=None, on_dismiss=None):
    content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
    content.add_widget(Label(
        text=message,
        text_size=(dp(340), None),
        halign="center",
        valign="middle",
        font_size="13sp",
        color=(1, 0.9, 0.9, 1),
    ))
    btn_row = BoxLayout(orientation="horizontal", size_hint_y=None,
                        height=dp(44), spacing=dp(8))
    dismiss_btn = Button(text="OK", font_size="13sp")
    btn_row.add_widget(dismiss_btn)
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
    dismiss_btn.bind(on_release=lambda *a: (popup.dismiss(),
                                            on_dismiss() if on_dismiss else None))
    if on_retry:
        retry_btn.bind(on_release=lambda *a: (popup.dismiss(), on_retry()))
    popup.open()
    return popup


class PrinterCard(BoxLayout):
    printer_name  = StringProperty("")
    status        = StringProperty("")
    subtext       = StringProperty("")
    status_color  = ColorProperty((1, 1, 1, 1))
    is_ready      = BooleanProperty(False)
    origin        = StringProperty("scan")


class PrinterListScreen(Screen):
    available_printers  = ListProperty([])
    scan_status         = StringProperty("SCANNING FOR LOCAL DEVICES...")
    origin              = StringProperty("scan")
    no_device_visible   = BooleanProperty(False)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def on_enter(self):
        self.origin = getattr(App.get_running_app(), "_printer_list_origin", "scan")
        self._start_discovery()

    def _start_discovery(self):
        self.scan_status = "SCANNING FOR LOCAL DEVICES..."
        self.available_printers = []
        self.no_device_visible = False
        self._update_ui()
        threading.Thread(target=self._discover_printers, daemon=True).start()

    # ── Discovery ──────────────────────────────────────────────────────────────

    def _discover_printers(self):
        found = []
        try:
            import cups
            conn = cups.Connection()
            printers = conn.getPrinters()
            for name, attrs in printers.items():
                uri   = attrs.get("device-uri", "")
                state = attrs.get("printer-state", 0)

                if not self._is_reachable(uri, attrs):
                    print(f"[PrinterList] Skipping unreachable printer: {name} ({uri})")
                    continue

                state_msg = attrs.get("printer-state-message", "")
                jobs      = self._get_job_count(conn, name)

                is_ready = (state == 3)
                if is_ready:
                    status  = "READY"
                    subtext = self._connection_label(uri)
                    color   = _C["success"]
                elif state == 4:
                    status  = "PRINTING"
                    subtext = f"{jobs} job{'s' if jobs != 1 else ''} in queue"
                    color   = _C["warning"]
                elif state == 5:
                    status  = "STOPPED"
                    subtext = state_msg or "Check printer"
                    color   = (0.9, 0.3, 0.2, 1)
                else:
                    status  = "UNKNOWN"
                    subtext = self._connection_label(uri)
                    color   = _C["text_muted"]

                found.append({
                    "name":    name,
                    "status":  status,
                    "subtext": subtext,
                    "ready":   is_ready,
                    "color":   color,
                })
        except Exception as e:
            print(f"[PrinterList] CUPS discovery error: {e}")

        Clock.schedule_once(lambda dt: self._on_discovery_done(found), 0)

    @staticmethod
    def _is_reachable(uri, attrs):
        import socket as _socket
        import re as _re

        def tcp_ok(host, port, timeout=2.0):
            try:
                s = _socket.create_connection((host, port), timeout=timeout)
                s.close()
                return True
            except OSError:
                return False

        def extract_ip_from_hp_uri(u):
            m = _re.search(r"[?&]ip=([^&]+)", u)
            if m:
                return m.group(1).strip()
            m = _re.search(r"[?&]zc=([^&]+)", u)
            if m:
                return m.group(1).strip()
            return None

        try:
            if uri.startswith(("ipp://", "ipps://")):
                without_scheme = uri.split("://", 1)[1]
                host_part = without_scheme.split("/")[0]
                host, port = (host_part.rsplit(":", 1) if ":" in host_part
                              else (host_part, "631"))
                return tcp_ok(host, int(port))
            elif uri.startswith("socket://"):
                without_scheme = uri.split("://", 1)[1]
                host_part = without_scheme.split("/")[0]
                host = host_part.rsplit(":", 1)[0] if ":" in host_part else host_part
                port_str = host_part.rsplit(":", 1)[1] if ":" in host_part else "9100"
                return tcp_ok(host, int(port_str))
            elif uri.startswith("lpd://"):
                host = uri.split("://", 1)[1].split("/")[0].split(":")[0]
                return tcp_ok(host, 515)
            elif uri.startswith("http://"):
                host = uri.split("://", 1)[1].split("/")[0].split(":")[0]
                return tcp_ok(host, 80)
            elif uri.startswith("https://"):
                host = uri.split("://", 1)[1].split("/")[0].split(":")[0]
                return tcp_ok(host, 443)
            elif uri.startswith(("hp:/net/", "hpfax:/net/", "hp:/usb/", "hpfax:/usb/")):
                if "/net/" in uri:
                    ip = extract_ip_from_hp_uri(uri)
                    return tcp_ok(ip, 9100) if ip else False
                else:
                    return attrs.get("printer-state", 0) != 5
            elif uri.startswith("usb://"):
                return attrs.get("printer-state", 0) != 5
            else:
                print(f"[PrinterList] Unknown URI scheme, excluding: {uri}")
                return False
        except Exception as e:
            print(f"[PrinterList] Reachability probe error for {uri}: {e}")
            return False

    @staticmethod
    def _connection_label(uri):
        if uri.startswith(("ipp://", "ipps://", "hp:/net/", "hpfax:/net/")):
            return "Wi-Fi"
        if uri.startswith(("socket://", "lpd://", "http://", "https://")):
            return "Network"
        if uri.startswith(("usb://", "hp:/usb/", "hpfax:/usb/")):
            return "USB"
        return "Connected"

    def _get_job_count(self, conn, printer_name):
        try:
            jobs = conn.getJobs(which_jobs="not-completed", my_jobs=False)
            return sum(1 for j in jobs.values()
                       if j.get("printer-uri", "").endswith(printer_name))
        except Exception:
            return 0

    def _on_discovery_done(self, found):
        self.available_printers = found
        if found:
            self.scan_status = f"FOUND {len(found)} DEVICE{'S' if len(found) != 1 else ''}"
            self.no_device_visible = False
        else:
            self.scan_status = "NO DEVICES FOUND"
            self.no_device_visible = True
        self._update_ui()

    # ── UI helpers ─────────────────────────────────────────────────────────────

    def _update_ui(self):
        if "printer_container" not in self.ids:
            return
        container = self.ids.printer_container
        container.clear_widgets()
        for p in self.available_printers:
            card = PrinterCard(
                printer_name = p["name"],
                status       = p["status"],
                subtext      = p["subtext"],
                status_color = p["color"],
                is_ready     = p["ready"],
                origin       = self.origin,
            )
            container.add_widget(card)

    def refresh_printer_list(self):
        self._start_discovery()

    # ── Navigation ─────────────────────────────────────────────────────────────

    def select_printer(self, printer_name):
        app = App.get_running_app()
        dashboard = app.root.get_screen("dashboard")
        dashboard.set_printer(printer_name)
        app.selected_printer = printer_name

        classes_screen = app.root.get_screen("classes")
        if self.origin == "scan":
            classes_screen.navigation_mode = "scan_flow"
        else:
            classes_screen.navigation_mode = "grading"
        app.navigate("classes")

    def go_back(self):
        App.get_running_app().navigate("dashboard", direction="right")

    # ── Print job retry handling ────────────────────────────────────────────────

    def send_with_retry(self, pdf_path: str, printer_name: str,
                        attempt: int = 0, on_done=None):
        """
        Submit a print job to CUPS with automatic retry on transient failures.
        Pops an error popup after PRINT_JOB_MAX_RETRIES failed attempts.
        on_done(success: bool) is called on the Kivy thread when finished.
        """
        def bg():
            try:
                import cups
                conn = cups.Connection()
                options = {"media": "na_letter_8.5x11in", "scaling": "100"}
                job_id = conn.printFile(printer_name, pdf_path,
                                        "WizPrinter_Job", options)
                Clock.schedule_once(
                    lambda dt: self._on_job_sent(job_id, printer_name,
                                                 pdf_path, attempt, on_done), 0
                )
            except Exception as e:
                Clock.schedule_once(
                    lambda dt, err=e: self._on_job_error(
                        err, pdf_path, printer_name, attempt, on_done
                    ), 0
                )

        threading.Thread(target=bg, daemon=True).start()

    def _on_job_sent(self, job_id, printer_name, pdf_path, attempt, on_done):
        print(f"[PrinterList] Job {job_id} queued on {printer_name}")
        if on_done:
            on_done(True)

    def _on_job_error(self, exc, pdf_path, printer_name, attempt, on_done):
        print(f"[PrinterList] Print job attempt {attempt+1} failed: {exc}")
        if attempt < PRINT_JOB_MAX_RETRIES - 1:
            # Schedule a retry
            Clock.schedule_once(
                lambda dt: self.send_with_retry(
                    pdf_path, printer_name, attempt + 1, on_done
                ),
                PRINT_JOB_RETRY_INTERVAL,
            )
        else:
            # All retries exhausted — show error popup with option to retry manually
            def manual_retry():
                self.send_with_retry(pdf_path, printer_name, 0, on_done)

            _show_error_popup(
                "Print Failed",
                f"Could not print after {PRINT_JOB_MAX_RETRIES} attempts.\n{exc}",
                on_retry=manual_retry,
                on_dismiss=lambda: on_done(False) if on_done else None,
            )
