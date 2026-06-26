"""WiFi network selection screen — real nmcli scan, password prompt, actual connect."""

import subprocess
import threading
import re

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import ListProperty, StringProperty, BooleanProperty
from kivy.clock import Clock


# ── helpers ───────────────────────────────────────────────────────────────────

def _scan_networks() -> list[dict]:
    """
    Run `nmcli -t -f SSID,SIGNAL,SECURITY device wifi list` and return a list
    of dicts: {name, signal_strength (0-100), secured (bool), signal (str label)}.

    Falls back to an empty list if nmcli is unavailable or returns no output.
    """
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list",
             "--rescan", "yes"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        networks = []
        seen = set()
        for line in result.stdout.splitlines():
            # Format: SSID:SIGNAL:SECURITY  (fields may contain escaped colons)
            parts = line.split(":")
            if len(parts) < 3:
                continue
            ssid = parts[0].strip()
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            try:
                strength = int(parts[1].strip())
            except ValueError:
                strength = 0
            security = ":".join(parts[2:]).strip()
            secured = bool(security and security.upper() != "--")
            if strength >= 67:
                label = "strong"
            elif strength >= 34:
                label = "medium"
            else:
                label = "weak"
            networks.append({
                "name": ssid,
                "signal": label,
                "signal_strength": strength,
                "secured": secured,
            })
        # Sort by signal strength descending
        networks.sort(key=lambda n: n["signal_strength"], reverse=True)
        return networks
    except FileNotFoundError:
        # nmcli not installed (dev machine) — return empty list
        return []
    except subprocess.TimeoutExpired:
        return []
    except Exception as e:
        print(f"[WiFi] Scan error: {e}")
        return []


def _connect_network(ssid: str, password: str | None) -> tuple[bool, str]:
    """
    Connect to *ssid* using nmcli.  Returns (success, message).
    If password is None or empty, attempts an open connection.
    """
    try:
        if password:
            cmd = ["nmcli", "device", "wifi", "connect", ssid, "password", password]
        else:
            cmd = ["nmcli", "device", "wifi", "connect", ssid]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return True, f"Connected to {ssid}"
        else:
            err = result.stderr.strip() or result.stdout.strip()
            return False, err or "Connection failed."
    except FileNotFoundError:
        return False, "nmcli not found. Install NetworkManager."
    except subprocess.TimeoutExpired:
        return False, "Connection timed out."
    except Exception as e:
        return False, str(e)


# ── Screen ────────────────────────────────────────────────────────────────────

