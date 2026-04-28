"""Printer discovery and selection screen."""

import threading
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import ListProperty, StringProperty, ColorProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.clock import Clock

# ─── Color palette (matches theme.kv) ──────────────────────
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


class PrinterCard(BoxLayout):
    """Reusable row widget for a discovered printer."""
    printer_name  = StringProperty("")
    status        = StringProperty("")
    subtext       = StringProperty("")
    status_color  = ColorProperty((1, 1, 1, 1))
    is_ready      = BooleanProperty(False)
    # Which flow triggered this screen: 'scan' or 'grade'
    origin        = StringProperty("scan")


class PrinterListScreen(Screen):
    """Discover USB/Wi-Fi printers and let the user pick one before continuing."""

    available_printers = ListProperty([])
    scan_status        = StringProperty("SCANNING FOR LOCAL DEVICES...")
    # Stores which dashboard button brought us here: 'scan' or 'grade'
    origin             = StringProperty("scan")

    # ── Lifecycle ──────────────────────────────────────────

    def on_enter(self):
        self.origin = getattr(App.get_running_app(), '_printer_list_origin', 'scan')
        self.scan_status = "SCANNING FOR LOCAL DEVICES..."
        self.available_printers = []
        self._update_ui()
        # Run discovery in a background thread so the UI stays responsive
        threading.Thread(target=self._discover_printers, daemon=True).start()

    # ── Discovery ──────────────────────────────────────────

    def _discover_printers(self):
        """Find printers via CUPS (covers both USB and Wi-Fi/network)."""
        found = []
        try:
            import cups
            conn = cups.Connection()
            printers = conn.getPrinters()
            for name, attrs in printers.items():
                state      = attrs.get('printer-state', 0)
                state_msg  = attrs.get('printer-state-message', '')
                uri        = attrs.get('device-uri', '')
                jobs       = self._get_job_count(conn, name)

                is_ready = (state == 3)          # 3 = idle/ready in IPP
                if is_ready:
                    status  = "READY"
                    subtext = self._friendly_uri(uri)
                    color   = _C['success']
                elif state == 4:                 # 4 = processing
                    status  = "PRINTING"
                    subtext = f"{jobs} job{'s' if jobs != 1 else ''} in queue"
                    color   = _C['warning']
                elif state == 5:                 # 5 = stopped
                    status  = "STOPPED"
                    subtext = state_msg or "Check printer"
                    color   = (0.9, 0.3, 0.2, 1)
                else:
                    status  = "UNKNOWN"
                    subtext = uri
                    color   = _C['text_muted']

                found.append({
                    "name":    name,
                    "status":  status,
                    "subtext": subtext,
                    "ready":   is_ready,
                    "color":   color,
                })
        except Exception as e:
            print(f"[PrinterList] CUPS discovery error: {e}")

        # Schedule UI update back on the main thread
        Clock.schedule_once(lambda dt: self._on_discovery_done(found), 0)

    def _get_job_count(self, conn, printer_name):
        try:
            jobs = conn.getJobs(which_jobs='not-completed', my_jobs=False)
            return sum(1 for j in jobs.values()
                       if j.get('printer-uri', '').endswith(printer_name))
        except Exception:
            return 0

    @staticmethod
    def _friendly_uri(uri):
        """Turn a device URI into a human-readable string."""
        if uri.startswith('ipp://') or uri.startswith('ipps://'):
            # ipp://192.168.1.x/... → IP: 192.168.1.x
            host = uri.split('/')[2].split(':')[0]
            return f"IP: {host}"
        if uri.startswith('usb://'):
            return "USB connected"
        if uri.startswith('socket://'):
            host = uri.split('/')[2].split(':')[0]
            return f"Network: {host}"
        return uri

    def _on_discovery_done(self, found):
        self.available_printers = found
        if found:
            self.scan_status = f"FOUND {len(found)} DEVICE{'S' if len(found) != 1 else ''}"
        else:
            self.scan_status = "NO DEVICES FOUND"
        self._update_ui()

    # ── UI helpers ─────────────────────────────────────────

    def _update_ui(self):
        if 'printer_container' not in self.ids:
            return
        container = self.ids.printer_container
        container.clear_widgets()
        for p in self.available_printers:
            card = PrinterCard(
                printer_name = p['name'],
                status       = p['status'],
                subtext      = p['subtext'],
                status_color = p['color'],
                is_ready     = p['ready'],
                origin       = self.origin,
            )
            container.add_widget(card)

    def refresh_printer_list(self):
        self.scan_status = "SCANNING FOR LOCAL DEVICES..."
        self.available_printers = []
        self._update_ui()
        threading.Thread(target=self._discover_printers, daemon=True).start()

    # ── Navigation ─────────────────────────────────────────

    def select_printer(self, printer_name):
        """Connect to the chosen printer and continue the intended flow."""
        app = App.get_running_app()

        # Tell the dashboard a printer is now connected
        dashboard = app.root.get_screen('dashboard')
        dashboard.set_printer(printer_name)

        # Also store it on the app for any screen that needs it
        app.selected_printer = printer_name

        # Continue to the screen that triggered us
        if self.origin == 'scan':
            app.navigate('scan')
        else:
            # 'grade' flow → classes → documents → preview
            app.navigate('classes')

    def go_back(self):
        App.get_running_app().navigate('dashboard', direction='right')