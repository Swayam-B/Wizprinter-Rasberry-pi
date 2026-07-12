# `tests/` — pytest suite

Pure-Python unit tests that run without a display, SANE, or CUPS. CI runs them
with `WIZPRINTER_MOCK_HARDWARE=1` (see [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)).
Kivy-UI and real-hardware behaviour are out of scope here — see
[`docs/manual_qa_checklist.md`](../docs/manual_qa_checklist.md).

Run locally:

```bash
pip install -r requirements-dev.txt
WIZPRINTER_MOCK_HARDWARE=1 pytest -v
```

| File | Covers |
|------|--------|
| `test_accessibility.py` | Runtime TTS enable/disable toggle and `speak()` no-op guards. |
| `test_api_client.py` | Backoff classification, rate limiter, and path-traversal (`_safe_abspath`) guards. |
| `test_grading.py` | Grading domain logic: confidence flagging, review state, grouping. |
| `test_hardware_mock.py` | `PrinterManager` behaviour under mock mode and without pycups. |
| `test_session.py` | Firebase token holder: validity, refresh scheduling, clear. |
| `test_updates.py` | Update version parsing/comparison (`is_newer`). |

`__init__.py` marks the folder as a package for import resolution.
