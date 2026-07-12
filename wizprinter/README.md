# `wizprinter/` — application package

Core Python package for the WizPrinter kiosk. Screens live in
[`screens/`](screens/), reusable UI widgets in [`widgets/`](widgets/), and
non-UI helpers in [`utils/`](utils/). Kivy layouts (`.kv`) live in the
top-level [`kv/`](../kv/) folder.

| File | What it does |
|------|--------------|
| `__init__.py` | Package marker; holds `__version__` — the single source of truth for the app version. |
| `app.py` | `WizPrinterApp` (Kivy `App`): loads KV, registers screens, owns the navigation history stack, and starts the idle watchdog + update checker. |
| `accessibility.py` | Text-to-speech (Piper/Pico/espeak with PipeWire routing), "explore by touch" speak-then-activate, high-contrast theme, and font scaling. |
| `admin_pin.py` | Optional PIN gate (env `WIZPRINTER_ADMIN_PIN`) guarding destructive actions like logout. |
| `api_client.py` | All backend/Firebase HTTP calls, retry/backoff, per-endpoint rate limiting, and path-traversal-safe file download/upload. |
| `grading.py` | Pure grading domain logic: output modes, confidence flagging, review state, and client-side grouping. No Kivy dependency. |
| `hardware.py` | Single switch (`MOCK_HARDWARE`) that fakes scanner/printer for dev/CI. |
| `idle.py` | Inactivity watchdog: idle → 30s logout-warning countdown → auto-logout + landing. |
| `logger.py` | Rotating-file + console logging setup; call `setup_logging()` once at startup. |
| `session.py` | Firebase ID-token holder with automatic silent refresh; keeps tokens in memory only. |
| `telemetry.py` | Local heartbeat/crash logging plus a best-effort remote beacon. |
| `theme.py` | Colour palette, dimensions, and typography constants shared by Python and KV. |
| `updates.py` | Update-available detection, version comparison, and the "Update Available" popup (ready for backend/OTA integration). |

See each module's top-of-file docstring for detail.
