# Project Zara 🏔️

**Smart IoT-Based Landslide Early Warning System**  
*Using Localized Rainfall Thresholds for Leon, Iloilo*

---

## Overview

Project Zara is an integrated IoT system that monitors environmental conditions on landslide-prone slopes and provides real-time risk assessment through a web dashboard. The system operates fully offline at the base station (Barangay Hall).

### Architecture

```
[Mountain/Slope]                        [Base Station / Barangay Hall]
┌──────────────────┐     LoRa 433MHz    ┌────────────────────────────┐
│  Arduino Uno R3  │ ─────2-5km──────▶  │     Raspberry Pi 5         │
│  • Soil Moisture │                    │  • LoRa Receiver (SX1278)  │
│  • Rain Gauge    │                    │  • SQLite Database         │
│  • MPU6050 Tilt  │                    │  • Risk Assessment Engine  │
│  • BME280 Temp   │                    │  • Web Dashboard           │
│  • LoRa TX       │                    │  • Alert System            │
└──────────────────┘                    └────────────────────────────┘
```

## Quick Start (Development on PC)

### 1. Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Run in Simulator Mode

```bash
python main.py
```

This starts the system with simulated sensor data (no hardware needed).

### 3. Open Dashboard

Navigate to **http://localhost:8000** in your browser.

The simulator cycles through scenarios: Normal → Light Rain → Heavy Rain → Typhoon.

## Deployment on Raspberry Pi 5

### 1. Run Setup Script

```bash
cd scripts
chmod +x setup_pi.sh
sudo ./setup_pi.sh
```

### 2. Start the Service

```bash
# Set to live LoRa mode
export ZARA_MODE=live

# Or use systemd (auto-start on boot)
sudo systemctl start zara.service
```

### 3. Access Dashboard

Open a browser on any device on the same network:
```
http://<raspberry-pi-ip>:8000
```

## Risk Level Classification

| Level | Score Range | Color | Action |
|-------|-----------|-------|--------|
| 🟢 SAFE | 0–30% | Green | Normal monitoring |
| 🟡 CAUTION | 31–60% | Amber | Heightened monitoring |
| 🟠 WARNING | 61–90% | Orange | Prepare for evacuation |
| 🔴 DANGER | 91–100% | Red | EVACUATE IMMEDIATELY |

## Configuration

All thresholds and settings are in `backend/config.py`:
- Rainfall thresholds (1hr, 3hr, 24hr, 72hr)
- Soil moisture thresholds per depth
- Tilt/slope movement thresholds
- Risk weight factors
- LoRa configuration

## Project Structure

```
project_zara/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # All configuration & thresholds
│   ├── database.py          # SQLite database
│   ├── lora_receiver.py     # SX1278 LoRa hardware driver
│   ├── lora_simulator.py    # Simulated sensor data
│   ├── risk_engine.py       # Threshold-based risk assessment
│   ├── data_processor.py    # Feature extraction
│   ├── alert_manager.py     # Alert generation
│   ├── websocket_manager.py # Real-time WebSocket
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── index.html           # Dashboard page
│   ├── css/styles.css       # Dark-mode styles
│   └── js/                  # Dashboard JavaScript
├── data/                    # SQLite database (auto-created)
├── scripts/
│   ├── setup_pi.sh          # Pi setup script
│   └── zara.service         # systemd service
└── README.md
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Dashboard UI |
| WS | `/ws` | WebSocket for real-time data |
| GET | `/api/dashboard` | Full dashboard data |
| GET | `/api/readings?hours=24` | Sensor readings |
| GET | `/api/assessments?hours=24` | Risk assessments |
| GET | `/api/rainfall` | Cumulative rainfall |
| GET | `/api/alerts` | Alert history |
| POST | `/api/alerts/{id}/acknowledge` | Acknowledge alert |
| GET | `/api/system/stats` | System statistics |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ZARA_MODE` | `simulator` | `simulator` or `live` |

---

*Project Zara — Protecting lives in Leon, Iloilo through early warning technology.*
