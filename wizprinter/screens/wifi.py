"""
WiFi screen — real nmcli scan, password prompt, actual connect.

Navigation note
───────────────
Connecting to a new router does NOT force a re-login.  If the user already
has a valid session token, they are sent directly to the dashboard.
If this is the first-time setup flow, they are sent to login.
"""

import logging
import re
import subprocess
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.properties import BooleanProperty, ListProperty, StringProperty
from kivy.uix.screenmanager import Screen

from wizprinter.accessibility import a11y
from wizprinter.session import session_mgr

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _scan_networks() -> list[dict]:
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY",
             "device", "wifi", "list", "--rescan", "yes"],
            capture_output=True, text=True, timeout=15,
        )
        networks, seen = [], set()
        for line in result.stdout.splitlines():
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
            secured  = bool(security and security.upper() != "--")
            if strength >= 67:   label = "strong"
            elif strength >= 34: label = "medium"
            else:                label = "weak"
            networks.append({"name": ssid, "signal": label,
                             "signal_strength": strength, "secured": secured})
        networks.sort(key=lambda n: n["signal_strength"], reverse=True)
        return networks
    except FileNotFoundError:
        return []
    except subprocess.TimeoutExpired:
        logger.warning("nmcli scan timed out")
        return []
    except Exception as e:
        logger.error("WiFi scan error: %s", e)
        return []


