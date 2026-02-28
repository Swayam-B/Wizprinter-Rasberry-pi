# WizPrinter - Raspberry Pi Kiosk

Self-service printing kiosk application built with **Python + Kivy** for a Raspberry Pi with a 3.5" touchscreen (480×320).

## Features

- **Grade** – Scan and AI-grade student documents
- **Scan** – Scan documents and upload to your web backend
- **Classes** – Select semester, subject, and class for document routing
- **Print** – Preview and print documents from USB or cloud
- **Settings** – WiFi, time/region config, and user logout

## Project Structure

```
├── main.py                  # Entry point
├── requirements.txt         # Python dependencies
├── wizprinter/
│   ├── app.py               # Kivy App + ScreenManager
│   ├── theme.py             # Colors, sizes, constants
│   ├── screens/             # Screen logic (Python)
│   │   ├── landing.py       # Tap to Start
│   │   ├── wifi.py          # WiFi selection
│   │   ├── login.py         # User authentication
│   │   ├── dashboard.py     # 2×2 action grid
│   │   ├── classes.py       # Semester/Subject/Class pickers
│   │   ├── documents.py     # Document file list
│   │   ├── preview.py       # Doc preview + Delete/Grade/Print
│   │   ├── grade.py         # Grade document split view
│   │   ├── scan.py          # Scan & upload split view
│   │   └── settings.py      # System settings + logout
│   └── widgets/             # Reusable components
│       ├── statusbar.py     # Top status bar
│       └── bottomnav.py     # Bottom navigation tabs
├── kv/                      # Kivy Layout files (UI)
│   ├── theme.kv
│   ├── widgets.kv
│   ├── landing.kv
│   ├── wifi.kv
│   ├── login.kv
│   ├── dashboard.kv
│   ├── classes.kv
│   ├── documents.kv
│   ├── preview.kv
│   ├── grade.kv
│   ├── scan.kv
│   └── settings.kv
├── design/                  # HTML mockups from Stitch
└── docs/                    # Setup guides
    └── pi-setup.md
```

## Quick Start (Desktop Dev)

```bash
# Clone
git clone https://github.com/Swayam-B/Wizprinter-Rasberry-pi.git
cd Wizprinter-Rasberry-pi

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

## Raspberry Pi Setup

See [docs/pi-setup.md](docs/pi-setup.md) for full instructions. Quick version:

```bash
# On Raspberry Pi (Raspberry Pi OS)
sudo apt update && sudo apt install -y python3-pip python3-kivy

# Clone and run
git clone https://github.com/Swayam-B/Wizprinter-Rasberry-pi.git
cd Wizprinter-Rasberry-pi
pip install -r requirements.txt
python3 main.py
```

## Screen Flow

```
Landing → WiFi → Login → Dashboard
                            ├── Grade → Preview → (Success) → Dashboard
                            ├── Scan  → Upload  → Dashboard
                            ├── Classes → Documents → Preview
                            └── Settings → (Logout) → Landing
```

## Connecting to Your Web Backend

The screens include TODO placeholders for API integration. Key integration points:

| Screen | Method | Purpose |
|--------|--------|---------|
| `login.py` | `attempt_login()` | Authenticate against your web API |
| `grade.py` | `grade_now()` | Submit document for AI grading |
| `scan.py` | `upload()` | Upload scanned document |
| `documents.py` | `on_enter()` | Fetch document list from API |

## Hardware

- Raspberry Pi 3B+ / 4 / 5
- 3.5" SPI/GPIO touchscreen (480×320, resistive)
- USB scanner (optional)
- Thermal/inkjet printer (optional)

## License

MIT License – see [LICENSE](LICENSE)
