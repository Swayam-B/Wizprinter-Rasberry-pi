"""
Minimum-viable admin PIN gate.

Guards destructive/administrative actions (currently: Log Out from Settings)
behind a PIN so this isn't a single accidental tap. Opt-in: if
WIZPRINTER_ADMIN_PIN is unset, the gate is a no-op (check() always returns
True) so existing deployments aren't broken by this change.

Missing contract note: there is no remote/rotatable PIN management yet —
this reads a single static PIN from the environment. A real fleet deployment
would want per-device or per-org PINs issued from a backend; this is the
safest workable version until that contract exists (see
docs/deployment_checklist.md follow-up).
"""
import os


def is_enabled() -> bool:
    return bool(os.environ.get("WIZPRINTER_ADMIN_PIN", "").strip())


def check(entered_pin: str) -> bool:
    expected = os.environ.get("WIZPRINTER_ADMIN_PIN", "").strip()
    if not expected:
        return True  # gate disabled — no PIN configured
    return entered_pin.strip() == expected
