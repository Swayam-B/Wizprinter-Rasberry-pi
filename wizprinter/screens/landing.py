"""
Landing / splash screen — "TAP TO START".

Also serves as the logged-out / auto-logout home screen. Tapping start runs a
quick connectivity check off the UI thread: if the device can't reach the
internet (which login needs), the user is sent to the Wi-Fi screen to connect
first; otherwise straight to the login screen.
"""

import logging
import socket
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.screenmanager import Screen

logger = logging.getLogger(__name__)


def _has_internet(timeout: float = 1.2) -> bool:
    """Best-effort internet reachability check (DNS port on public resolvers)."""
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            sock = socket.create_connection((host, 53), timeout=timeout)
            sock.close()
            return True
        except OSError:
            continue
    return False


class LandingScreen(Screen):
    """Initial landing screen with WizPrinter branding."""

    def on_tap_start(self):
        # Connectivity check can block briefly, so run it off the UI thread and
        # route once we know the result.
        threading.Thread(target=self._route_by_connectivity, daemon=True).start()

    def _route_by_connectivity(self):
        online = _has_internet()
        Clock.schedule_once(lambda dt: self._go(online), 0)

    def _go(self, online: bool):
        app = App.get_running_app()
        if online:
            app.navigate("login")
        else:
            logger.info("No internet at start → routing to Wi-Fi setup")
            app.navigate("wifi")
