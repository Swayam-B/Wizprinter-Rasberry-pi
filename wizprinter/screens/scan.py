"""Scan screen — threaded hardware scanning with timeouts, progress, guards, and cleanup."""

import os
import re
import shutil
import subprocess
import tempfile
import threading

from PIL import Image as PILImage, ImageChops
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.uix.image import Image as KivyImage
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty, ListProperty, NumericProperty
from kivy.clock import Clock
from kivy.metrics import dp

from wizprinter.hardware import MOCK_HARDWARE
from wizprinter.utils.image_file import is_valid_jpeg

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_PAGES = 30          # Hard guard: refuse to scan beyond this many pages
SCAN_TIMEOUT_SEC = 60   # subprocess timeout for a single scanimage call
SCAN_BASE_DIR = "temp"  # root temp dir; cleaned on go_back and on app start


# ── Image helpers ─────────────────────────────────────────────────────────────

def _crop_white_bottom(img: PILImage.Image, fuzz: int = 12, bottom_padding: int = 8) -> PILImage.Image:
    """Trim trailing white rows from the bottom of a scanned page."""
    rgb = img.convert("RGB")
    bg = PILImage.new("RGB", rgb.size, (255, 255, 255))
    diff = ImageChops.difference(rgb, bg).convert("L")
    diff = diff.point(lambda p: 255 if p > fuzz else 0)
    bbox = diff.getbbox()
    if not bbox:
        return rgb
    _, _, _, bottom = bbox
    new_bottom = min(rgb.height, bottom + bottom_padding)
    if new_bottom < rgb.height:
        return rgb.crop((0, 0, rgb.width, new_bottom))
    return rgb


# ── Error popup helper ─────────────────────────────────────────────────────────

def _show_error_popup(title: str, message: str, on_dismiss=None):
    """Display a user-facing modal error popup."""
    content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
    content.add_widget(Label(
        text=message,
        text_size=(dp(340), None),
        halign="center",
        valign="middle",
        font_size="13sp",
        color=(1, 0.9, 0.9, 1),
    ))
    btn = Button(
        text="OK",
        size_hint=(1, None),
        height=dp(44),
        font_size="14sp",
    )
    content.add_widget(btn)
    popup = Popup(
        title=title,
        content=content,
        size_hint=(None, None),
        size=(dp(380), dp(200)),
        auto_dismiss=True,
    )
    btn.bind(on_release=lambda *a: popup.dismiss())
    if on_dismiss:
        popup.bind(on_dismiss=lambda *a: on_dismiss())
    popup.open()
    return popup


# ── Screen ────────────────────────────────────────────────────────────────────

