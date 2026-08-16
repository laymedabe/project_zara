#!/bin/bash
# =============================================================================
# Project Zara — Raspberry Pi 5 Setup Script
# =============================================================================
# Run this script on your Raspberry Pi 5 to set up everything.
# Usage: chmod +x setup_pi.sh && sudo ./setup_pi.sh
# =============================================================================

set -e

echo "============================================"
echo "  PROJECT ZARA — Pi 5 Setup"
echo "============================================"
echo ""

# --- Enable SPI ---
echo "[1/5] Enabling SPI interface..."
if ! grep -q "^dtparam=spi=on" /boot/firmware/config.txt 2>/dev/null; then
    echo "dtparam=spi=on" | sudo tee -a /boot/firmware/config.txt
    echo "  SPI enabled. Reboot required after setup."
else
    echo "  SPI already enabled."
fi

# --- Install system dependencies ---
echo "[2/5] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv python3-dev

# --- Create Python virtual environment ---
echo "[3/5] Setting up Python virtual environment..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r "$PROJECT_DIR/backend/requirements.txt"

# Install Pi-specific libraries
pip install spidev RPi.GPIO

# --- Create data directory ---
echo "[4/5] Creating data directory..."
mkdir -p "$PROJECT_DIR/data"

# --- Install systemd service ---
echo "[5/5] Installing systemd service..."
sudo cp "$SCRIPT_DIR/zara.service" /etc/systemd/system/zara.service

# Update paths in service file
sudo sed -i "s|/home/pi/project_zara|$PROJECT_DIR|g" /etc/systemd/system/zara.service

sudo systemctl daemon-reload
sudo systemctl enable zara.service

echo ""
echo "============================================"
echo "  SETUP COMPLETE"
echo "============================================"
echo ""
echo "  To start Project Zara:"
echo "    sudo systemctl start zara.service"
echo ""
echo "  To view logs:"
echo "    sudo journalctl -u zara.service -f"
echo ""
echo "  Dashboard will be available at:"
echo "    http://<pi-ip-address>:8000"
echo ""
echo "  NOTE: If SPI was just enabled, please reboot first:"
echo "    sudo reboot"
echo ""
