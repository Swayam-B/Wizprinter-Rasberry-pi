#!/bin/bash
# setup_pi.sh - Configures a fresh Pi for WizPrinter

echo "--- Phase 1: System Dependencies ---"
sudo apt-get update
# libcups2-dev is REQUIRED for pycups to compile
sudo apt-get install -y libcups2-dev cups hplip libjpeg-dev zlib1g-dev libcamera-apps

echo "--- Phase 2: User Permissions ---"
# Adds current user to the printer admin group
sudo usermod -a -G lpadmin $USER

echo "--- Phase 3: Services ---"
sudo systemctl enable cups
sudo systemctl start cups

echo "--- Phase 4: Python Environment ---"
# Check if env exists, if not create it
if [ ! -d "env" ]; then
    python3 -m venv env
fi

# Use the absolute path to pip to ensure it hits the virtual environment
./env/bin/pip install --upgrade pip
./env/bin/pip install -r requirements.txt

echo "Setup complete. YOU MUST REBOOT for group changes to take effect."