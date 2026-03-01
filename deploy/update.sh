#!/bin/bash
set -e

echo "Starting GPIO-UA Update..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo ./update.sh)"
  exit 1
fi

INSTALL_DIR="/opt/gpio-ua"

if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Pulling latest changes from git..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    echo "Warning: $INSTALL_DIR is not a git repository."
    echo "Cannot auto-update via git pull. Please overwrite files manually."
    exit 1
fi

echo "Updating Python dependencies..."
./venv/bin/pip install -r requirements.txt

echo "Restarting service..."
systemctl daemon-reload
systemctl restart gpio-ua.service

echo "Update Complete!"
