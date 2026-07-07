"""Unit tests for wizprinter.accessibility — runtime TTS toggle."""
from wizprinter.accessibility import a11y


def test_tts_enabled_toggle_roundtrip():
    original = a11y.tts_enabled()
    try:
        a11y.set_tts_enabled(True)
        assert a11y.tts_enabled() is True
        a11y.set_tts_enabled(False)
        assert a11y.tts_enabled() is False
    finally:
        a11y.set_tts_enabled(original)


def test_speak_is_noop_when_tts_disabled(monkeypatch):
    """When TTS is disabled, speak() must not spawn espeak-ng at all."""
    a11y.set_tts_enabled(False)
    spawned = []
    monkeypatch.setattr(
        "wizprinter.accessibility.subprocess.Popen",
        lambda *a, **kw: spawned.append(1),
    )
    a11y.speak("hello")
    assert spawned == []


def test_speak_ignores_blank_text(monkeypatch):
    a11y.set_tts_enabled(True)
    spawned = []
    monkeypatch.setattr(
        "wizprinter.accessibility.subprocess.Popen",
        lambda *a, **kw: spawned.append(1),
    )
    try:
        a11y.speak("   ")
        assert spawned == []
    finally:
        a11y.set_tts_enabled(False)
