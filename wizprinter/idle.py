"""
Kiosk inactivity watchdog.

On a shared self-service kiosk, a walk-away must not leave a teacher's session
open. This monitor watches for touch activity on the Kivy Window and:

  * after IDLE_TO_LANDING_SEC with no touch, returns to the landing
    ("Tap to start") screen; and
  * if the landing screen then stays untouched for a further
    LANDING_TO_LOGOUT_SEC, clears the session (logs the user out).

Any touch anywhere resets the timer. A screen actively showing its grading/print
overlay (`show_success` True) counts as activity, so a long backend job running
without touches is never interrupted. Both thresholds are overridable via
environment variables for tuning and testing.
"""
from __future__ import annotations

import logging
import os
import time

from kivy.clock import Clock
from kivy.core.window import Window

logger = logging.getLogger(__name__)

IDLE_TO_LANDING_SEC:   float = float(os.environ.get("KIOSK_IDLE_TO_LANDING_SEC", "60"))
LANDING_TO_LOGOUT_SEC: float = float(os.environ.get("KIOSK_LANDING_TO_LOGOUT_SEC", "60"))
_CHECK_INTERVAL_SEC = 2.0


class IdleMonitor:
    """Watches Window touches and enforces the idle → landing → logout policy."""

    def __init__(self, app):
        self._app = app
        self._last_activity = time.monotonic()
        self._check_ev = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        Window.bind(on_touch_down=self._on_touch)
        self._check_ev = Clock.schedule_interval(self._check, _CHECK_INTERVAL_SEC)
        logger.info(
            "Idle monitor started (landing after %.0fs idle, logout after a further %.0fs)",
            IDLE_TO_LANDING_SEC, LANDING_TO_LOGOUT_SEC,
        )

    def stop(self) -> None:
        if self._check_ev is not None:
            self._check_ev.cancel()
            self._check_ev = None
        Window.unbind(on_touch_down=self._on_touch)

    def notify_activity(self) -> None:
        """Manually mark activity (e.g. from a non-touch input source)."""
        self._last_activity = time.monotonic()

    # ── Internals ─────────────────────────────────────────────────────────────

    def _on_touch(self, window, touch):
        self._last_activity = time.monotonic()
        return False   # never consume — just observe

    def _current_screen(self):
        root = getattr(self._app, "root", None)
        if root is None:
            return None, None
        name = root.current
        try:
            return name, root.get_screen(name)
        except Exception:
            return name, None

    def _check(self, dt):
        name, screen = self._current_screen()
        if name is None:
            return

        # An in-progress grading/print job (overlay visible) counts as activity
        # so we never yank the user away mid-operation.
        if getattr(screen, "show_success", False):
            self._last_activity = time.monotonic()
            return

        idle = time.monotonic() - self._last_activity

        if name != "landing":
            if idle >= IDLE_TO_LANDING_SEC:
                logger.info("Idle %.0fs → returning to landing screen", idle)
                self._app._nav_stack.clear()
                self._app.navigate("landing", push_history=False)
            return

        # Already on the landing screen: if a session is still open and the
        # kiosk has now been idle long enough, log the user out.
        from wizprinter.session import session_mgr
        if session_mgr.is_valid and idle >= IDLE_TO_LANDING_SEC + LANDING_TO_LOGOUT_SEC:
            logger.info("Landing idle %.0fs → clearing session (auto-logout)", idle)
            import wizprinter.api_client as api
            api.clear_session()
