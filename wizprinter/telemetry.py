"""
Minimum-viable fleet-ops telemetry: local heartbeat/crash logging, plus a
best-effort remote beacon if the backend is reachable.

This is intentionally lightweight — a real fleet-management pipeline
(structured metrics, dashboards, alerting rules) is out of scope for a
kiosk-side module. What this gives an on-call person *today*:

  * a local, rotated log of heartbeats and crashes (survives reboots,
    inspectable over SSH even with no network), and
  * a best-effort POST to the backend so a fleet dashboard can eventually
    show "last seen" / crash counts per device, once that endpoint exists.

Missing contract note: there is no documented `/api/telemetry/*` endpoint
yet. `_post_event()` is written defensively (short timeout, swallows all
errors) so it is safe to call speculatively; it simply no-ops against a
backend that doesn't implement the route yet (404/connection errors are
caught and logged at DEBUG, not surfaced to the user).
"""
from __future__ import annotations

import json
import logging
import os
import platform
import time
import uuid

logger = logging.getLogger(__name__)

_LOG_DIR = os.environ.get("LOG_DIR", "logs")
_TELEMETRY_LOG = os.path.join(_LOG_DIR, "telemetry.jsonl")

_DEVICE_ID_FILE = os.path.join(_LOG_DIR, "device_id")


def get_device_id() -> str:
    """Stable per-kiosk id, generated once and cached on disk."""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        if os.path.isfile(_DEVICE_ID_FILE):
            with open(_DEVICE_ID_FILE, "r", encoding="utf-8") as fh:
                existing = fh.read().strip()
                if existing:
                    return existing
        new_id = uuid.uuid4().hex[:12]
        with open(_DEVICE_ID_FILE, "w", encoding="utf-8") as fh:
            fh.write(new_id)
        return new_id
    except OSError:
        return "unknown-device"


def _append_local(event: dict) -> None:
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        with open(_TELEMETRY_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
    except OSError as e:
        logger.warning("Could not write telemetry log: %s", e)


def _post_event(event: dict) -> None:
    """Best-effort remote beacon. Never raises; never blocks the caller long."""
    try:
        import wizprinter.api_client as api
        import requests
        requests.post(
            f"{api.BASE_URL}/api/telemetry/events",
            json=event,
            timeout=5,
        )
    except Exception as e:
        logger.debug("Remote telemetry beacon skipped (%s)", e)


def record_heartbeat(extra: dict | None = None) -> None:
    event = {
        "type": "heartbeat",
        "device_id": get_device_id(),
        "ts": time.time(),
        "platform": platform.platform(),
    }
    if extra:
        event.update(extra)
    _append_local(event)
    _post_event(event)


def record_crash(exc: BaseException, context: str = "") -> None:
    event = {
        "type": "crash",
        "device_id": get_device_id(),
        "ts": time.time(),
        "context": context,
        "exception_type": type(exc).__name__,
        "message": str(exc),
    }
    _append_local(event)
    _post_event(event)
    logger.critical("Crash recorded (%s): %s", context, exc, exc_info=exc)
