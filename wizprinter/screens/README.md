# `wizprinter/screens/` — screen controllers

One module per Kivy `Screen`. Each pairs with a `.kv` layout of the same name in
[`kv/`](../../kv/) and is registered in [`app.py`](../app.py) (both the `kv_files`
list and the `sm.add_widget(...)` block). Screens navigate via
`App.get_running_app().navigate(...)` / `go_back()`.

Typical flow: **landing → login → dashboard → (classes → documents) → scan →
preview → review**.

| File | Screen role |
|------|-------------|
| `landing.py` | Splash / "Tap to Start"; also the idle-timeout and logged-out home screen. |
| `login.py` | Firebase email/password sign-in; never persists credentials. |
| `dashboard.py` | Home hub: live clock, live printer status, heartbeat, navigation to Grade/Scan/Settings. |
| `wifi.py` | Wi-Fi scan/connect via `nmcli`; redacts secrets from status messages. |
| `classes.py` | Dependent Semester → Subject → Class dropdowns feeding the grading selection. |
| `documents.py` | Exam (document) list for the chosen subject. |
| `printer_list.py` | CUPS printer discovery, reachability probing, and selection. |
| `scan.py` | Multi-page hardware scanning (SANE), page management, and PDF compile. |
| `preview.py` | Scan/exam preview, grade-output choice, grade submission, manual print. |
| `grading_status.py` | `GradingStatusMixin`: shared poll → download → print state machine used by preview/review. |
| `review.py` | Post-grading per-student review, correction/override, approval, and finalize. |
| `settings.py` | Time/region, network config, accessibility, remote help, and logout. |

See each module's top-of-file docstring for detail.
