# Raspberry Pi Setup Guide

## Prerequisites

- Raspberry Pi 3B+, 4, or 5
- 3.5" SPI touchscreen (480×320)
- Raspberry Pi OS (Bookworm or later)
- microSD card (16GB+)

## 1. Install Raspberry Pi OS

Flash Raspberry Pi OS using [Raspberry Pi Imager](https://www.raspberrypi.com/software/).

## 2. Configure the Touchscreen

For most 3.5" SPI displays (e.g., Waveshare, Elecrow):

```bash
# Install display drivers (varies by manufacturer)
# Example for Waveshare 3.5" (A):
git clone https://github.com/waveshare/LCD-show.git
cd LCD-show
chmod +x LCD35-show
./LCD35-show
```

The Pi will reboot with the display active.

## 3. Install Dependencies

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv libsdl2-dev libsdl2-image-dev \
    libsdl2-mixer-dev libsdl2-ttf-dev libgstreamer1.0-dev

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Kivy
pip install kivy[full] pillow requests
```

## 4. Clone and Run

```bash
git clone https://github.com/Swayam-B/Wizprinter-Rasberry-pi.git
cd Wizprinter-Rasberry-pi
python3 main.py
```

## 5. Auto-Start on Boot (Kiosk Mode)

Create a systemd service:

```bash
sudo nano /etc/systemd/system/wizprinter.service
```

Paste:

```ini
[Unit]
Description=WizPrinter Kiosk
After=graphical.target

[Service]
User=pi
Environment=DISPLAY=:0
WorkingDirectory=/home/pi/Wizprinter-Rasberry-pi
ExecStart=/home/pi/Wizprinter-Rasberry-pi/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
```

Enable:

```bash
sudo systemctl enable wizprinter
sudo systemctl start wizprinter
```

## 6. Fullscreen Mode

In `main.py`, change:
```python
Config.set('graphics', 'fullscreen', '1')  # Enable fullscreen
```

## 7. Touchscreen Calibration

If touch input is misaligned:

```bash
sudo apt install xinput-calibrator
DISPLAY=:0 xinput_calibrator
```

Copy the output calibration data to `/etc/X11/xorg.conf.d/99-calibration.conf`.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Black screen | Check SPI enabled in `raspi-config` |
| Touch not working | Verify `/dev/input/event*` exists |
| Kivy crash | Install SDL2 deps: `sudo apt install libsdl2*` |
| Wrong orientation | Edit `/boot/config.txt`: `display_rotate=1` |