def _connect_network(ssid: str, password: str | None) -> tuple[bool, str]:
    try:
        cmd = ["nmcli", "device", "wifi", "connect", ssid]
        if password:
            cmd += ["password", password]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return True, f"Connected to {ssid}"
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
    networks            = ListProperty([])
    scan_status         = StringProperty("Scanning for networks…")
    is_scanning         = BooleanProperty(False)
    is_connecting       = BooleanProperty(False)
    connect_status      = StringProperty("")
    show_password_prompt = BooleanProperty(False)
    prompt_ssid         = StringProperty("")
    password_visible    = BooleanProperty(False)

    _pending_ssid:    str  = ""
    _pending_secured: bool = False

    def on_enter(self, *args):
        a11y.speak("Wi-Fi setup. Select a network from the list.")
        self._start_scan()

    def _start_scan(self):
        if self.is_scanning:
            return
        self.is_scanning   = True
        self.scan_status   = "Scanning for networks…"
        self.networks      = []
        threading.Thread(target=self._bg_scan, daemon=True).start()

    def _bg_scan(self):
        found = _scan_networks()
        Clock.schedule_once(lambda dt: self._on_scan_done(found), 0)

    def _on_scan_done(self, found: list):
        self.is_scanning = False
        self.networks    = found
        if found:
            n = len(found)
            self.scan_status = f"Found {n} network{'s' if n != 1 else ''}"
            a11y.speak(f"Found {n} network{'s' if n != 1 else ''}. Tap one to connect.")
        else:
            self.scan_status = "No networks found. Tap Refresh to retry."
            a11y.speak("No networks found. Tap Refresh to scan again.")

    def refresh(self):
        self.connect_status = ""
        a11y.speak("Scanning for networks.")
        self._start_scan()

    def select_network(self, network: dict):
        if self.is_connecting:
            return
        ssid    = network.get("name", "")
        secured = network.get("secured", False)
        a11y.speak(f"Selected {ssid}. {'Secured network, password required.' if secured else 'Open network, connecting.'}")
        if secured:
            self._pending_ssid    = ssid
            self._pending_secured = True
            self.prompt_ssid      = ssid
            self.password_visible = False
            self.show_password_prompt = True
        else:
            self._do_connect(ssid, None)

    def confirm_password(self, password: str):
        self.show_password_prompt = False
        self._do_connect(self._pending_ssid, password.strip() or None)

    def cancel_password(self):
        self.show_password_prompt = False
        self._pending_ssid        = ""
        a11y.speak("Password entry cancelled.")

    def toggle_password_visible(self):
        self.password_visible = not self.password_visible
        a11y.speak("Password " + ("shown." if self.password_visible else "hidden."))

    def _do_connect(self, ssid: str, password: str | None):
        self.is_connecting  = True
        self.connect_status = f"Connecting to {ssid}…"
        a11y.speak(f"Connecting to {ssid}, please wait.")
        threading.Thread(
            target=self._bg_connect, args=(ssid, password), daemon=True
        ).start()

    def _bg_connect(self, ssid: str, password: str | None):
        success, msg = _connect_network(ssid, password)
        Clock.schedule_once(
            lambda dt: self._on_connect_done(success, msg, ssid), 0
        )

    def _on_connect_done(self, success: bool, msg: str, ssid: str):
        self.is_connecting = False
        if success:
            self.connect_status = f"✓ Connected to {ssid}"
            a11y.speak(f"Connected to {ssid} successfully.")
            # ── Smart post-connect navigation ────────────────────────────────
            # If already authenticated, go straight to dashboard.
            # Only send to login on first-time / expired session.
            if session_mgr.is_valid:
                Clock.schedule_once(
                    lambda dt: App.get_running_app().navigate(
                        "dashboard", push_history=False), 1.2
                )
            else:
                Clock.schedule_once(
                    lambda dt: App.get_running_app().navigate(
                        "login", push_history=False), 1.2
                )
        else:
            safe_msg = re.sub(
                r"(?i)(password|psk|key)\s*[:=]\s*\S+", "[redacted]", msg
            )
            self.connect_status = f"✗ {safe_msg}"
            a11y.speak(f"Connection failed. {safe_msg}")

    def on_networks(self, instance, networks):
        if "network_rows" not in self.ids:
            return
        container = self.ids.network_rows
        container.clear_widgets()
        for net in networks:
            self._add_network_row(container, net)

    def _add_network_row(self, container, net: dict):
        from kivy.graphics import Color, Rectangle
        from kivy.metrics import dp
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label

        row = Button(size_hint_y=None, height=dp(52), background_color=(0, 0, 0, 0))
        with row.canvas.before:
            Color(0.098, 0.149, 0.200, 1)
            rect = Rectangle(pos=row.pos, size=row.size)
        row.bind(pos=lambda w, v: setattr(rect, "pos", v))
        row.bind(size=lambda w, v: setattr(rect, "size", v))

        inner = BoxLayout(orientation="horizontal", padding=[dp(12), 0], spacing=dp(8))
        inner.size = row.size
        inner.pos  = row.pos
        row.bind(size=lambda w, v: setattr(inner, "size", v))
        row.bind(pos=lambda w, v: setattr(inner, "pos", v))

        sig    = net.get("signal", "weak")
        icons  = {"strong": "▮▮▮", "medium": "▮▮░", "weak": "▮░░"}
        colors = {
            "strong": (0.18, 0.8, 0.44, 1),
            "medium": (0.98, 0.74, 0.13, 1),
            "weak":   (0.9,  0.3,  0.2,  1),
        }
        inner.add_widget(Label(
            text=icons.get(sig, "░░░"), font_size="11sp",
            size_hint_x=None, width=dp(36),
            color=colors.get(sig, (1, 1, 1, 1)), halign="center",
        ))
        name_lbl = Label(
            text=net.get("name", ""), font_size="15sp",
            color=(0.92, 0.93, 0.97, 1), halign="left", valign="middle",
        )
        name_lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
        inner.add_widget(name_lbl)
        inner.add_widget(Label(
            text="🔒" if net.get("secured") else "",
            font_size="13sp", size_hint_x=None, width=dp(24),
            color=(0.573, 0.678, 0.788, 1),
        ))

        row.add_widget(inner)
        net_copy = dict(net)
        row.bind(on_release=lambda btn, n=net_copy: self.select_network(n))
        container.add_widget(row)

    def go_back(self):
        App.get_running_app().go_back()
