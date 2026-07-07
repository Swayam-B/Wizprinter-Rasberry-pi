# Manual QA Checklist

This covers everything in the release process that requires **real hardware,
a real network, or a real human doing non-visual navigation** — none of
which a CI runner or a plain dev machine can validate. Anything below is a
sign-off checklist, not something `pytest` can claim to have "passed."

If you're looking for what *is* automated, see `tests/` and
`.github/workflows/ci.yml`: rate limiting/backoff classification, path
traversal guarding, grading confidence/grouping logic, mock-hardware mode,
and — specifically — **grading-polling-timeout-exceeded** and **Firebase
token-expiry-mid-session** are both covered by automated unit tests
(`tests/test_session.py::TestTokenExpiryMidSession`,
`wizprinter/screens/grading_status.py`'s `MAX_POLL_ATTEMPTS` logic exercised
indirectly via the grading module tests). Don't re-verify those by hand —
verify everything below instead.

## Update delivery

- [ ] **Staged rollout**: deploy to one canary device, confirm it boots and
      grades/prints correctly for a full period before touching other
      devices (no automated staged-rollout mechanism exists — see
      `docs/deployment_checklist.md`)
- [ ] **Rollback**: from the canary, revert to the previous git commit/tag
      and restart the service; confirm the app boots on the old version
      without leftover state from the new one causing a crash
- [ ] **Reconnect after interrupted update**: kill the update process
      (`git pull` or file copy) halfway through, then restart the service —
      confirm it either fails loudly (doesn't boot into a half-updated,
      silently-broken state) or the update tooling used resumes cleanly
- [ ] **Remote config changes**: change a value via whatever fetches
      `fetch_remote_config()`'s backend source, confirm the kiosk picks it up
      (there's no push mechanism — confirm current behavior is poll-based,
      not real-time, and that this matches expectations)
- [ ] **Version mismatch**: run a kiosk on an older client version against a
      newer backend (and vice versa); confirm failures are visible errors,
      not silent corruption of grading/print data

## Network conditions

- [ ] **Fully offline**: disconnect Wi-Fi mid-session — confirm in-flight API
      calls fail with a visible, non-crashing error (grading submit, exam
      list load, login) rather than hanging forever
- [ ] **Poor/flaky network**: use `tc`/`netem` or a flaky access point to
      simulate high latency + packet loss during grading polling and
      printing; confirm the existing retry/backoff (`api_client._RETRY_MAX`,
      `_RETRY_BASE_SEC`) recovers once the network improves, and that a
      permanently-down network eventually surfaces the timeout error rather
      than polling forever
- [ ] **Logging/monitoring alerts**: with the network down, confirm
      `logs/telemetry.jsonl` still gets local heartbeat/crash entries even
      though the remote beacon (`_post_event` in `wizprinter/telemetry.py`)
      can't reach the backend — local logging must not depend on network
      availability

## Fleet provisioning / setup flow

- [ ] Follow `docs/pi-setup.md` on a genuinely fresh Pi/SD card, start to
      finish, and note anywhere the steps are stale (Kivy/OS version drift,
      renamed packages, etc.)
- [ ] Confirm a freshly provisioned device generates its own
      `logs/device_id` on first run and it's stable across reboots
- [ ] Confirm `WIZPRINTER_MOCK_HARDWARE` is **not** set in the provisioned
      device's `.env` (mock mode is for dev/CI only — see the "known
      limitations" note in `docs/support_notes.md`)

## Accessibility (non-visual, end-to-end)

- [ ] **Non-visual navigation**: with a teacher who cannot see the screen (or
      the screen covered), confirm every screen touched by the grading flow
      (Landing → Login → Dashboard → Classes → Documents → Preview → Grade
      Output popup → Review → student detail popups) can be operated by
      touch alone using only the spoken prompts, with no step that silently
      requires seeing the screen
- [ ] **TTS/audio prompts**: set `A11Y_TTS=1`; confirm every `a11y.speak(...)`
      call site in the touched screens is actually reached during a full
      grading run (Preview submit → Review load → per-student approve →
      finalize), and that nothing talks over itself confusingly
- [ ] **High-contrast mode**: set `A11Y_HIGH_CONTRAST=1`; visually confirm
      every new screen added in this change (Review screen, Grade Output
      popup, Accessibility popup, Admin PIN popup) respects the high-contrast
      palette and doesn't hardcode colors that fight it
- [ ] **Large-text mode**: set `A11Y_FONT_SCALE=1.5` (or higher); confirm
      text doesn't clip/overlap on the 800×480 kiosk display, especially in
      the Review screen's student cards and the Grade Output popup

## Hardware failure recovery

- [ ] **Printer failure**: pull power/USB from the printer mid-job; confirm
      the retry-then-error-popup path (`PRINT_JOB_MAX_RETRIES`) triggers and
      the teacher can retry once the printer's back
- [ ] **Scanner failure**: disconnect the scanner mid-batch; confirm
      `ScanScreen`'s error states surface clearly and a reconnect + "Refresh"
      recovers without needing an app restart
- [ ] **Network failure mid-grading-submit**: kill Wi-Fi right as "Grade" is
      tapped; confirm the submit error is shown (not a silent hang) and
      retry works once reconnected

## Kiosk restart / crash recovery

- [ ] Force-kill the app process (`kill -9`) while mid-scan and mid-grading;
      confirm systemd (`Restart=always`, see `docs/pi-setup.md` §5) brings it
      back up, and that `logs/telemetry.jsonl` has a `"type": "crash"` entry
      from `main.py`'s crash handler for the kill that produced a Python
      exception (a `kill -9` itself won't — that's an OS-level kill with no
      chance for Python to run its except block; use an unhandled exception
      instead — e.g. temporarily raise one in a screen's `on_enter` — to
      exercise the actual crash-logging path)
- [ ] Confirm `temp/` doesn't accumulate unbounded orphaned files across
      repeated crash/restart cycles during a scan-heavy session
