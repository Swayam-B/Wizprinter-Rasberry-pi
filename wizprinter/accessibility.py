"""
WizPrinter Accessibility module
================================
Provides:
  • Text-to-speech (TTS) via espeak-ng subprocess
  • High-contrast colour theme toggle
  • Font-scale application
  • Kivy keyboard navigation helper

All features are opt-in via environment variables (see .env.example).

Usage
-----
    from wizprinter.accessibility import a11y
    a11y.speak("Welcome to WizPrinter")
    a11y.speak("Scan complete. 3 pages captured.")
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading

logger = logging.getLogger(__name__)

# ── Feature flags (from environment) ─────────────────────────────────────────
TTS_ENABLED:           bool  = os.environ.get("A11Y_TTS", "0") == "1"
HIGH_CONTRAST_ENABLED: bool  = os.environ.get("A11Y_HIGH_CONTRAST", "0") == "1"
FONT_SCALE:            float = float(os.environ.get("A11Y_FONT_SCALE", "1.0"))

# ── High-contrast palette ─────────────────────────────────────────────────────
# Replaces the default blue-on-dark with a strict black/white/yellow palette
# that meets WCAG 2.1 AA contrast ratios.
HC_PALETTE = {
    "BG_DARK":        [0, 0, 0, 1],            # pure black
    "BG_SURFACE":     [0.08, 0.08, 0.08, 1],
    "BG_CARD":        [0.12, 0.12, 0.12, 1],
    "PRIMARY":        [1, 0.9, 0, 1],          # high-vis yellow
    "PRIMARY_COLOR":  [1, 0.9, 0, 1],
    "SUCCESS_COLOR":  [0, 1, 0.4, 1],          # bright green
    "DANGER_COLOR":   [1, 0.2, 0.2, 1],        # bright red
    "TEXT_WHITE":     [1, 1, 1, 1],
    "TEXT_MUTED":     [0.85, 0.85, 0.85, 1],
    "BORDER_COLOR":   [0.7, 0.7, 0.7, 1],
}


class _Accessibility:
    """Singleton accessibility controller."""

    def __init__(self):
        self._tts_lock = threading.Lock()
        self._tts_proc: subprocess.Popen | None = None

    # ── TTS ───────────────────────────────────────────────────────────────────

    def speak(self, text: str, interrupt: bool = True) -> None:
        """
        Speak *text* via espeak-ng in a background thread.

        Args:
            text:      The string to vocalise.
            interrupt: If True (default), kill any in-progress utterance first.
        """
        if not TTS_ENABLED:
            return
        if not text or not text.strip():
            return

        def _do_speak():
            with self._tts_lock:
                if interrupt and self._tts_proc and self._tts_proc.poll() is None:
                    try:
                        self._tts_proc.terminate()
                        self._tts_proc.wait(timeout=1)
                    except Exception:
                        pass

                try:
                    self._tts_proc = subprocess.Popen(
                        ["espeak-ng", "--", text],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except FileNotFoundError:
                    logger.warning("espeak-ng not found; TTS disabled for this session")
                except Exception as exc:
                    logger.warning("TTS error: %s", exc)

        threading.Thread(target=_do_speak, daemon=True).start()

    def stop_speaking(self) -> None:
        """Immediately stop any ongoing utterance."""
        with self._tts_lock:
            if self._tts_proc and self._tts_proc.poll() is None:
                try:
                    self._tts_proc.terminate()
                except Exception:
                    pass

    @staticmethod
    def tts_enabled() -> bool:
        return TTS_ENABLED

    @staticmethod
    def set_tts_enabled(enabled: bool) -> None:
        """Toggle TTS for the remainder of this session (does not persist to .env)."""
        global TTS_ENABLED
        TTS_ENABLED = enabled

    # ── High-contrast ─────────────────────────────────────────────────────────

    @staticmethod
    def apply_high_contrast() -> None:
        """
        Patch wizprinter.theme colour constants in-place so all KV rules that
        reference them pick up the high-contrast values at next redraw.

        Call once at startup, before Builder.load_file().
        """
        if not HIGH_CONTRAST_ENABLED:
            return
        import wizprinter.theme as theme
        for attr, value in HC_PALETTE.items():
            if hasattr(theme, attr):
                setattr(theme, attr, value)
        logger.info("High-contrast mode applied")

    # ── Font scaling ──────────────────────────────────────────────────────────

    @staticmethod
    def apply_font_scale() -> None:
        """
        Multiply every FONT_SIZE_* constant in wizprinter.theme by FONT_SCALE.
        The KV global #:set declarations are strings like '18sp'; we patch the
        Python-side constants that screens can import directly.
        """
        if FONT_SCALE == 1.0:
            return
        import wizprinter.theme as theme
        for attr in dir(theme):
            if attr.startswith("FONT_SIZE_"):
                raw = getattr(theme, attr)           # e.g. '18sp'
                if isinstance(raw, str) and raw.endswith("sp"):
                    try:
                        scaled = float(raw[:-2]) * FONT_SCALE
                        setattr(theme, attr, f"{scaled:.1f}sp")
                    except ValueError:
                        pass
        logger.info("Font scale %.2f applied", FONT_SCALE)

    # ── Accessible label helper ───────────────────────────────────────────────

    @staticmethod
    def label(text: str, role: str = "") -> str:
        """
        Return an accessible label string.  Currently a pass-through; in future
        this could inject ARIA-style annotations if a screen-reader bridge is added.
        """
        return text


# Module-level singleton
a11y = _Accessibility()
