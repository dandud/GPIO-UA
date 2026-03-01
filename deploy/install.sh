#!/bin/bash
set -e

echo "Starting GPIO-UA Installation..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo ./install.sh)"
  exit 1
fi

INSTALL_DIR="/opt/gpio-ua"
SERVICE_FILE="/etc/systemd/system/gpio-ua.service"

echo "Installing system dependencies..."
apt-get update
apt-get install -y python3 python3-venv python3-pip git

echo "Cloning or setting up directory at $INSTALL_DIR..."
# If deploying from local, we assume the user copied the files, but typically this clones from git
# For now, we will just copy current directory to /opt/gpio-ua if not already there
if [ "$PWD" != "$INSTALL_DIR" ]; then
    mkdir -p "$INSTALL_DIR"
    cp -r * "$INSTALL_DIR/"
fi

cd "$INSTALL_DIR"

echo "Setting up Python Virtual Environment..."
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

echo "Installing systemd service..."
cp deploy/gpio-ua.service "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable gpio-ua.service
systemctl restart gpio-ua.service

echo "Installation Complete!"
echo "GPIO-UA is now running as a background service."
echo "Access the web console at http://<ip_address>:8080"
