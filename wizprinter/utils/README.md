# `wizprinter/utils/` — non-UI helpers

Small, focused, Kivy-independent utility modules used across screens.

| File | What it does |
|------|--------------|
| `image_file.py` | `is_valid_jpeg()` — validate a local JPEG/PNG is readable before Kivy loads it (guards against corrupt scans). |
| `pdf_preview.py` | `pdf_to_png_paths()` — rasterize PDF pages to PNGs (via PyMuPDF/`fitz`) for on-screen preview. |
| `printer.py` | `PrinterManager` — thin CUPS wrapper for one-shot printing, with mock-hardware and import guards. |

See each module's top-of-file docstring for detail.
