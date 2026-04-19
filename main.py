"""
WizPrinter Kiosk Application
800x480 HDMI Display — Responsive Layout
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

os.environ['KIVY_WINDOW'] = 'sdl2'

from kivy.config import Config

SCREEN_W = 800
SCREEN_H = 480

# Configure for 800x480 HDMI display
Config.set('graphics', 'width',      str(SCREEN_W))
Config.set('graphics', 'height',     str(SCREEN_H))
Config.set('graphics', 'resizable',  '0')
Config.set('graphics', 'borderless', '1')
Config.set('graphics', 'fullscreen', '1')
Config.set('kivy', 'keyboard_mode',  'systemanddock')
Config.set('input', 'mouse',         'mouse,multitouch_on_demand')

BASE_W = 480
SCALE_FACTOR = SCREEN_W / BASE_W

os.environ['WP_SCALE']    = f'{SCALE_FACTOR:.4f}'
os.environ['WP_SCREEN_W'] = str(SCREEN_W)
os.environ['WP_SCREEN_H'] = str(SCREEN_H)

from wizprinter.app import WizPrinterApp

if __name__ == '__main__':
    WizPrinterApp().run()