class WifiScreen(Screen):
    """WiFi network selection with real scan, password prompt, and nmcli connect."""

    networks = ListProperty([])
    scan_status = StringProperty("Scanning for networks…")
    is_scanning = BooleanProperty(False)
    is_connecting = BooleanProperty(False)
    connect_status = StringProperty("")

    # Password prompt state
    show_password_prompt = BooleanProperty(False)
    prompt_ssid = StringProperty("")
    password_visible = BooleanProperty(False)

    # Internal
    _pending_ssid: str = ""
    _pending_secured: bool = False

    def on_enter(self, *args):
        self._start_scan()

    def _start_scan(self):
        if self.is_scanning:
            return
        self.is_scanning = True
        self.scan_status = "Scanning for networks…"
        self.networks = []
        threading.Thread(target=self._bg_scan, daemon=True).start()

    def _bg_scan(self):
        found = _scan_networks()
        Clock.schedule_once(lambda dt: self._on_scan_done(found), 0)

    def _on_scan_done(self, found: list):
        self.is_scanning = False
        self.networks = found
        if found:
            self.scan_status = f"Found {len(found)} network{'s' if len(found) != 1 else ''}"
        else:
            self.scan_status = "No networks found. Tap Refresh to retry."

    def refresh(self):
        self.connect_status = ""
        self._start_scan()

    def select_network(self, network: dict):
        """Called when the user taps a network row."""
        if self.is_connecting:
            return
        ssid = network.get("name", "")
        secured = network.get("secured", False)

        if secured:
            # Show the password entry popup
            self._pending_ssid = ssid
            self._pending_secured = True
            self.prompt_ssid = ssid
            self.password_visible = False
            self.show_password_prompt = True
        else:
            # Open network — connect immediately
            self._do_connect(ssid, None)

    def confirm_password(self, password: str):
        """Called when the user submits the password prompt."""
        self.show_password_prompt = False
        self._do_connect(self._pending_ssid, password.strip() or None)

    def cancel_password(self):
        self.show_password_prompt = False
        self._pending_ssid = ""

    def toggle_password_visible(self):
        self.password_visible = not self.password_visible

    def _do_connect(self, ssid: str, password: str | None):
        self.is_connecting = True
        self.connect_status = f"Connecting to {ssid}…"
        threading.Thread(
            target=self._bg_connect,
            args=(ssid, password),
            daemon=True,
        ).start()

    def _bg_connect(self, ssid: str, password: str | None):
        success, msg = _connect_network(ssid, password)
        Clock.schedule_once(lambda dt: self._on_connect_done(success, msg, ssid), 0)

    def _on_connect_done(self, success: bool, msg: str, ssid: str):
        self.is_connecting = False
        if success:
            self.connect_status = f"✓ Connected to {ssid}"
            # Navigate forward after a short pause so the user sees confirmation
            Clock.schedule_once(lambda dt: App.get_running_app().navigate("login"), 1.2)
        else:
            # Strip any credential info from error messages before displaying
            safe_msg = re.sub(r"(?i)(password|psk|key)\s*[:=]\s*\S+", "[redacted]", msg)
            self.connect_status = f"✗ {safe_msg}"

    def go_back(self):
        App.get_running_app().navigate("landing", direction="right")

    def on_networks(self, instance, networks):
        """Populate the dynamic network row container whenever the list changes."""
        if "network_rows" not in self.ids:
            return
        container = self.ids.network_rows
        container.clear_widgets()
        for net in networks:
            self._add_network_row(container, net)

    def _add_network_row(self, container, net: dict):
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.label import Label
        from kivy.uix.button import Button
        from kivy.graphics import Color, Rectangle, Line
        from kivy.metrics import dp

        row = Button(
            size_hint_y=None,
            height=dp(48),
            background_color=(0, 0, 0, 0),
        )

        # Background via canvas
        with row.canvas.before:
            Color(0.098, 0.149, 0.200, 1)
            rect = Rectangle(pos=row.pos, size=row.size)
        row.bind(pos=lambda w, v: setattr(rect, "pos", v))
        row.bind(size=lambda w, v: setattr(rect, "size", v))

        inner = BoxLayout(orientation="horizontal", padding=[dp(12), 0], spacing=dp(8))
        inner.size = row.size
        inner.pos = row.pos
        row.bind(size=lambda w, v: setattr(inner, "size", v))
        row.bind(pos=lambda w, v: setattr(inner, "pos", v))

        # Signal strength icon
        signal_icons = {"strong": "▮▮▮", "medium": "▮▮░", "weak": "▮░░"}
        signal_colors = {"strong": (0.18, 0.8, 0.44, 1),
                         "medium": (0.98, 0.74, 0.13, 1),
                         "weak":   (0.9,  0.3,  0.2,  1)}
        sig = net.get("signal", "weak")
        signal_lbl = Label(
            text=signal_icons.get(sig, "░░░"),
            font_size="11sp",
            size_hint_x=None,
            width=dp(36),
            color=signal_colors.get(sig, (1, 1, 1, 1)),
            halign="center",
        )
        inner.add_widget(signal_lbl)

        # SSID
        name_lbl = Label(
            text=net.get("name", ""),
            font_size="14sp",
            color=(0.88, 0.89, 0.93, 1),
            halign="left",
            valign="middle",
        )
        name_lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
        inner.add_widget(name_lbl)

        # Lock icon for secured networks
        lock_lbl = Label(
            text="🔒" if net.get("secured") else "",
            font_size="13sp",
            size_hint_x=None,
            width=dp(24),
            color=(0.573, 0.678, 0.788, 1),
        )
        inner.add_widget(lock_lbl)

        row.add_widget(inner)
        net_copy = dict(net)
        row.bind(on_release=lambda btn, n=net_copy: self.select_network(n))
        container.add_widget(row)
