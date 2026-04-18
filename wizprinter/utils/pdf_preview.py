"""Rasterize PDF pages to PNG files for Kivy Image widgets."""
import os
import glob

import fitz


def pdf_to_png_paths(
    pdf_path: str,
    out_dir: str,
    max_pages: int = 15,
    zoom: float = 1.35,
) -> list:
    """Return absolute paths to PNGs (one per page), newest render only."""
    os.makedirs(out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, "exam_page_*.png")):
        try:
            os.remove(old)
        except OSError:
            pass

    doc = fitz.open(pdf_path)
    try:
        paths = []
        n = min(len(doc), max_pages)
        mat = fitz.Matrix(zoom, zoom)
        for i in range(n):
            pix = doc.load_page(i).get_pixmap(matrix=mat, alpha=False)
            out = os.path.abspath(os.path.join(out_dir, f"exam_page_{i + 1:03d}.png"))
            pix.save(out)
            paths.append(out)
        return paths
    finally:
        doc.close()
