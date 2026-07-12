#!/usr/bin/env bash
# setup_pi.sh — configure a fresh Raspberry Pi for WizPrinter
# Usage: bash setup_pi.sh [--user <username>]
set -euo pipefail

# ── Configurable system user (default: pi, override with --user) ──────────────
SYS_USER="${SUDO_USER:-${USER:-pi}}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --user) SYS_USER="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# Abort if not running as root (sudo)
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: Run this script with sudo: sudo bash setup_pi.sh" >&2
    exit 1
fi

echo "=== WizPrinter Pi Setup (user: $SYS_USER) ==="

# ── Phase 1: System packages ──────────────────────────────────────────────────
echo "--- Phase 1: System packages ---"
apt-get update -qq
apt-get install -y --no-install-recommends \
    libcups2-dev \
    cups \
    sane \
    sane-utils \
    libsane-dev \
    hplip \
    libjpeg-dev \
    zlib1g-dev \
    libmupdf-dev \
    swig \
    espeak-ng \
    libttspico-utils \
    alsa-utils \
    pulseaudio-utils \
    python3-venv \
    git

# ── Phase 2: User permissions ─────────────────────────────────────────────────
echo "--- Phase 2: User permissions ---"
if id "$SYS_USER" &>/dev/null; then
    usermod -aG lpadmin,scanner "$SYS_USER"
    echo "Added $SYS_USER to lpadmin + scanner groups"
else
    echo "WARNING: User '$SYS_USER' not found — skipping group assignment" >&2
fi

# ── Phase 3: Services ──────────────────────────────────────────────────────────
echo "--- Phase 3: Services ---"
systemctl enable cups
systemctl start  cups

# ── Phase 4: NTP (setup concern, not a runtime feature) ──────────────────────
echo "--- Phase 4: NTP sync ---"
if command -v timedatectl &>/dev/null; then
    timedatectl set-ntp true && echo "NTP enabled via timedatectl"
elif apt-get install -y --no-install-recommends chrony &>/dev/null; then
    systemctl enable --now chrony && echo "chrony installed and started"
else
    echo "WARNING: Could not enable NTP — time may drift" >&2
fi

# ── Phase 5: Python environment ────────────────────────────────────────────────
echo "--- Phase 5: Python environment ---"

# Run as the target user so the venv is owned correctly
sudo -u "$SYS_USER" bash -c '
    set -euo pipefail
    cd "$(dirname "$(realpath "$0")")"     2>/dev/null || cd "$HOME"
    
    if [ ! -d env ]; then
        python3 -m venv env
        echo "Created virtual environment: env/"
    fi

    env/bin/pip install --upgrade pip --quiet
    env/bin/pip install -r requirements.txt --quiet
    echo "Python dependencies installed."
'

# ── Phase 5b: Piper neural TTS voice (accessibility) ──────────────────────────
# Recommended, natural-sounding offline voice. Best-effort: a failure here must
# not abort provisioning — the app falls back to Pico/espeak automatically.
echo "--- Phase 5b: Piper TTS voice ---"
sudo -u "$SYS_USER" bash -c '
    set -uo pipefail
    cd "$(dirname "$(realpath "$0")")" 2>/dev/null || cd "$HOME"
    env/bin/pip install piper-tts --quiet || { echo "WARNING: piper-tts install failed; will fall back to Pico/espeak" >&2; exit 0; }

    mkdir -p voices
    base="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium"
    for f in en_US-amy-medium.onnx en_US-amy-medium.onnx.json; do
        if [ ! -f "voices/$f" ]; then
            echo "Downloading Piper voice: $f"
            curl -fsSL "$base/$f?download=true" -o "voices/$f" \
                || { echo "WARNING: could not download $f; falling back to Pico/espeak" >&2; rm -f "voices/$f"; }
        fi
    done
' || true

# ── Phase 6: Verify critical tools ────────────────────────────────────────────
echo "--- Phase 6: Verification ---"
MISSING=()
for cmd in scanimage espeak-ng cupsd python3; do
    command -v "$cmd" &>/dev/null || MISSING+=("$cmd")
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "WARNING: The following tools were not found after setup: ${MISSING[*]}" >&2
else
    echo "All critical tools verified ✓"
fi

echo ""
echo "=== Setup complete ==="
echo "YOU MUST REBOOT for group changes to take effect."
echo "After reboot, copy .env.example to .env and fill in your secrets."