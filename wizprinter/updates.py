"""
Over-the-air update awareness (client side).

The device periodically asks the backend whether a newer build is available and,
if so, surfaces an "Update Available" popup. This module is deliberately decoupled
from any specific delivery mechanism — it only *detects and notifies*. Wire the
actual download/install into `UpdateManager.apply_update()` (or pass your own
`on_apply` to `show_update_popup`) once the backend/OTA contract exists.

Backend contract
----------------
`UpdateManager` calls `api.check_for_update()` (GET /api/updates/latest). The
expected JSON response, for easy future integration:

    {
        "version":   "2.6.0",           # required — latest available version
        "url":       "https://…/wizprinter-2.6.0.tar.gz",   # optional
        "mandatory": false,              # optional — if true, popup can't be dismissed
        "notes":     "What's new …"      # optional — shown in the popup body
    }

Until that route exists (404) or if the device is offline, the check is a silent
no-op — nothing is shown. Nothing here assumes a running backend, so it is safe
to ship now and light up later by implementing the route and `apply_update()`.

Auth model (mass production): the check is *device-scoped*, not user-scoped. It
sends an `X-Device-Id` header (see api_client._device_headers) and NO user token,
so a kiosk learns about updates even while idle at the landing screen with nobody
logged in. Have the backend authorise/rate-limit on that device id and drive
staged rollouts from it. When you implement `apply_update()`, verify the download
is HTTPS and integrity-checked before swapping anything.
"""
from __future__ import annotations

import logging
import threading

import wizprinter.api_client as api
from wizprinter import __version__

logger = logging.getLogger(__name__)

# How long after boot to run the first check, and how often thereafter.
CHECK_ON_START_DELAY_SEC = 20.0
CHECK_INTERVAL_SEC = 6 * 60 * 60   # every 6 hours


# ── Version comparison (kivy-free so it stays unit-testable) ──────────────────

def _parse_version(v) -> tuple[int, ...]:
    """Parse a dotted version like 'v2.6.0' or '2.6.0-rc1' into a comparable
    int tuple, using only the leading digits of each dotted component."""
    import itertools
    parts = []
    for chunk in str(v).strip().lstrip("vV").split("."):
        digits = "".join(itertools.takewhile(str.isdigit, chunk))
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(candidate, current: str = __version__) -> bool:
    """True if *candidate* is a strictly newer version than *current*."""
    return _parse_version(candidate) > _parse_version(current)


# ── Manager ───────────────────────────────────────────────────────────────────

class UpdateManager:
    """Polls the backend for updates and notifies via a callback."""

    def __init__(self):
        self._notified_version = None
        self._on_update = None
        self._start_ev = None
        self._interval_ev = None

    def start(self, on_update_available) -> None:
        """Begin periodic checks. `on_update_available(info: dict)` runs on the
        Kivy main thread when a newer version is first seen."""
        from kivy.clock import Clock
        self._on_update = on_update_available
        self._start_ev = Clock.schedule_once(
            lambda dt: self.check_now(), CHECK_ON_START_DELAY_SEC
        )
        self._interval_ev = Clock.schedule_interval(
            lambda dt: self.check_now(), CHECK_INTERVAL_SEC
        )
        logger.info("Update manager started (current version %s)", __version__)

    def stop(self) -> None:
        for ev in (self._start_ev, self._interval_ev):
            if ev is not None:
                ev.cancel()
        self._start_ev = self._interval_ev = None

    def check_now(self) -> None:
        """Kick off a non-blocking update check."""
        threading.Thread(target=self._check_bg, daemon=True).start()

    def _check_bg(self) -> None:
        try:
            info = api.check_for_update()
        except Exception as e:
            # 404 (route not built yet), offline, rate-limited, or not authed —
            # all fine, just try again next interval.
            logger.debug("Update check skipped (%s)", e)
            return

        if not isinstance(info, dict):
            return
        latest = info.get("version")
        if not latest or not is_newer(latest):
            return
        if latest == self._notified_version:
            return   # already surfaced this one; don't nag

        self._notified_version = latest
        logger.info("Update available: %s (current %s)", latest, __version__)
        if self._on_update:
            from kivy.clock import Clock
            Clock.schedule_once(lambda dt: self._on_update(info), 0)

    @staticmethod
    def apply_update(info: dict) -> bool:
        """
        Placeholder for the actual update delivery — intentionally NOT
        implemented. Wire this to your mechanism: download `info['url']`, verify
        it, swap the checkout / OTA image, then restart via the systemd unit.

        Returns False so callers show a "manual update required" message until a
        real mechanism is in place.
        """
        logger.warning(
            "apply_update() not implemented — manual update required for %s",
            info.get("version"),
        )
        return False


# ── UI ────────────────────────────────────────────────────────────────────────

def show_update_popup(info: dict, on_apply=None):
    """
    Show the "Update Available" popup. `on_apply(info) -> bool` performs the
    update and returns whether it started; defaults to UpdateManager.apply_update
    (a stub) until real delivery is wired in.
    """
    from kivy.metrics import dp
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup

    version   = info.get("version", "")
    notes     = info.get("notes", "")
    mandatory = bool(info.get("mandatory"))
    apply_fn  = on_apply or UpdateManager.apply_update

    body = f"A new version ({version}) is available."
    if notes:
        body += f"\n\n{notes}"

    content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
    content.add_widget(Label(
        text=body, font_size="13sp", halign="center", valign="middle",
        text_size=(dp(340), None), color=(0.9, 0.94, 1, 1),
    ))
    btn_row = BoxLayout(orientation="horizontal", size_hint_y=None,
                        height=dp(46), spacing=dp(8))
    later_btn  = Button(text="Later", font_size="13sp")
    update_btn = Button(text="Update Now", font_size="13sp",
                        background_color=(0.08, 0.5, 0.9, 1))
    if not mandatory:
        btn_row.add_widget(later_btn)
    btn_row.add_widget(update_btn)
    content.add_widget(btn_row)

    popup = Popup(
        title="Update Available", content=content,
        size_hint=(None, None), size=(dp(400), dp(230)),
        auto_dismiss=not mandatory,
    )

    def do_update(*_a):
        started = False
        try:
            started = apply_fn(info)
        except Exception as e:
            logger.error("apply_update failed: %s", e)
        if started:
            popup.dismiss()
            return
        # No delivery mechanism yet (or it failed) — tell the user gracefully.
        content.clear_widgets()
        content.add_widget(Label(
            text=f"Update {version} needs to be installed by an administrator.\n"
                 "Please contact support.",
            font_size="12sp", halign="center", valign="middle",
            text_size=(dp(340), None), color=(1, 0.9, 0.6, 1),
        ))
        ok_btn = Button(text="OK", size_hint_y=None, height=dp(44), font_size="13sp")
        ok_btn.bind(on_release=lambda *a: popup.dismiss())
        content.add_widget(ok_btn)

    later_btn.bind(on_release=lambda *a: popup.dismiss())
    update_btn.bind(on_release=do_update)
    popup.open()
    return popup
