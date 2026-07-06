"""Settings screen — network config (no re-login loop), time/region, logout."""

import logging
import subprocess
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.spinner import Spinner

from wizprinter.accessibility import a11y
import wizprinter.api_client as api

logger = logging.getLogger(__name__)

TIMEZONES = [
    "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "America/Anchorage", "Pacific/Honolulu",
    "America/Sao_Paulo", "America/Mexico_City", "America/Toronto",
    "America/Vancouver", "Europe/London", "Europe/Paris", "Europe/Berlin",
    "Europe/Rome", "Europe/Madrid", "Europe/Istanbul", "Africa/Cairo",
    "Africa/Johannesburg", "Africa/Lagos", "Asia/Dubai", "Asia/Karachi",
    "Asia/Kolkata", "Asia/Dhaka", "Asia/Bangkok", "Asia/Singapore",
    "Asia/Shanghai", "Asia/Tokyo", "Asia/Seoul", "Australia/Sydney",
    "Pacific/Auckland",
]
NTP_SERVERS = [
    "pool.ntp.org", "time.google.com", "time.cloudflare.com", "time.apple.com",
]


def _get_current_timezone() -> str:
    try:
        r = subprocess.run(
            ["timedatectl", "show", "--property=Timezone", "--value"],
            capture_output=True, text=True, timeout=5,
        )
        tz = r.stdout.strip()
        return tz if tz else "UTC"
    except Exception:
        return "UTC"


def _apply_timezone(tz: str) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["sudo", "timedatectl", "set-timezone", tz],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return True, f"Timezone set to {tz}"
        return False, r.stderr.strip() or "Failed to set timezone."
    except FileNotFoundError:
        return False, "timedatectl not found."
    except subprocess.TimeoutExpired:
        return False, "Timed out."
    except Exception as e:
        return False, str(e)


def _sync_ntp(server: str) -> tuple[bool, str]:
    for tool, cmd in [
        ("chronyc",  ["sudo", "chronyc", "makestep"]),
        ("ntpdate",  ["sudo", "ntpdate", "-u", server]),
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if r.returncode == 0:
                return True, f"Time synced via {tool}"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        except Exception as e:
            return False, str(e)
    return False, "Could not sync time. Install chrony or ntp."


def _show_info_popup(title: str, message: str):
    content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
    content.add_widget(Label(
        text=message, text_size=(dp(320), None),
        halign="center", valign="middle", font_size="13sp",
    ))
    btn = Button(text="OK", size_hint=(1, None), height=dp(44))
    content.add_widget(btn)
    popup = Popup(
        title=title, content=content,
        size_hint=(None, None), size=(dp(360), dp(200)),
        auto_dismiss=True,
    )
    btn.bind(on_release=lambda *a: popup.dismiss())
    popup.open()


class SettingsScreen(Screen):
    current_tz = StringProperty("")

    def on_enter(self, *args):
        self.current_tz = _get_current_timezone()
        a11y.speak("Settings screen. Choose Time and Region, Network Config, or Log Out.")

    # ── Time / Region ─────────────────────────────────────────────────────────

    def open_time_region(self):
        a11y.speak("Time and region settings.")
        current = _get_current_timezone()
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        root.add_widget(Label(
            text=f"Current timezone: {current}",
            size_hint_y=None, height=dp(28), font_size="12sp",
            color=(0.7, 0.85, 1, 1),
        ))
        tz_spinner = Spinner(
            text=current if current in TIMEZONES else TIMEZONES[0],
            values=TIMEZONES, size_hint_y=None, height=dp(44), font_size="13sp",
        )
        root.add_widget(tz_spinner)
        root.add_widget(Label(
            text="NTP server:", size_hint_y=None, height=dp(24),
            font_size="12sp", halign="left",
        ))
        ntp_spinner = Spinner(
            text=NTP_SERVERS[0], values=NTP_SERVERS,
            size_hint_y=None, height=dp(40), font_size="13sp",
        )
        root.add_widget(ntp_spinner)
        status_lbl = Label(
            text="", size_hint_y=None, height=dp(28),
            font_size="12sp", color=(0.4, 0.9, 0.5, 1),
        )
        root.add_widget(status_lbl)
        btn_row = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8)
        )
        cancel_btn = Button(text="Cancel", font_size="13sp")
        apply_btn  = Button(text="Apply",  font_size="13sp",
                            background_color=(0.08, 0.5, 0.9, 1))
        btn_row.add_widget(cancel_btn)
        btn_row.add_widget(apply_btn)
        root.add_widget(btn_row)

        popup = Popup(
            title="Time & Region", content=root,
            size_hint=(None, None), size=(dp(420), dp(340)),
            auto_dismiss=False,
        )
        cancel_btn.bind(on_release=lambda *a: popup.dismiss())

        def do_apply(*a):
            chosen_tz  = tz_spinner.text
            chosen_ntp = ntp_spinner.text
            status_lbl.text  = "Applying…"
            status_lbl.color = (1, 0.9, 0.4, 1)
            apply_btn.disabled = True

            def bg():
                ok_tz,  msg_tz  = _apply_timezone(chosen_tz)
                ok_ntp, msg_ntp = _sync_ntp(chosen_ntp)
                Clock.schedule_once(
                    lambda dt: _on_done(ok_tz, msg_tz, ok_ntp, msg_ntp), 0
                )

            def _on_done(ok_tz, msg_tz, ok_ntp, msg_ntp):
                apply_btn.disabled = False
                if ok_tz and ok_ntp:
                    status_lbl.text  = "✓ Applied"
                    status_lbl.color = (0.3, 1, 0.5, 1)
                    self.current_tz  = chosen_tz
                    a11y.speak(f"Time zone set to {chosen_tz}.")
                    Clock.schedule_once(lambda dt: popup.dismiss(), 1.2)
                else:
                    msgs = []
                    if not ok_tz:  msgs.append(f"TZ: {msg_tz}")
                    if not ok_ntp: msgs.append(f"NTP: {msg_ntp}")
                    status_lbl.text  = "\n".join(msgs)
                    status_lbl.color = (1, 0.4, 0.4, 1)
                    a11y.speak("Error applying settings. " + " ".join(msgs))

            threading.Thread(target=bg, daemon=True).start()

        apply_btn.bind(on_release=do_apply)
        popup.open()

    # ── Network ───────────────────────────────────────────────────────────────

    def open_network_config(self):
        """
        Go to WiFi screen.  Post-connect navigation in wifi.py decides whether
        to return here or to dashboard — no re-login forced.
        """
        a11y.speak("Opening network configuration.")
        App.get_running_app().navigate("wifi")

    # ── Logout ────────────────────────────────────────────────────────────────

    def logout(self):
        a11y.speak("Logging out.")
        api.clear_session()
        app = App.get_running_app()
        # Clear the nav stack so go_back() from landing doesn't loop
        app._nav_stack.clear()
        app.navigate("landing", push_history=False)

    def go_back(self):
        App.get_running_app().go_back()
