#!/usr/bin/env python3
"""
WizPrinter Kiosk Application
Raspberry Pi 3.5" Touchscreen (480x320) Self-Service Printing Kiosk
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Set Kivy configuration BEFORE importing kivy
os.environ['KIVY_WINDOW'] = 'sdl2'

from kivy.config import Config

# Configure for 480x320 kiosk display
Config.set('graphics', 'width', '800')
Config.set('graphics', 'height', '480')
Config.set('graphics', 'resizable', '0')
Config.set('graphics', 'borderless', '1')
Config.set('graphics', 'fullscreen', '1')
Config.set('kivy', 'keyboard_mode', 'systemanddock')
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

from kivy.core.window import Window
from wizprinter.app import WizPrinterApp

if __name__ == '__main__':
    # 2. MANUAL OVERRIDE (This kills the "Bottom-Left" bug)
    Window.size = (800, 480)
    Window.top = 0
    Window.left = 0
    WizPrinterApp().run()