"""
Firebase ID-token refresh + silent renewal loop.

The Firebase REST API returns an idToken (valid for 1 hour) and a
refreshToken (long-lived).  This module stores the refresh token in memory
(never on disk), and schedules a background renewal 5 minutes before expiry.

Usage
-----
    from wizprinter.session import session_mgr
    session_mgr.start(id_token, refresh_token, expires_in_seconds)
    # api_client reads session_mgr.token instead of its own _token

The module intentionally does NOT write any credential to disk.
"""

from __future__ import annotations

import logging
import os
import threading
import time

import requests

logger = logging.getLogger(__name__)

FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "")

# How many seconds before expiry to trigger a proactive refresh
REFRESH_MARGIN_SEC = 5 * 60   # 5 minutes


class _SessionManager:
    """Thread-safe Firebase token holder with automatic silent renewal."""

    def __init__(self):
        self._lock = threading.Lock()
        self._id_token: str = ""
        self._refresh_token: str = ""
        self._expires_at: float = 0.0       # monotonic clock
        self._renewal_timer: threading.Timer | None = None
        self._on_refreshed_callbacks: list = []

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def token(self) -> str:
        """Current Firebase idToken (may be empty if not logged in)."""
        with self._lock:
            return self._id_token

    @property
    def is_valid(self) -> bool:
        """True if we have a token and it has not expired yet."""
        with self._lock:
            return bool(self._id_token) and time.monotonic() < self._expires_at

    def start(self, id_token: str, refresh_token: str, expires_in: int = 3600) -> None:
        """
        Initialise the session after a successful sign-in.

        Args:
            id_token:      Firebase idToken.
            refresh_token: Firebase refreshToken (kept only in memory).
            expires_in:    Seconds until idToken expires (default: 3600).
        """
        with self._lock:
            self._id_token = id_token
            self._refresh_token = refresh_token
            self._expires_at = time.monotonic() + expires_in

        self._schedule_renewal(expires_in)
        logger.info("Session started; token expires in %ds", expires_in)

    def clear(self) -> None:
        """Wipe all credentials from memory (call on logout)."""
        with self._lock:
            self._id_token = ""
            self._refresh_token = ""
            self._expires_at = 0.0
            if self._renewal_timer:
                self._renewal_timer.cancel()
                self._renewal_timer = None
        logger.info("Session cleared")

    def on_refreshed(self, callback) -> None:
        """Register a callback(new_token: str) invoked after each silent renewal."""
        self._on_refreshed_callbacks.append(callback)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _schedule_renewal(self, expires_in: int) -> None:
        delay = max(0, expires_in - REFRESH_MARGIN_SEC)
        with self._lock:
            if self._renewal_timer:
                self._renewal_timer.cancel()
            self._renewal_timer = threading.Timer(delay, self._do_refresh)
            self._renewal_timer.daemon = True
            self._renewal_timer.start()
        logger.debug("Token renewal scheduled in %ds", delay)

    def _do_refresh(self) -> None:
        logger.info("Refreshing Firebase token silently…")
        with self._lock:
            rt = self._refresh_token
        if not rt:
            logger.warning("No refresh token available; cannot renew")
            return

        if not FIREBASE_API_KEY:
            logger.error("FIREBASE_API_KEY missing; cannot refresh token")
            return

        try:
            resp = requests.post(
                f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}",
                json={"grant_type": "refresh_token", "refresh_token": rt},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()

            new_id_token    = data["id_token"]
            new_refresh_tok = data.get("refresh_token", rt)
            expires_in      = int(data.get("expires_in", 3600))

            with self._lock:
                self._id_token      = new_id_token
                self._refresh_token = new_refresh_tok
                self._expires_at    = time.monotonic() + expires_in

            self._schedule_renewal(expires_in)
            logger.info("Token silently renewed; next renewal in %ds", expires_in)

            for cb in self._on_refreshed_callbacks:
                try:
                    cb(new_id_token)
                except Exception as exc:
                    logger.warning("on_refreshed callback raised: %s", exc)

        except Exception as exc:
            logger.error("Silent token refresh failed: %s", exc)
            # Retry in 60 s rather than leaving the user silently logged-out
            self._schedule_renewal(60)


# Module-level singleton used by api_client and login screen
session_mgr = _SessionManager()
