"""Settings screen — network config (no re-login loop), time/region, logout."""

import logging
import os
import subprocess
import threading
import time

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

from kivy.uix.textinput import TextInput

from wizprinter.accessibility import a11y
import wizprinter.admin_pin as admin_pin
import wizprinter.api_client as api

logger = logging.getLogger(__name__)


class _SafeSpinner(Spinner):
    """
    Spinner that won't crash the app if it's tapped while detached from the
    window.

    Kivy raises "Cannot open a dropdown list on a hidden widget" if the dropdown
    is opened when the spinner has no root window — which happens when the host
    popup has been dismissed (or the app is shutting down) with a touch still in
    flight. We simply skip opening in that case instead of letting it crash the
    kiosk.
    """

    def _toggle_dropdown(self, *args):
        if self.get_root_window() is None:
            return
        return super()._toggle_dropdown(*args)


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
DEFAULT_NTP_SERVER = "pool.ntp.org"


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
            # timedatectl updates /etc/localtime, but this long-running process
            # cached the timezone at startup — so datetime.now() (the dashboard
            # clock) would keep showing the OLD zone. Re-point the process's TZ
            # and re-read it so the change is visible immediately.
            os.environ["TZ"] = tz
            if hasattr(time, "tzset"):
                time.tzset()
            return True, f"Timezone set to {tz}"
        return False, r.stderr.strip() or "Failed to set timezone."
    except FileNotFoundError:
        return False, "timedatectl not found."
    except subprocess.TimeoutExpired:
        return False, "Timed out."
    except Exception as e:
        return False, str(e)


