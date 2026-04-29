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
        """Find printers via CUPS, then probe each one to confirm it is
        physically reachable before showing it in the list."""
        found = []
        try:
            import cups
            conn = cups.Connection()
            printers = conn.getPrinters()
            for name, attrs in printers.items():
                uri   = attrs.get('device-uri', '')
                state = attrs.get('printer-state', 0)

                # ── Reachability probe ──────────────────────────────
                # Skip any printer we cannot actually reach right now.
                if not self._is_reachable(uri, attrs):
                    print(f"[PrinterList] Skipping unreachable printer: {name} ({uri})")
                    continue

                state_msg = attrs.get('printer-state-message', '')
                jobs      = self._get_job_count(conn, name)

                is_ready = (state == 3)          # IPP: 3 = idle/ready
                if is_ready:
                    status  = "READY"
                    subtext = self._connection_label(uri)
                    color   = _C['success']
                elif state == 4:                 # IPP: 4 = processing
                    status  = "PRINTING"
                    subtext = f"{jobs} job{'s' if jobs != 1 else ''} in queue"
                    color   = _C['warning']
                elif state == 5:                 # IPP: 5 = stopped/error
                    status  = "STOPPED"
                    subtext = state_msg or "Check printer"
                    color   = (0.9, 0.3, 0.2, 1)
                else:
                    status  = "UNKNOWN"
                    subtext = self._connection_label(uri)
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

        Clock.schedule_once(lambda dt: self._on_discovery_done(found), 0)

    @staticmethod
    def _is_reachable(uri, attrs):
        """Return True only if we can confirm the printer is physically reachable.

        Probe strategy per URI scheme:
          ipp / ipps        → TCP port 631 (or URI port)
          socket            → TCP port 9100
          lpd               → TCP port 515
          http / https      → TCP port 80 / 443
          hp:/net / hpfax   → TCP port 9100 on embedded IP from query string
          usb://            → CUPS state must not be stopped (5)
          anything else     → conservatively DENY (unknown = untestable = skip)
        """
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
            """hp:/net/Model?ip=x.x.x.x  or  hp:/net/Model?zc=hostname"""
            m = _re.search(r'[?&]ip=([^&]+)', u)
            if m:
                return m.group(1).strip()
            m = _re.search(r'[?&]zc=([^&]+)', u)
            if m:
                return m.group(1).strip()
            return None

        try:
            if uri.startswith(('ipp://', 'ipps://')):
                without_scheme = uri.split('://', 1)[1]
                host_part = without_scheme.split('/')[0]
                if ':' in host_part:
                    host, port_str = host_part.rsplit(':', 1)
                    port = int(port_str)
                else:
                    host = host_part
                    port = 631
                return tcp_ok(host, port)

            elif uri.startswith('socket://'):
                without_scheme = uri.split('://', 1)[1]
                host_part = without_scheme.split('/')[0]
                host = host_part.rsplit(':', 1)[0] if ':' in host_part else host_part
                port_str = host_part.rsplit(':', 1)[1] if ':' in host_part else '9100'
                return tcp_ok(host, int(port_str))

            elif uri.startswith('lpd://'):
                host = uri.split('://', 1)[1].split('/')[0].split(':')[0]
                return tcp_ok(host, 515)

            elif uri.startswith('http://'):
                host = uri.split('://', 1)[1].split('/')[0].split(':')[0]
                return tcp_ok(host, 80)

            elif uri.startswith('https://'):
                host = uri.split('://', 1)[1].split('/')[0].split(':')[0]
                return tcp_ok(host, 443)

            elif uri.startswith(('hp:/net/', 'hpfax:/net/', 'hp:/usb/', 'hpfax:/usb/')):
                if '/net/' in uri:
                    # Network HPLIP: probe JetDirect port on the embedded IP
                    ip = extract_ip_from_hp_uri(uri)
                    if ip:
                        return tcp_ok(ip, 9100)
                    # No IP in URI — can't probe, deny
                    return False
                else:
                    # USB HPLIP: treat like usb://
                    state = attrs.get('printer-state', 0)
                    return state != 5

            elif uri.startswith('usb://'):
                state = attrs.get('printer-state', 0)
                return state != 5

            else:
                # Unknown scheme — we have no way to probe it, so exclude it
                # to avoid showing stale/phantom printers
                print(f"[PrinterList] Unknown URI scheme, excluding: {uri}")
                return False

        except Exception as e:
            print(f"[PrinterList] Reachability probe error for {uri}: {e}")
            return False

    @staticmethod
    def _connection_label(uri):
        """Return a short, privacy-safe connection label — no IPs, no raw URIs."""
        if uri.startswith(('ipp://', 'ipps://')):
            return "Wi-Fi"
        if uri.startswith(('hp:/net/', 'hpfax:/net/')):
            return "Wi-Fi"
        if uri.startswith('socket://'):
            return "Network"
        if uri.startswith('lpd://'):
            return "Network"
        if uri.startswith(('usb://', 'hp:/usb/', 'hpfax:/usb/')):
            return "USB"
        if uri.startswith(('http://', 'https://')):
            return "Network"
        return "Connected"

    def _get_job_count(self, conn, printer_name):
        try:
            jobs = conn.getJobs(which_jobs='not-completed', my_jobs=False)
            return sum(1 for j in jobs.values()
                       if j.get('printer-uri', '').endswith(printer_name))
        except Exception:
            return 0

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

        # Continue to the screen that triggered us, preserving navigation_mode
        classes_screen = app.root.get_screen('classes')
        if self.origin == 'scan':
            classes_screen.navigation_mode = 'scan_flow'
            app.navigate('classes')
        else:
            # 'grade' flow → classes → documents → preview
            classes_screen.navigation_mode = 'grading'
            app.navigate('classes')

    def go_back(self):
        App.get_running_app().navigate('dashboard', direction='right')