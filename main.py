#!/usr/bin/env python3
"""
WizPrinter Kiosk Application
Raspberry Pi 3.5" Touchscreen (480x320) Self-Service Printing Kiosk
"""

import os
import sys

# Set Kivy configuration BEFORE importing kivy
os.environ['KIVY_WINDOW'] = 'sdl2'

from kivy.config import Config

# Configure for 480x320 kiosk display
Config.set('graphics', 'width', '480')
Config.set('graphics', 'height', '320')
Config.set('graphics', 'resizable', '0')
Config.set('graphics', 'borderless', '1')
Config.set('graphics', 'fullscreen', '0')  # Set to '1' on actual Pi
Config.set('kivy', 'keyboard_mode', 'systemanddock')
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

from wizprinter.app import WizPrinterApp

if __name__ == '__main__':
    WizPrinterApp().run()
