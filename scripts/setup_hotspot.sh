#!/bin/bash

# Project Iraya — Offline Wi-Fi Hotspot Setup
# This script configures the Raspberry Pi's NetworkManager to broadcast 
# its own Wi-Fi network so phones can connect without internet.

echo "==============================================="
echo "  PROJECT IRAYA - WI-FI HOTSPOT SETUP"
echo "==============================================="

# Ensure running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run this script with sudo:"
  echo "sudo bash setup_hotspot.sh"
  exit
fi

SSID="Iraya_BaseStation"
PASSWORD="iraya1234"
IP="192.168.4.1/24"

echo "[1/4] Checking NetworkManager..."
if ! command -v nmcli &> /dev/null; then
    echo "ERROR: nmcli not found. This script requires Raspberry Pi OS Bookworm or later."
    exit 1
fi

echo "[2/4] Removing existing hotspot configurations..."
nmcli con delete "$SSID" 2>/dev/null || true

echo "[3/4] Creating Wi-Fi Access Point..."
# Create the connection
nmcli con add type wifi ifname wlan0 mode ap con-name "$SSID" ssid "$SSID"

# Set frequency band and channel (2.4GHz, channel 6 is most compatible)
nmcli con modify "$SSID" 802-11-wireless.band bg
nmcli con modify "$SSID" 802-11-wireless.channel 6

# Set WPA2 Password
nmcli con modify "$SSID" 802-11-wireless-security.key-mgmt wpa-psk
nmcli con modify "$SSID" 802-11-wireless-security.psk "$PASSWORD"

# Set static IP and enable DHCP server (shared method)
nmcli con modify "$SSID" ipv4.method shared ipv4.address "$IP"

echo "[4/4] Starting the Wi-Fi Hotspot..."
nmcli con up "$SSID"

echo ""
echo "==============================================="
echo "  SUCCESS! HOTSPOT IS NOW RUNNING!"
echo "==============================================="
echo "Network Name (SSID) : $SSID"
echo "Password            : $PASSWORD"
echo "Dashboard URL       : http://192.168.4.1"
echo ""
echo "NOTE: If your SSH terminal freezes after this, it means you were"
echo "connected over Wi-Fi, and the Pi has successfully disconnected from"
echo "your router to broadcast its own network. Connect your laptop to"
echo "'$SSID' to regain access!"
echo "==============================================="
