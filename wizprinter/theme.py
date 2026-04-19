"""
WizPrinter Theme Configuration
Colors and layout constants for 800x480 HDMI display.
"""

import os

# ─── Color Palette ──────────────────────────────────────────
PRIMARY      = [0.075, 0.498, 0.925, 1]
PRIMARY_HEX  = '#137fec'
BG_DARK      = [0.063, 0.098, 0.133, 1]
BG_SURFACE   = [0.098, 0.149, 0.200, 1]
BG_CARD      = [0.118, 0.161, 0.230, 1]
BORDER       = [0.196, 0.302, 0.404, 1]
TEXT_WHITE   = [1, 1, 1, 1]
TEXT_MUTED   = [0.573, 0.678, 0.788, 1]
TEXT_DIM     = [0.4, 0.4, 0.4, 1]
SUCCESS      = [0.180, 0.800, 0.443, 1]
SUCCESS_HEX  = '#2ecc71'
DANGER       = [0.906, 0.298, 0.235, 1]
DANGER_HEX   = '#e74c3c'
BLACK        = [0, 0, 0, 1]
WHITE        = [1, 1, 1, 1]
TRANSPARENT  = [0, 0, 0, 0]

SCREEN_W     = int(os.environ.get('WP_SCREEN_W', 800))
SCREEN_H     = int(os.environ.get('WP_SCREEN_H', 480))
SCALE_FACTOR = float(os.environ.get('WP_SCALE',   '1.667'))

STATUS_BAR_H    = 52
BOTTOM_NAV_H    = 56

TOUCH_TARGET_MIN = 48
BUTTON_H_LARGE   = 64
BUTTON_H_MEDIUM  = 52
BUTTON_RADIUS    = 14

FONT_SIZE_XL  = '48sp'
FONT_SIZE_LG  = '24sp'
FONT_SIZE_MD  = '16sp'
FONT_SIZE_SM  = '13sp'
FONT_SIZE_XS  = '11sp'
FONT_SIZE_XXS = '9sp'
