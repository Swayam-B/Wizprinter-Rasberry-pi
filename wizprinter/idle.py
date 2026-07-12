"""
Kiosk inactivity watchdog.

On a shared self-service kiosk, a walk-away must not leave a teacher's session
open. This monitor watches for touch activity on the Kivy Window and enforces:

  * While signed in — after IDLE_WARNING_SEC of no touch, a modal warning pops up
    counting down LOGOUT_COUNTDOWN_SEC seconds. Any touch anywhere dismisses it
    and resets the timer. If the countdown reaches zero the session is cleared
    (auto-logout) and the kiosk returns to the landing screen. Default timings
    give the user 60s + 30s = 90s of grace before a forced logout.

  * While signed out — the watchdog does nothing. The pre-login screens
    (landing, login, Wi-Fi) are never interrupted by a warning, countdown, or
    forced navigation, since there is no session to protect.

A screen actively showing its grading/print overlay (`show_success` True) counts
as activity, so a long backend job running without touches is never interrupted.
Timings are overridable via environment variables for tuning and testing.
"""
from __future__ import annotations

import logging
import math
import os
import time

from kivy.clock import Clock
from kivy.core.window import Window

logger = logging.getLogger(__name__)

# Seconds of inactivity before the logout warning appears.
IDLE_WARNING_SEC:      float = float(os.environ.get("KIOSK_IDLE_WARNING_SEC", "60"))
# Length of the warning countdown before the session is cleared.
LOGOUT_COUNTDOWN_SEC:  float = float(os.environ.get("KIOSK_LOGOUT_COUNTDOWN_SEC", "30"))
# How often the watchdog re-evaluates (also drives the 1s countdown display).
_CHECK_INTERVAL_SEC = 1.0


class IdleMonitor:
    """Watches Window touches and enforces the idle → warning → logout policy."""

    def __init__(self, app):
        self._app = app
        self._last_activity = time.monotonic()
        self._check_ev = None
        self._warning = None   # {"popup": Popup, "label": Label} while showing

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        Window.bind(on_touch_down=self._on_touch)
        self._check_ev = Clock.schedule_interval(self._check, _CHECK_INTERVAL_SEC)
        logger.info(
            "Idle monitor started (warn after %.0fs idle, then %.0fs countdown to logout)",
            IDLE_WARNING_SEC, LOGOUT_COUNTDOWN_SEC,
        )

    def stop(self) -> None:
        if self._check_ev is not None:
            self._check_ev.cancel()
            self._check_ev = None
        self._cancel_warning()
        Window.unbind(on_touch_down=self._on_touch)

    def notify_activity(self) -> None:
        """Manually mark activity (e.g. from a non-touch input source)."""
        self._last_activity = time.monotonic()

    # ── Touch handling ────────────────────────────────────────────────────────

    def _on_touch(self, window, touch):
        # While the logout warning is showing, a tap on the "Log out" button
        # logs the user out; a tap anywhere else means "stay" (the whole point
        # of "touch anywhere to stay"). Otherwise any touch is just activity.
        if self._warning is not None:
            logout_btn = self._warning.get("logout_btn")
            if logout_btn is not None and self._touch_in_widget(logout_btn, touch):
                self._logout()
                return True   # consume — we handled it
            self._last_activity = time.monotonic()
            self._cancel_warning()
            return False
        self._last_activity = time.monotonic()
        return False   # never consume — just observe

    # ── Watchdog tick ─────────────────────────────────────────────────────────

    def _check(self, dt):
        name, screen = self._current_screen()
        if name is None:
            return

        # An in-progress grading/print job (overlay visible) counts as activity
        # so we never yank the user away mid-operation.
        if getattr(screen, "show_success", False):
            self._last_activity = time.monotonic()
            if self._warning is not None:
                self._cancel_warning()
            return

        idle = time.monotonic() - self._last_activity

        from wizprinter.session import session_mgr
        if not session_mgr.is_valid:
            # Signed out: nothing to protect. The pre-login screens (landing,
            # login, Wi-Fi) must NOT be interrupted by the idle warning/logout.
            if self._warning is not None:
                self._cancel_warning()
            return

        # Signed in: warn, then log out if the countdown expires.
        total = IDLE_WARNING_SEC + LOGOUT_COUNTDOWN_SEC
        if idle < IDLE_WARNING_SEC:
            if self._warning is not None:
                self._cancel_warning()
            return

        if self._warning is None:
            self._show_warning()

        remaining = total - idle
        if remaining <= 0:
            self._logout()
        else:
            self._update_warning(int(math.ceil(remaining)))

    # ── Warning popup ─────────────────────────────────────────────────────────

    def _show_warning(self) -> None:
        from kivy.metrics import dp
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup

        content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        msg = Label(
            text="", font_size="15sp", halign="center", valign="middle",
            text_size=(dp(380), None), color=(1, 1, 1, 1),
        )
        content.add_widget(msg)

        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None,
                            height=dp(48), spacing=dp(10))
        logout_btn = Button(
            text="Log out", font_size="14sp", background_color=(0.9, 0.3, 0.2, 1),
        )
        stay_btn = Button(
            text="I'm still here", font_size="14sp",
            background_color=(0.08, 0.5, 0.9, 1),
        )
        btn_row.add_widget(logout_btn)
        btn_row.add_widget(stay_btn)
        content.add_widget(btn_row)

        # Primary handling is in _on_touch (so "touch anywhere" stays, and a tap
        # on Log Out logs out regardless of TTS two-tap). These bindings are a
        # harmless fallback.
        stay_btn.bind(on_release=lambda *a: self._reset_and_cancel())
        logout_btn.bind(on_release=lambda *a: self._logout())

        popup = Popup(
            title="Are you still there?", content=content,
            size_hint=(None, None), size=(dp(440), dp(240)),
            auto_dismiss=False,
        )
        self._warning = {"popup": popup, "label": msg, "logout_btn": logout_btn}
        popup.open()

        try:
            from wizprinter.accessibility import a11y
            a11y.speak(
                "You will be logged out soon due to inactivity. "
                "Touch the screen to stay signed in."
            )
        except Exception:
            pass

    def _update_warning(self, seconds: int) -> None:
        if self._warning is None:
            return
        seconds = max(0, seconds)
        self._warning["label"].text = (
            f"Logging out in {seconds} second{'s' if seconds != 1 else ''}…\n"
            "Touch anywhere to stay signed in."
        )

    def _reset_and_cancel(self) -> None:
        self._last_activity = time.monotonic()
        self._cancel_warning()

    def _cancel_warning(self) -> None:
        if self._warning is not None:
            try:
                self._warning["popup"].dismiss()
            except Exception:
                pass
            self._warning = None

    # ── Actions ───────────────────────────────────────────────────────────────

    def _logout(self) -> None:
        logger.info("Inactivity timeout expired → clearing session (auto-logout)")
        self._cancel_warning()
        import wizprinter.api_client as api
        api.clear_session()
        self._to_landing()

    def _to_landing(self) -> None:
        self._app._nav_stack.clear()
        self._app.navigate("landing", push_history=False)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _current_screen(self):
        root = getattr(self._app, "root", None)
        if root is None:
            return None, None
        name = root.current
        try:
            return name, root.get_screen(name)
        except Exception:
            return name, None

    @staticmethod
    def _touch_in_widget(widget, touch) -> bool:
        """True if a window-space touch falls within *widget* (no scaling)."""
        try:
            wx, wy = widget.to_window(widget.x, widget.y)
        except Exception:
            return False
        return (wx <= touch.x <= wx + widget.width and
                wy <= touch.y <= wy + widget.height)
