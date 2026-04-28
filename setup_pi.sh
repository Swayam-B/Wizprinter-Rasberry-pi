#!/bin/bash
# setup_pi.sh - Configures a fresh Pi for WizPrinter

echo "--- Phase 1: System Dependencies ---"
sudo apt-get update
# Added libmupdf-dev and swig for PDF rendering support
sudo apt-get install -y libcups2-dev cups sane sane-utils libsane-dev hplip libjpeg-dev zlib1g-dev \
     libcamera-apps libmupdf-dev swig

echo "--- Phase 2: User Permissions ---"
sudo usermod -a -G lpadmin $USER

echo "--- Phase 3: Services ---"
sudo systemctl enable cups
sudo systemctl start cups

echo "--- Phase 4: Python Environment ---"
if [ ! -d "env" ]; then
    python3 -m venv env
fi

./env/bin/pip install --upgrade pip
# Ensure pymupdf is in requirements.txt or installed here
./env/bin/pip install pymupdf
./env/bin/pip install -r requirements.txt

echo "Setup complete. YOU MUST REBOOT for group changes to take effect."