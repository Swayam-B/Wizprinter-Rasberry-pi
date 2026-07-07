"""
Tests for the mock-hardware test mode (WIZPRINTER_MOCK_HARDWARE=1).

These modules read the env var at import time, so tests that flip it use
importlib.reload() to force re-evaluation, and restore the original state
afterward so later tests/modules aren't affected.
"""
import importlib

import wizprinter.hardware as hardware_mod


def test_mock_hardware_off_by_default(monkeypatch):
    monkeypatch.delenv("WIZPRINTER_MOCK_HARDWARE", raising=False)
    importlib.reload(hardware_mod)
    assert hardware_mod.MOCK_HARDWARE is False


def test_mock_hardware_enabled_via_env(monkeypatch):
    monkeypatch.setenv("WIZPRINTER_MOCK_HARDWARE", "1")
    importlib.reload(hardware_mod)
    try:
        assert hardware_mod.MOCK_HARDWARE is True
    finally:
        monkeypatch.delenv("WIZPRINTER_MOCK_HARDWARE", raising=False)
        importlib.reload(hardware_mod)


def test_printer_manager_mock_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZPRINTER_MOCK_HARDWARE", "1")
    importlib.reload(hardware_mod)
    import wizprinter.utils.printer as printer_mod
    importlib.reload(printer_mod)

    try:
        mgr = printer_mod.PrinterManager()
        assert mgr.conn is None  # mock mode never opens a real CUPS connection

        fake_pdf = tmp_path / "doc.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake")
        assert mgr.print_document(str(fake_pdf), "Any-Printer") is True
    finally:
        monkeypatch.delenv("WIZPRINTER_MOCK_HARDWARE", raising=False)
        importlib.reload(hardware_mod)
        importlib.reload(printer_mod)


def test_printer_manager_without_cups_installed_fails_soft(tmp_path, monkeypatch):
    """
    If pycups isn't installed and mock mode is off, PrinterManager must
    degrade gracefully (no connection, print_document() returns False)
    rather than raising ImportError at import time. This is what makes it
    possible to import/test this module at all on a machine without CUPS.
    """
    monkeypatch.setenv("WIZPRINTER_MOCK_HARDWARE", "0")
    importlib.reload(hardware_mod)
    import wizprinter.utils.printer as printer_mod
    importlib.reload(printer_mod)
    monkeypatch.setattr(printer_mod, "cups", None)

    try:
        mgr = printer_mod.PrinterManager()
        assert mgr.conn is None

        fake_pdf = tmp_path / "doc.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake")
        assert mgr.print_document(str(fake_pdf)) is False
    finally:
        importlib.reload(hardware_mod)
        importlib.reload(printer_mod)
