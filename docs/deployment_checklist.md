# Deployment Checklist

Use this before shipping a new kiosk image or pushing an update to fleet
devices. See [pi-setup.md](pi-setup.md) for first-time provisioning and
[manual_qa_checklist.md](manual_qa_checklist.md) for the hardware/e2e sign-off
this checklist points to.

## Before merging to `main`

- [ ] `pytest` passes locally (`pip install -r requirements-dev.txt && pytest`)
- [ ] CI is green (`.github/workflows/ci.yml`) — pure-Python logic + full-tree
      syntax check
- [ ] No new top-level `import cups` / `import sane`-style hardware imports
      outside of a `try/except ImportError` guard (breaks importability on
      non-Pi dev machines and CI — see `wizprinter/utils/printer.py` for the
      pattern)
- [ ] `WIZPRINTER_MOCK_HARDWARE=1 python main.py` still boots on a dev machine
      without a scanner/printer attached (smoke test for the mock-hardware
      mode used by CI)
- [ ] Any new screen is registered in **both** places in `wizprinter/app.py`:
      the `kv_files` list and the `sm.add_widget(...)` block
- [ ] Any new environment variable is documented in `.env.example` (create one
      if it doesn't exist yet) and in this checklist's [Environment
      variables](#environment-variables) section below

## Before flashing/updating a kiosk device

- [ ] Confirm `FIREBASE_API_KEY` and `WIZPRINTER_API_URL` are set correctly
      for the target environment (staging vs. production backend)
- [ ] Confirm the systemd unit's `Restart=always` / `RestartSec=5` policy is
      in place (see [pi-setup.md](pi-setup.md) §5) — this is the actual
      crash-recovery mechanism; the in-app crash logging
      (`wizprinter/telemetry.py`) records *why* a crash happened, it does not
      itself restart the process
- [ ] If `WIZPRINTER_ADMIN_PIN` is set, confirm it's been communicated to the
      staff member responsible for this device (losing it locks logout
      behind a PIN nobody remembers)
- [ ] Manual QA sign-off from [manual_qa_checklist.md](manual_qa_checklist.md)
      is complete for anything touched by this release (printer/scanner
      flows, accessibility, offline behavior, etc.)

## Staged rollout / update delivery

**Missing contract note:** there is no documented staged-rollout, remote-config
push, or version-mismatch-handling contract in this codebase yet.
`wizprinter/api_client.py` has `check_for_update()` and `fetch_remote_config()`
client calls, but nothing server-side is assumed here beyond "returns JSON."
Until that contract exists, treat rollout as manual:

- [ ] Deploy to a single canary device first; watch `logs/wizprinter.log` and
      `logs/telemetry.jsonl` on that device for at least one full class
      period before wider rollout
- [ ] Have a rollback plan: keep the previous known-good git tag/commit
      checked out in a second directory (or documented) so a canary failure
      can be reverted by re-pointing the systemd `WorkingDirectory`/checkout
      without a rebuild
- [ ] After rollout, verify `get_device_id()`-tagged heartbeats
      (`logs/telemetry.jsonl`, and `/api/telemetry/events` once that backend
      route exists) are arriving from the updated devices
- [ ] Reconnect-after-interrupted-update and version-mismatch handling are
      **not implemented** in this codebase — see
      [manual_qa_checklist.md](manual_qa_checklist.md) for what to verify by
      hand until a real update mechanism (e.g. `git pull` + service restart,
      or an OTA image swap) is designed

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `WIZPRINTER_API_URL` | Backend base URL | `http://localhost:8000` |
| `FIREBASE_API_KEY` | Firebase Auth REST key | *(required)* |
| `A11Y_TTS` | Enable text-to-speech at startup | `0` |
| `A11Y_HIGH_CONTRAST` | Enable high-contrast palette at startup | `0` |
| `A11Y_FONT_SCALE` | Multiply all font sizes | `1.0` |
| `WIZPRINTER_MOCK_HARDWARE` | Fake scanner/printer for dev/CI | `0` |
| `WIZPRINTER_ADMIN_PIN` | Require a PIN before Settings → Log Out | *(unset = disabled)* |
| `LOG_DIR` | Rotating log + telemetry file location | `logs` |
| `LOG_LEVEL` | Root logger level | `INFO` |