class ScanScreen(Screen):
    """Multi-page hardware scanning with threaded I/O, timeouts, and full cleanup."""

    page_info = StringProperty("Page 0")
    is_scanning = BooleanProperty(False)
    status_msg = StringProperty("READY TO SCAN")
    scanned_images = ListProperty([])
    scan_progress = StringProperty("")   # e.g. "Scanning page 3…"
    scanner_found = BooleanProperty(False)
    no_device_msg = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.temp_dir = os.path.abspath(SCAN_BASE_DIR)
        os.makedirs(self.temp_dir, exist_ok=True)
        self.device_path: str | None = None
        # Scanner discovery runs once at startup in a background thread
        threading.Thread(target=self._discover_scanner_bg, daemon=True).start()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_pre_enter(self, *args):
        """Drop corrupt/empty leftovers so Kivy never tries to load them."""
        if not os.path.isdir(self.temp_dir):
            return
        for name in os.listdir(self.temp_dir):
            if not name.lower().endswith((".jpg", ".jpeg")):
                continue
            path = os.path.join(self.temp_dir, name)
            if not is_valid_jpeg(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        # Reconcile list with disk
        self.scanned_images = [
            os.path.abspath(p)
            for p in self.scanned_images
            if is_valid_jpeg(p)
        ]
        self._update_page_info()

    # ── Scanner discovery ─────────────────────────────────────────────────────

    def _discover_scanner_bg(self):
        """Background thread: find an airscan/USB SANE device."""
        if MOCK_HARDWARE:
            Clock.schedule_once(lambda dt: self._on_discovery_done("Mock Scanner", ""), 0)
            return
        device = None
        try:
            if not shutil.which("scanimage"):
                Clock.schedule_once(lambda dt: self._on_discovery_done(None,
                    "scanimage not found. Install SANE."), 0)
                return
            result = subprocess.run(
                ["scanimage", "-L"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            for line in result.stdout.splitlines():
                m = re.search(r"`(.*?)'", line)
                if m:
                    device = m.group(1)
                    break  # Take first available scanner
        except subprocess.TimeoutExpired:
            Clock.schedule_once(lambda dt: self._on_discovery_done(None,
                "Scanner discovery timed out."), 0)
            return
        except Exception as e:
            Clock.schedule_once(lambda dt: self._on_discovery_done(None, str(e)), 0)
            return
        Clock.schedule_once(lambda dt: self._on_discovery_done(device, ""), 0)

    def _on_discovery_done(self, device: str | None, error: str):
        if device:
            self.device_path = device
            self.scanner_found = True
            self.no_device_msg = ""
            self.status_msg = "READY TO SCAN"
            print(f"[Scan] Scanner: {device}")
        else:
            self.device_path = None
            self.scanner_found = False
            self.no_device_msg = error or "No scanner detected. Connect scanner and tap Refresh."
            self.status_msg = "NO SCANNER FOUND"

    def rediscover_scanner(self):
        """User-triggered re-scan for hardware."""
        self.status_msg = "SEARCHING FOR SCANNER…"
        self.no_device_msg = ""
        threading.Thread(target=self._discover_scanner_bg, daemon=True).start()

    # ── Thumbnail grid ────────────────────────────────────────────────────────

    def on_scanned_images(self, instance, value):
        """Kivy observer: repopulate thumbnail grid whenever page list changes."""
        if "thumbnail_grid" not in self.ids:
            return
        grid = self.ids.thumbnail_grid
        grid.clear_widgets()
        for img_path in value:
            if not is_valid_jpeg(img_path):
                continue
            abs_path = os.path.abspath(img_path)
            img_widget = KivyImage(
                source=abs_path,
                size_hint=(1, None),
                allow_stretch=True,
                keep_ratio=True,
            )
            img_widget.bind(width=lambda ins, val: setattr(ins, "height", val * 1.294))
            img_widget.reload()
            grid.add_widget(img_widget)
        Clock.schedule_once(self._scroll_to_bottom, 0.1)
        self._update_page_info()

    def _scroll_to_bottom(self, dt):
        if "scroll_container" in self.ids:
            self.ids.scroll_container.scroll_y = 0

    def _update_page_info(self):
        n = len(self.scanned_images)
        self.page_info = f"{n} Page{'s' if n != 1 else ''}"

    # ── Scanning ──────────────────────────────────────────────────────────────

    def add_page(self):
        """Initiate a hardware scan on a background thread."""
        if self.is_scanning:
            return

        if not self.scanner_found or not self.device_path:
            _show_error_popup(
                "No Scanner",
                "No scanner is connected.\nConnect scanner and tap Refresh.",
            )
            return

        if not shutil.which("scanimage"):
            _show_error_popup("Scanner Error", "scanimage not installed. Run setup_pi.sh.")
            return

        if len(self.scanned_images) >= MAX_PAGES:
            _show_error_popup(
                "Page Limit Reached",
                f"Maximum {MAX_PAGES} pages per batch.\n"
                "Tap Upload to submit this batch before scanning more.",
            )
            return

        self.is_scanning = True
        page_num = len(self.scanned_images) + 1
        self.status_msg = f"SCANNING PAGE {page_num}…"
        self.scan_progress = f"Scanning page {page_num}…"
        threading.Thread(target=self._perform_scan_bg, daemon=True).start()

    def _perform_scan_bg(self):
        """Run scanimage in a background thread with subprocess timeout."""
        # Write to a fresh temp file; rename on success to avoid partial files
        fd, tmp_path = tempfile.mkstemp(suffix=".jpg", dir=self.temp_dir)
        os.close(fd)

        page_num = len(self.scanned_images) + 1
        out_path = os.path.join(self.temp_dir, f"page_{page_num:03d}.jpg")

        if MOCK_HARDWARE:
            try:
                PILImage.new("RGB", (850, 1100), (255, 255, 255)).save(tmp_path, "JPEG")
                os.replace(tmp_path, out_path)
                abs_out = os.path.abspath(out_path)
                Clock.schedule_once(lambda dt, p=abs_out: self._on_scan_success(p), 0)
            except Exception as e:
                Clock.schedule_once(
                    lambda dt, err=e: self._on_scan_error(f"Mock scan error:\n{err}", tmp_path), 0
                )
            return

        cmd = [
            "scanimage",
            "-d", self.device_path,
            "--format=jpeg",
            f"--output-file={tmp_path}",
            "--mode", "Gray",
            "--resolution", "150",
            "-x", "215.9",
            "-y", "279.4",
        ]
        # Try ADF first; fall back to Flatbed if ADF fails
        adf_cmd = cmd + ["--source", "ADF"]

        def run_cmd(c):
            return subprocess.run(
                c,
                capture_output=True,
                text=True,
                timeout=SCAN_TIMEOUT_SEC,
            )

        try:
            result = run_cmd(adf_cmd)

            if result.returncode != 0:
                stderr_lower = result.stderr.lower()
                if "out of paper" in stderr_lower or "no documents" in stderr_lower:
                    # ADF empty — try flatbed
                    Clock.schedule_once(lambda dt: self._update_progress("ADF empty, trying Flatbed…"), 0)
                    flatbed_cmd = cmd + ["--source", "Flatbed"]
                    result = run_cmd(flatbed_cmd)

            if result.returncode != 0:
                stderr_lower = result.stderr.lower()
                if "out of paper" in stderr_lower or "no documents" in stderr_lower:
                    error_msg = "ADF EMPTY — place pages in feeder"
                elif "invalid argument" in stderr_lower:
                    error_msg = "SCANNER ARGUMENT ERROR\nCheck device compatibility"
                elif "device busy" in stderr_lower:
                    error_msg = "SCANNER BUSY — try again"
                else:
                    error_msg = f"SCAN ERROR\n{result.stderr.strip()[:120]}"
                Clock.schedule_once(
                    lambda dt, m=error_msg: self._on_scan_error(m, tmp_path), 0
                )
                return

            # Validate the produced file
            if not is_valid_jpeg(tmp_path):
                Clock.schedule_once(
                    lambda dt: self._on_scan_error("Scanner produced invalid image", tmp_path), 0
                )
                return

            # Atomic rename
            os.replace(tmp_path, out_path)
            abs_out = os.path.abspath(out_path)
            Clock.schedule_once(lambda dt, p=abs_out: self._on_scan_success(p), 0)

        except subprocess.TimeoutExpired:
            Clock.schedule_once(
                lambda dt: self._on_scan_error(
                    f"Scan timed out after {SCAN_TIMEOUT_SEC}s.\nCheck scanner connection.", tmp_path
                ), 0
            )
        except FileNotFoundError:
            Clock.schedule_once(
                lambda dt: self._on_scan_error("scanimage not found.", tmp_path), 0
            )
        except Exception as e:
            Clock.schedule_once(
                lambda dt, err=e: self._on_scan_error(f"Unexpected error:\n{err}", tmp_path), 0
            )

    def _update_progress(self, msg: str):
        self.scan_progress = msg

    def _on_scan_success(self, path: str):
        self.is_scanning = False
        self.scan_progress = ""
        self.scanned_images = self.scanned_images + [path]
        remaining = MAX_PAGES - len(self.scanned_images)
        self.status_msg = f"PAGE ADDED — {remaining} remaining"

    def _on_scan_error(self, message: str, tmp_path: str | None = None):
        self.is_scanning = False
        self.scan_progress = ""
        self.status_msg = "SCAN FAILED"
        # Clean up any partial temp file
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        _show_error_popup("Scan Error", message)

    # ── Page management ───────────────────────────────────────────────────────

    def delete_page(self):
        """Remove the most recent page from batch and disk."""
        if not self.scanned_images:
            return
        new_list = list(self.scanned_images)
        img_to_remove = new_list.pop()
        if os.path.exists(img_to_remove):
            try:
                os.remove(img_to_remove)
            except OSError as e:
                print(f"[Scan] Could not remove {img_to_remove}: {e}")
        self.scanned_images = new_list
        self.status_msg = "PAGE DELETED"

    # ── Upload / compile ──────────────────────────────────────────────────────

    def upload(self):
        """Compile JPG batch into PDF and switch to Preview."""
        if not self.scanned_images:
            _show_error_popup("No Pages", "Scan at least one page before uploading.")
            return

        valid_paths = [p for p in self.scanned_images if is_valid_jpeg(p)]
        if not valid_paths:
            _show_error_popup("No Valid Pages", "All scanned pages are corrupt. Please rescan.")
            return

        self.status_msg = "COMPILING PDF…"
        threading.Thread(
            target=self._compile_pdf_bg,
            args=(valid_paths,),
            daemon=True,
        ).start()

    def _compile_pdf_bg(self, paths: list[str]):
        scan_pdf_dir = os.path.abspath(os.path.join(SCAN_BASE_DIR, "scan_pdf"))
        os.makedirs(scan_pdf_dir, exist_ok=True)

        # Wipe previous PDF output
        for old_file in os.listdir(scan_pdf_dir):
            try:
                os.remove(os.path.join(scan_pdf_dir, old_file))
            except OSError:
                pass

        pdf_path = os.path.join(scan_pdf_dir, "latest_scan.pdf")

        try:
            images = []
            for i, path in enumerate(paths):
                Clock.schedule_once(
                    lambda dt, n=i + 1, t=len(paths): setattr(
                        self, "scan_progress", f"Processing page {n}/{t}…"
                    ), 0
                )
                original = PILImage.open(path)
                cropped = _crop_white_bottom(original)
                cropped.save(path, "JPEG", quality=95)
                images.append(cropped.convert("RGB"))

            if not images:
                Clock.schedule_once(
                    lambda dt: _show_error_popup("Compile Error", "No valid images to compile."), 0
                )
                return

            images[0].save(
                pdf_path,
                save_all=True,
                append_images=images[1:],
                resolution=150,
            )

            # Hand off to Preview screen
            Clock.schedule_once(lambda dt, p=pdf_path: self._on_compile_done(p), 0)

        except Exception as e:
            Clock.schedule_once(
                lambda dt, err=e: self._on_compile_error(err), 0
            )

    def _on_compile_done(self, pdf_path: str):
        self.scan_progress = ""
        self.status_msg = "UPLOAD COMPLETE"
        # Clear in-memory list but keep files on disk until Preview is done
        pages_to_clear = list(self.scanned_images)
        self.scanned_images = []

        app = App.get_running_app()
        preview_screen = app.root.get_screen("preview")
        preview_screen.scanned_pdf_path = pdf_path
        preview_screen.show_scan_jpeg_previews()
        app.navigate("preview")

    def _on_compile_error(self, exc: Exception):
        self.scan_progress = ""
        self.status_msg = "PDF ERROR"
        _show_error_popup("Compile Error", f"Could not compile PDF:\n{exc}")

    # ── Cleanup & navigation ──────────────────────────────────────────────────

    def _cleanup_temp_scans(self):
        """Delete all in-memory-tracked temp scan files from disk."""
        for img in list(self.scanned_images):
            if os.path.exists(img):
                try:
                    os.remove(img)
                except OSError as e:
                    print(f"[Scan] Cleanup error: {e}")
        self.scanned_images = []

    def go_back(self):
        """Return to dashboard and clean up temp scan files."""
        self._cleanup_temp_scans()
        self.status_msg = "READY TO SCAN"
        self.scan_progress = ""
        App.get_running_app().navigate("dashboard", direction="right")