def _sync_ntp(server: str) -> tuple[bool, str]:
    """
    Best-effort network time sync.

    Preferred path is `timedatectl set-ntp true`, which enables the built-in
    systemd-timesyncd on Raspberry Pi OS (Bookworm) with nothing extra to
    install — this is what replaces the old "install chrony or ntp" failure.
    chrony/ntpdate remain as one-shot fallbacks for images that ship them.
    """
    # 1) systemd-timesyncd via timedatectl (default on Bookworm — no extra pkg)
    try:
        r = subprocess.run(
            ["sudo", "timedatectl", "set-ntp", "true"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return True, "Network time sync enabled (systemd-timesyncd)"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception as e:
        return False, str(e)

    # 2) One-shot step via chrony or ntpdate, if present
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
    return False, "Could not enable network time sync."


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
        tz_spinner = _SafeSpinner(
            text=current if current in TIMEZONES else TIMEZONES[0],
            values=TIMEZONES, size_hint_y=None, height=dp(44), font_size="13sp",
        )
        root.add_widget(tz_spinner)
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
            size_hint=(None, None), size=(dp(420), dp(280)),
            auto_dismiss=False,
        )
        cancel_btn.bind(on_release=lambda *a: popup.dismiss())

        def do_apply(*a):
            chosen_tz  = tz_spinner.text
            status_lbl.text  = "Applying…"
            status_lbl.color = (1, 0.9, 0.4, 1)
            apply_btn.disabled = True

            def bg():
                ok_tz,  msg_tz  = _apply_timezone(chosen_tz)
                ok_ntp, msg_ntp = _sync_ntp(DEFAULT_NTP_SERVER)
                Clock.schedule_once(
                    lambda dt: _on_done(ok_tz, msg_tz, ok_ntp, msg_ntp), 0
                )

            def _on_done(ok_tz, msg_tz, ok_ntp, msg_ntp):
                apply_btn.disabled = False
                # Timezone is the primary action; network time sync is a best-
                # effort extra and must not fail the whole operation.
                if ok_tz:
                    self.current_tz = chosen_tz
                    if ok_ntp:
                        status_lbl.text = "✓ Applied"
                    else:
                        status_lbl.text = "✓ Timezone set (time sync unavailable)"
                    status_lbl.color = (0.3, 1, 0.5, 1)
                    a11y.speak(f"Time zone set to {chosen_tz}.")
                    Clock.schedule_once(lambda dt: popup.dismiss(), 1.2)
                else:
                    status_lbl.text  = f"TZ: {msg_tz}"
                    status_lbl.color = (1, 0.4, 0.4, 1)
                    a11y.speak("Error setting time zone. " + msg_tz)

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

    # ── Remote support (fleet-ops MVP) ────────────────────────────────────────

    def request_help(self):
        a11y.speak("Requesting remote support.")

        def bg():
            sent = api.request_remote_support(
                reason="Teacher requested help from Settings screen.",
                context={"screen": "settings"},
            )
            Clock.schedule_once(lambda dt: self._on_help_requested(sent), 0)

        threading.Thread(target=bg, daemon=True).start()

    def _on_help_requested(self, sent: bool):
        if sent:
            a11y.speak("Support has been notified.")
            _show_info_popup("Help Requested", "Support has been notified and will follow up.")
        else:
            a11y.speak("Could not reach support. Check your network connection.")
            _show_info_popup(
                "Could Not Reach Support",
                "No connection to the support system right now.\n"
                "Please check the network or contact support directly.",
            )

    # ── Accessibility ─────────────────────────────────────────────────────────

    def open_accessibility(self):
        a11y.speak("Accessibility settings.")
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))

        tts_btn = Button(
            text=f"Text-to-Speech: {'ON' if a11y.tts_enabled() else 'OFF'}",
            size_hint_y=None, height=dp(44), font_size="13sp",
        )
        root.add_widget(tts_btn)

        close_btn = Button(text="Close", size_hint_y=None, height=dp(44), font_size="13sp")
        root.add_widget(close_btn)

        popup = Popup(
            title="Accessibility", content=root,
            size_hint=(None, None), size=(dp(380), dp(160)),
            auto_dismiss=False,
        )

        def toggle_tts(*a):
            new_state = not a11y.tts_enabled()
            a11y.set_tts_enabled(new_state)
            tts_btn.text = f"Text-to-Speech: {'ON' if new_state else 'OFF'}"
            a11y.speak("Text to speech enabled." if new_state else "")

        tts_btn.bind(on_release=toggle_tts)
        close_btn.bind(on_release=lambda *a: popup.dismiss())
        popup.open()

    # ── Logout ────────────────────────────────────────────────────────────────

    def logout(self):
        if admin_pin.is_enabled():
            self._prompt_admin_pin(self._do_logout)
        else:
            self._do_logout()

    def _prompt_admin_pin(self, on_success):
        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        content.add_widget(Label(
            text="Enter admin PIN to log out.",
            font_size="13sp", size_hint_y=None, height=dp(24),
        ))
        pin_input = TextInput(
            password=True, multiline=False, font_size="15sp",
            size_hint_y=None, height=dp(44),
        )
        content.add_widget(pin_input)
        error_lbl = Label(text="", font_size="11sp", color=(1, 0.4, 0.4, 1),
                          size_hint_y=None, height=dp(20))
        content.add_widget(error_lbl)

        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8))
        cancel_btn = Button(text="Cancel", font_size="13sp")
        submit_btn = Button(text="Submit", font_size="13sp",
                            background_color=(0.08, 0.5, 0.9, 1))
        btn_row.add_widget(cancel_btn)
        btn_row.add_widget(submit_btn)
        content.add_widget(btn_row)

        popup = Popup(title="Admin PIN Required", content=content,
                      size_hint=(None, None), size=(dp(340), dp(220)), auto_dismiss=False)

        def submit(*a):
            if admin_pin.check(pin_input.text):
                popup.dismiss()
                on_success()
            else:
                error_lbl.text = "Incorrect PIN."
                pin_input.text = ""

        cancel_btn.bind(on_release=lambda *a: popup.dismiss())
        submit_btn.bind(on_release=submit)
        popup.open()

    def _do_logout(self):
        a11y.speak("Logging out.")
        api.clear_session()
        app = App.get_running_app()
        # Clear the nav stack so go_back() from landing doesn't loop
        app._nav_stack.clear()
        app.navigate("landing", push_history=False)

    def go_back(self):
        App.get_running_app().go_back()
