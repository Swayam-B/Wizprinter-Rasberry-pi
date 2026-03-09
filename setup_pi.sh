#!/bin/bash
# setup_pi.sh - Configures a fresh Pi for WizPrinter

echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y libcups2-dev cups hplip # hplip adds common driver support

echo "Configuring user permissions..."
sudo usermod -a -G lpadmin $USER

echo "Enabling CUPS service..."
sudo systemctl enable cups
sudo systemctl start cups

echo "Installing Python requirements..."
source env/bin/activate
pip install -r requirements.txt

echo "Setup complete. Please reboot for group changes to take effect."