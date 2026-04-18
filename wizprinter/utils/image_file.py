"""Helpers for validating local image files before Kivy loads them."""
import os

from PIL import Image


def is_valid_jpeg(path: str) -> bool:
    """Return True if path is a readable JPEG/PNG suitable for Kivy Image."""
    if not path or not os.path.isfile(path):
        return False
    if os.path.getsize(path) < 32:
        return False
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            im.load()
            fmt = im.format
        return fmt in ("JPEG", "MPO", "PNG")
    except Exception:
        return False
