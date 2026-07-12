#!/usr/bin/env python3
"""
WizPrinter Kiosk — application entry point.

Boots the Raspberry Pi self-service grading/printing kiosk on a 7" 800x480
touchscreen. Responsibilities, in order:
  1. Load environment (.env) and configure logging before any other import.
  2. Apply accessibility patches (high-contrast / font scale) before KV loads.
  3. Set Kivy graphics config (fullscreen, fixed 800x480) before importing kivy.
  4. Record a startup heartbeat, run the app, and record any crash on the way out.

Process restart on crash is handled by the systemd unit (Restart=always), not
here — see docs/deployment_checklist.md.
"""

import os
import sys

from dotenv import load_dotenv
load_dotenv()

# ── Logging must be set up before any other wizprinter import ─────────────────
from wizprinter.logger import setup_logging
setup_logging()

# ── Accessibility patches (high-contrast + font scale) before KV loads ────────
from wizprinter.accessibility import a11y
a11y.apply_high_contrast()
a11y.apply_font_scale()

# ── Set Kivy configuration BEFORE importing kivy ──────────────────────────────
os.environ['KIVY_WINDOW'] = 'sdl2'

from kivy.config import Config
Config.set('graphics', 'width',      '800')
Config.set('graphics', 'height',     '480')
Config.set('graphics', 'resizable',  '0')
Config.set('graphics', 'borderless', '1')
Config.set('graphics', 'fullscreen', '1')
Config.set('kivy',     'keyboard_mode', 'systemanddock')
Config.set('input',    'mouse',      'mouse,multitouch_on_demand')

from kivy.core.window import Window
from wizprinter.app import WizPrinterApp
from wizprinter import telemetry

if __name__ == '__main__':
    Window.size = (800, 480)
    Window.top  = 0
    Window.left = 0

    telemetry.record_heartbeat({"event": "startup"})
    try:
        WizPrinterApp().run()
    except Exception as exc:
        # Crash recovery: record the crash so it survives the process exiting.
        # Actual process restart is handled by the OS service supervisor
        # (see docs/deployment_checklist.md — systemd Restart=on-failure).
        telemetry.record_crash(exc, context="main.run")
        raise
