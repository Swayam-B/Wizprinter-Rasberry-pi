#!/usr/bin/env python3
"""
WizPrinter Kiosk Application
Raspberry Pi 3.5" Touchscreen (800x480) Self-Service Printing Kiosk
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

if __name__ == '__main__':
    Window.size = (800, 480)
    Window.top  = 0
    Window.left = 0
    WizPrinterApp().run()
