# Maintenance Procedures

Routine upkeep for a deployed WizPrinter kiosk. Pair with
[deployment_checklist.md](deployment_checklist.md) for release-time steps.

## Logs

All logs live under `logs/` (override with `LOG_DIR`):

- `wizprinter.log` — rotating application log (`LOG_MAX_BYTES`,
  `LOG_BACKUP_COUNT` control rotation; default 5MB × 5 files)
- `telemetry.jsonl` — one JSON object per line: heartbeats (`type:
  "heartbeat"`) and crashes (`type: "crash"`) — see `wizprinter/telemetry.py`
- `device_id` — this kiosk's stable identifier, generated once on first run

To check whether a kiosk is alive and what it's seen recently over SSH:

```bash
tail -n 50 logs/wizprinter.log
tail -n 20 logs/telemetry.jsonl | python3 -m json.tool --json-lines
```

## Routine checks (weekly, or after any incident report)

- [ ] `systemctl status wizprinter` — confirm the service is running and
      note the restart count (`Restart=always` masks crashes unless you look)
- [ ] `grep '"type": "crash"' logs/telemetry.jsonl | tail` — any recent
      crashes and their `exception_type`/`message`
- [ ] Disk space under `temp/` — scanned pages and rendered PDFs accumulate
      there; `PreviewScreen.delete_document()` and `ScanScreen.go_back()`
      clean up their own files, but a kiosk that crashes mid-flow can leave
      orphans. Safe to clear `temp/` entirely while the kiosk is idle.
- [ ] Printer/scanner still enumerate: `lpstat -p` (CUPS) and
      `scanimage -L` (SANE) — compare against what the app's own
      discovery reports on the Printer List / Scan screens

## Common fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| App won't start, `AttributeError` on a kv `root.<property>` | New kv rule references a Kivy property not declared on the screen class | Add the missing `BooleanProperty`/`StringProperty` to the screen's `__init__`/class body — see the `wifi.kv` `pwd_focused` fix in git history for the exact failure mode |
| Grading never finishes, times out at ~10 minutes | Backend grading job stuck, or network flaking during polling | Check backend job status directly; `GradingStatusMixin.MAX_POLL_ATTEMPTS` / `POLL_INTERVAL_SEC` (in `wizprinter/screens/grading_status.py`) control the timeout — raise cautiously, don't remove it |
| Print jobs fail repeatedly | Printer offline/out of paper, or CUPS connection lost | Printer List screen shows live CUPS state (`READY`/`PRINTING`/`STOPPED`); `PRINT_JOB_MAX_RETRIES`/`PRINT_JOB_RETRY_DELAY` control retry behavior |
| Kiosk stuck logged out / keeps returning to Login | Firebase token expired and silent refresh failed (see `wizprinter/session.py`) | Check network connectivity to `securetoken.googleapis.com`; check `FIREBASE_API_KEY` is still valid |
| Can't log out from Settings | `WIZPRINTER_ADMIN_PIN` is set and PIN was entered incorrectly | Confirm the PIN with whoever configured the device's `.env` |

## Rotating the admin PIN

`WIZPRINTER_ADMIN_PIN` lives in the device's `.env` file (loaded by
`python-dotenv` in `main.py`). To change it:

```bash
# on the device
nano .env   # update WIZPRINTER_ADMIN_PIN=...
sudo systemctl restart wizprinter
```

There is no remote PIN-rotation mechanism yet — this is a per-device,
manual value (see the missing-contract note in `wizprinter/admin_pin.py`).

## Clearing a stuck session/selection without a full logout

`wizprinter/api_client.py`'s `clear_session()` wipes in-memory selection
state (semester/subject/class/exam) and the auth token together. There is
no way to clear only the selection state from the UI today; the workaround
is Settings → Log Out (PIN-gated if configured) and logging back in.
