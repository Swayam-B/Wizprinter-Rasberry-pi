# `kv/` — Kivy layout files

Declarative Kivy (`.kv`) layouts for the app. Each screen `.kv` pairs with its
controller in [`wizprinter/screens/`](../wizprinter/screens/); `theme.kv` and
`widgets.kv` provide shared styling and reusable widgets. Load order is defined
by the `kv_files` list in [`wizprinter/app.py`](../wizprinter/app.py) — add new
files there.

| File | Layout for |
|------|-----------|
| `theme.kv` | Global colour/dimension aliases and shared visual rules. |
| `widgets.kv` | `StatusBar`, `BottomNav`, and icon widgets used across screens. |
| `landing.kv` | Splash / "Tap to Start" screen. |
| `login.kv` | Sign-in form. |
| `dashboard.kv` | Home hub. |
| `wifi.kv` | Wi-Fi scan/connect screen. |
| `classes.kv` | Semester/Subject/Class selection. |
| `documents.kv` | Exam list. |
| `printerList.kv` | Printer discovery/selection. |
| `scan.kv` | Scanning screen and thumbnail grid. |
| `preview.kv` | Document/exam preview and grade actions. |
| `review.kv` | Post-grading student review. |
| `settings.kv` | Settings menu (time/region, network, accessibility, help, logout). |

Note: the Settings footer version reads `app.version` (from
`wizprinter.__version__`) — don't hardcode a version string here.
