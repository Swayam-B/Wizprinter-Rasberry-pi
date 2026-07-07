# Support Notes

Quick reference for whoever answers "the printer kiosk isn't working" calls.

## First questions to ask

1. **What's on the screen right now?** (blank/black, frozen, an error popup,
   stuck on a spinner) — narrows down app-crashed vs. app-hung vs.
   expected-error-with-a-message
2. **Did anything change recently?** (Wi-Fi password, printer moved/replaced,
   a software update was pushed)
3. **Can they read the on-screen message to you?** Most failure paths in
   this app show a popup with the actual error (see "Where errors show up"
   below) rather than failing silently.

## Where errors show up

- **Grading errors / timeouts** — popup titled "Grading Error" or "Grading
  Timed Out" with a Retry button (`wizprinter/screens/preview.py`,
  `_on_grading_failed`)
- **Print failures** — popup titled "Print Failed" with Retry, after 3
  automatic retries already failed (`wizprinter/screens/grading_status.py`)
- **Scanner issues** — inline status message on the Scan screen
  ("NO SCANNER FOUND", "ADF EMPTY — place pages in feeder", "SCANNER BUSY",
  etc. — `wizprinter/screens/scan.py`)
- **Network/Wi-Fi** — Wi-Fi screen shows connect status inline; error
  messages are redacted of anything that looks like a password before
  display or being spoken by TTS
- **Login** — generic-but-distinct messages ("Invalid email or password",
  "Email not registered", "Login failed. Check your connection.")

## Remote support hook

Settings → **Get Help** (`wizprinter/screens/settings.py`,
`request_help()`) sends a best-effort POST to
`{WIZPRINTER_API_URL}/api/support/request` with a reason and context, then
tells the teacher whether it reached support or not.

**Missing contract note:** `/api/support/request` is not a documented
backend endpoint yet (see `wizprinter/api_client.py`,
`request_remote_support()`). Until the backend implements it, this button
will always report "Could Not Reach Support" — that is expected, not a bug,
and is the honest fallback rather than a fake success message.

## Escalation checklist before calling engineering

- [ ] Check `logs/wizprinter.log` (last ~50 lines) on the affected device
      for the actual exception/traceback
- [ ] Check `logs/telemetry.jsonl` for a recent `"type": "crash"` entry —
      it'll have `exception_type` and `message`
- [ ] Confirm the device's `device_id` (`logs/device_id`) so engineering
      can correlate with any backend-side logs, once telemetry ingestion
      exists server-side
- [ ] Note whether `WIZPRINTER_MOCK_HARDWARE` is accidentally left enabled
      on a real kiosk (`.env`) — this would make printing/scanning silently
      "succeed" without touching real hardware, which looks like "nothing
      comes out of the printer" to a teacher

## Known limitations to set expectations on

- No remote/staged update rollout mechanism yet — updates are a manual
  `git pull` + service restart on each device (see
  [deployment_checklist.md](deployment_checklist.md))
- No fleet dashboard yet — "is this kiosk online" today means SSH-ing in and
  reading `logs/telemetry.jsonl`, not a web UI
- Per-response grading confidence/override data depends on the backend
  returning fields (`responses`, `confidence`) that aren't a finalized
  contract — see `wizprinter/grading.py` module docstring. A student card
  with "No per-response detail available" is expected if the backend hasn't
  started returning that shape yet, not a bug in the review screen.
