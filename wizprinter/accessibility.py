"""
WizPrinter Accessibility module
================================
Provides:
  • Text-to-speech (TTS) with a choice of engines (Piper / Pico / espeak-ng)
  • "Explore by touch": first tap on a control speaks its label, second tap
    activates it (screen-reader style)
  • High-contrast colour theme toggle
  • Font-scale application

All features are opt-in via environment variables (see .env.example).

Usage
-----
    from wizprinter.accessibility import a11y
    a11y.speak("Welcome to WizPrinter")

    # Once, at app startup (after the Kivy app is built):
    a11y.install_touch_speech()

Voice quality & engine
----------------------
Preference order (engine="auto"): Piper → Pico → espeak-ng.

  • Piper (recommended) — neural, natural, runs offline on the Pi CPU in real
    time. Best fit for this kiosk. `setup_pi.sh` installs it and downloads a
    default voice into ./voices/, which is auto-discovered. To set up by hand:
        pip install piper-tts
        # download BOTH files for a voice, e.g. en_US-amy-medium:
        #   voices/en_US-amy-medium.onnx  and  voices/en_US-amy-medium.onnx.json
    Kokoro / F5-TTS / ChatTTS were considered but are GPU/desktop-class and too
    heavy for a Pi; Piper is the right neural engine here.

  • Pico (fallback) — small, clearer than espeak:  apt install libttspico-utils
  • espeak-ng (last resort) — always present, robotic but intelligible.

Audio routing
-------------
All engines synthesise to a WAV and play it via paplay/pw-play (PipeWire) so it
reaches the *default sink* — e.g. a Bluetooth speaker. Plain `aplay` (raw ALSA)
is only a last resort because it can land on the wrong output (HDMI) and be
silent. Override the player with A11Y_AUDIO_PLAYER if needed.

Select the engine explicitly with A11Y_TTS_ENGINE = auto | piper | pico | espeak.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import weakref

logger = logging.getLogger(__name__)

# ── Feature flags (from environment) ─────────────────────────────────────────
TTS_ENABLED:           bool  = os.environ.get("A11Y_TTS", "0") == "1"
HIGH_CONTRAST_ENABLED: bool  = os.environ.get("A11Y_HIGH_CONTRAST", "0") == "1"
FONT_SCALE:            float = float(os.environ.get("A11Y_FONT_SCALE", "1.0"))

# ── TTS engine configuration ──────────────────────────────────────────────────
# Engine: "auto" picks the best installed one (piper → pico → espeak).
TTS_ENGINE: str = os.environ.get("A11Y_TTS_ENGINE", "auto").strip().lower()
# espeak-ng tuning. A slower rate, a plain (not pitched-up) voice, and louder
# amplitude are much easier to follow than the defaults. Override the voice with
# A11Y_TTS_VOICE, e.g. "en-gb", "en-us+f2", or an mbrola voice like "mb-en1".
# NOTE: espeak is inherently robotic — installing Pico or Piper (see module
# docstring) is what actually makes it pleasant. These settings only make the
# espeak *fallback* as clear as it can be.
TTS_RATE:  int = int(os.environ.get("A11Y_TTS_RATE", "140"))    # words/minute
TTS_PITCH: int = int(os.environ.get("A11Y_TTS_PITCH", "42"))    # 0-99, lower=deeper
TTS_VOICE: str = os.environ.get("A11Y_TTS_VOICE", "").strip()
# Piper (neural, best on a Pi). PIPER_MODEL points at a .onnx voice; if unset we
# auto-discover the first .onnx under ./voices/. PIPER_BIN overrides the CLI name.
PIPER_MODEL: str = os.environ.get("A11Y_PIPER_MODEL", "").strip()
PIPER_BIN:   str = os.environ.get("A11Y_PIPER_BIN", "piper").strip()
DEFAULT_VOICES_DIR = os.path.abspath("voices")

# All engines synthesise to a WAV and play it through one of these, in order.
# paplay/pw-play go through PipeWire/PulseAudio → the *default sink* (e.g. a
# Bluetooth speaker); aplay talks to raw ALSA and can land on the wrong output
# (HDMI) — so it's only the last resort. Override with A11Y_AUDIO_PLAYER.
AUDIO_PLAYER: str = os.environ.get("A11Y_AUDIO_PLAYER", "").strip()
_PLAYER_PREFERENCE = ("paplay", "pw-play", "aplay")

# ── Explore-by-touch configuration ────────────────────────────────────────────
# When TTS is on, the first tap on a control speaks its label instead of
# activating it; a second tap on the same control activates it. Set to 0 to make
# a single tap both speak and act.
TOUCH_SPEAK_ENABLED: bool = os.environ.get("A11Y_TOUCH_SPEAK", "1") == "1"
# How long a control stays "armed" before a stale first-tap is forgotten.
ARM_TIMEOUT_SEC: float = float(os.environ.get("A11Y_ARM_TIMEOUT_SEC", "6"))

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

# Widget attributes that carry a speakable label, in priority order.
# `a11y_label` is an explicit override a widget (or KV) can set for controls
# whose visible affordance isn't text (e.g. an icon-only Back button).
_LABEL_ATTRS = ("a11y_label", "text", "student_name", "printer_name",
                "title", "status_label")


class _Accessibility:
    """Singleton accessibility controller."""

    def __init__(self):
        self._tts_lock = threading.Lock()
        self._tts_proc: subprocess.Popen | None = None
        self._tts_tmp: str | None = None
        self._resolved_engine: str | None = None
        # Explore-by-touch arming state
        self._arm_lock = threading.Lock()
        self._armed_ref: "weakref.ref | None" = None
        self._arm_timer: threading.Timer | None = None

    # ── TTS ───────────────────────────────────────────────────────────────────

    def speak(self, text: str, interrupt: bool = True) -> None:
        """
        Speak *text* in a background thread using the configured engine.

        Args:
            text:      The string to vocalise.
            interrupt: If True (default), kill any in-progress utterance first.
        """
        if not TTS_ENABLED:
            return
        if not text or not text.strip():
            return
        threading.Thread(
            target=self._do_speak, args=(text.strip(), interrupt), daemon=True
        ).start()

    def _do_speak(self, text: str, interrupt: bool) -> None:
        with self._tts_lock:
            if interrupt:
                self._kill_proc_locked()
            try:
                proc, tmp = self._launch(text)
            except FileNotFoundError:
                logger.warning(
                    "TTS engine '%s' not found; TTS silent this session",
                    self._resolved_engine,
                )
                return
            except Exception as exc:
                logger.warning("TTS error: %s", exc)
                return
            self._tts_proc = proc
            self._tts_tmp = tmp

        # Wait for playback OUTSIDE the lock so a later interrupt can terminate
        # this process, then clean up any temp wav this utterance created.
        try:
            proc.wait()
        except Exception:
            pass
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def _launch(self, text: str) -> tuple[subprocess.Popen, str | None]:
        """
        Synthesise *text* to a temp WAV, then start a player for it.

        Every engine goes through the same player selection so audio always
        lands on the PipeWire/PulseAudio default sink (the Boom), never straight
        on raw-ALSA HDMI. Returns (player_process, temp_wav) for interrupt+cleanup.
        """
        engine = self._engine()
        devnull = subprocess.DEVNULL
        wav = self._mktemp_wav()
        try:
            if engine == "piper":
                subprocess.run(
                    [self._piper_bin(), "-m", self._piper_model(), "-f", wav],
                    input=text.encode("utf-8"),
                    stdout=devnull, stderr=devnull, check=True,
                )
            elif engine == "pico":
                subprocess.run(
                    ["pico2wave", "-l", TTS_VOICE or "en-US", "-w", wav, text],
                    stdout=devnull, stderr=devnull, check=True,
                )
            else:  # espeak
                subprocess.run(
                    [
                        "espeak-ng",
                        "-s", str(TTS_RATE),     # slower = clearer
                        "-p", str(TTS_PITCH),    # lower, not pitched-up
                        "-a", "200",             # louder
                        "-g", "6",               # word gap for separation
                        "-v", TTS_VOICE or "en-us",
                        "-w", wav, "--", text,
                    ],
                    stdout=devnull, stderr=devnull, check=True,
                )
        except BaseException:
            # Synthesis failed — don't leak the temp file.
            try:
                os.remove(wav)
            except OSError:
                pass
            raise

        player = self._play_cmd(wav)
        return subprocess.Popen(player, stdout=devnull, stderr=devnull), wav

    @staticmethod
    def _play_cmd(wav: str) -> list[str]:
        """Choose a WAV player that routes to the default (PipeWire) sink."""
        candidates = [AUDIO_PLAYER] if AUDIO_PLAYER else list(_PLAYER_PREFERENCE)
        for name in candidates:
            if name and shutil.which(name):
                # aplay is quieter about headers with -q; the others take a path.
                return [name, "-q", wav] if name == "aplay" else [name, wav]
        raise FileNotFoundError(
            "No WAV player found (tried: %s). Install pulseaudio-utils or alsa-utils."
            % ", ".join(c for c in candidates if c)
        )

    def _engine(self) -> str:
        """Resolve and cache which engine to use."""
        if self._resolved_engine:
            return self._resolved_engine
        if TTS_ENGINE in ("espeak", "pico", "piper"):
            self._resolved_engine = TTS_ENGINE
        elif self._piper_bin() and self._piper_model():
            self._resolved_engine = "piper"
        elif shutil.which("pico2wave"):
            self._resolved_engine = "pico"
        else:
            self._resolved_engine = "espeak"
        logger.info("TTS engine resolved to '%s'", self._resolved_engine)
        return self._resolved_engine

    @staticmethod
    def _piper_bin() -> str:
        """Resolve the piper CLI — on PATH, an explicit path, or in the venv."""
        if (os.sep in PIPER_BIN or (os.altsep and os.altsep in PIPER_BIN)) \
                and os.path.exists(PIPER_BIN):
            return PIPER_BIN
        found = shutil.which(PIPER_BIN)
        if found:
            return found
        # Installed into the same venv as the running interpreter (systemd runs
        # env/bin/python, so env/bin is usually NOT on PATH).
        venv_dir = os.path.dirname(sys.executable)
        for cand in (os.path.join(venv_dir, PIPER_BIN),
                     os.path.join(venv_dir, PIPER_BIN + ".exe")):
            if os.path.exists(cand):
                return cand
        return ""

    @staticmethod
    def _piper_model() -> str:
        """Explicit A11Y_PIPER_MODEL, else the first .onnx voice under ./voices/."""
        if PIPER_MODEL and os.path.exists(PIPER_MODEL):
            return PIPER_MODEL
        try:
            if os.path.isdir(DEFAULT_VOICES_DIR):
                for name in sorted(os.listdir(DEFAULT_VOICES_DIR)):
                    if name.endswith(".onnx"):
                        return os.path.join(DEFAULT_VOICES_DIR, name)
        except OSError:
            pass
        return ""

    @staticmethod
    def _mktemp_wav() -> str:
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="wiztts_")
        os.close(fd)
        return path

    def _kill_proc_locked(self) -> None:
        if self._tts_proc and self._tts_proc.poll() is None:
            try:
                self._tts_proc.terminate()
                self._tts_proc.wait(timeout=1)
            except Exception:
                pass

    def stop_speaking(self) -> None:
        """Immediately stop any ongoing utterance."""
        with self._tts_lock:
            self._kill_proc_locked()

    @staticmethod
    def tts_enabled() -> bool:
        return TTS_ENABLED

    def set_tts_enabled(self, enabled: bool) -> None:
        """Toggle TTS for the remainder of this session (does not persist to .env)."""
        global TTS_ENABLED
        TTS_ENABLED = enabled
        # Clear any pending "armed" control so state can't leak across toggles.
        self._disarm()

    # ── Explore by touch (speak-first, then activate) ─────────────────────────

    def install_touch_speech(self) -> None:
        """
        Patch Kivy's ButtonBehavior so that, while TTS is enabled, the first tap
        on any button/card speaks its label and the second tap activates it.

        Safe to call once at startup. When TTS is disabled, buttons behave
        exactly as before (single tap acts immediately).
        """
        if not TOUCH_SPEAK_ENABLED:
            return
        try:
            from kivy.uix.behaviors import ButtonBehavior
        except Exception as exc:  # pragma: no cover - Kivy always present at runtime
            logger.warning("Could not install touch-speech: %s", exc)
            return
        if getattr(ButtonBehavior, "_a11y_patched", False):
            return

        original_on_touch_down = ButtonBehavior.on_touch_down
        a11y_self = self

        def patched_on_touch_down(widget, touch):
            # When TTS is off, or this touch isn't a real press on this widget,
            # fall straight through to normal behaviour.
            if (
                not TTS_ENABLED
                or getattr(touch, "is_mouse_scrolling", False)
                or getattr(widget, "disabled", False)
                or not widget.collide_point(touch.x, touch.y)
            ):
                return original_on_touch_down(widget, touch)

            if a11y_self._is_armed(widget):
                # Second tap on the same control → let the real action run.
                a11y_self._disarm()
                return original_on_touch_down(widget, touch)

            # First tap → announce the control and swallow the press.
            a11y_self._arm(widget)
            a11y_self.speak(a11y_self._widget_label(widget))
            return True

        ButtonBehavior.on_touch_down = patched_on_touch_down
        ButtonBehavior._a11y_patched = True
        logger.info("Explore-by-touch (speak-first) installed")

    def _widget_label(self, widget) -> str:
        """Best-effort human-readable label for a control."""
        for attr in _LABEL_ATTRS:
            value = getattr(widget, attr, "")
            if isinstance(value, str) and self._meaningful(value):
                return self._clean_label(value)
        # Many buttons here have no text of their own — the caption is a nested
        # child Label sitting next to icon/chevron Labels. Walk the subtree and
        # take the first *meaningful* text (skipping symbol-only labels like "›").
        try:
            stack = list(getattr(widget, "children", []))
            while stack:
                child = stack.pop(0)
                text = getattr(child, "text", "")
                if isinstance(text, str) and self._meaningful(text):
                    return self._clean_label(text)
                stack.extend(getattr(child, "children", []))
        except Exception:
            pass
        return "button"

    @staticmethod
    def _meaningful(text: str) -> bool:
        # Ignore blanks and pure-symbol captions ("›", "?", "×") — they carry no
        # spoken meaning and would otherwise mask the real label.
        return any(ch.isalnum() for ch in text)

    @staticmethod
    def _clean_label(text: str) -> str:
        # Flatten multi-line button captions and cap length for a tidy utterance.
        flat = " ".join(text.split())
        return flat[:160]

    def _arm(self, widget) -> None:
        with self._arm_lock:
            if self._arm_timer:
                self._arm_timer.cancel()
            self._armed_ref = weakref.ref(widget)
            self._arm_timer = threading.Timer(ARM_TIMEOUT_SEC, self._disarm)
            self._arm_timer.daemon = True
            self._arm_timer.start()

    def _is_armed(self, widget) -> bool:
        with self._arm_lock:
            return self._armed_ref is not None and self._armed_ref() is widget

    def disarm(self) -> None:
        """Public: forget any armed control (call on screen change)."""
        self._disarm()

    def _disarm(self) -> None:
        with self._arm_lock:
            if self._arm_timer:
                self._arm_timer.cancel()
                self._arm_timer = None
            self._armed_ref = None

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
