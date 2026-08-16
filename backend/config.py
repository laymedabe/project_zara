"""
Project Zara — System Configuration & Thresholds
=================================================
All configurable parameters for the Landslide Early Warning System.
Thresholds are based on PAGASA standards adapted for Leon, Iloilo.
"""

from enum import Enum
from pathlib import Path

# =============================================================================
# PATHS
# =============================================================================
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR / "frontend"
DB_PATH = DATA_DIR / "zara.db"

# =============================================================================
# SERVER
# =============================================================================
HOST = "0.0.0.0"
PORT = 8000
DEBUG = True

# =============================================================================
# LORA CONFIGURATION
# =============================================================================
LORA_FREQUENCY = 433E6          # 433 MHz (common for Philippines)
LORA_SPREADING_FACTOR = 7       # SF7 — good balance of range and speed
LORA_BANDWIDTH = 125E3          # 125 kHz
LORA_CODING_RATE = 5            # 4/5
LORA_TX_POWER = 17              # dBm

# SPI Pins (Raspberry Pi 5 GPIO)
LORA_SPI_BUS = 0
LORA_SPI_CS = 0                 # CE0 — Pin 24 (GPIO 8)
LORA_RST_PIN = 25               # Pin 22 (GPIO 25)
LORA_DIO0_PIN = 4               # Pin 7 (GPIO 4)

# =============================================================================
# DATA COLLECTION
# =============================================================================
SENSOR_INTERVAL_SECONDS = 300   # 5 minutes (matches flowchart)
DATA_RETENTION_DAYS = 90        # Keep 3 months of data
SIMULATOR_INTERVAL_SECONDS = 5  # Faster interval for testing with simulator

# =============================================================================
# RISK LEVELS
# =============================================================================
class RiskLevel(str, Enum):
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    WARNING = "WARNING"
    DANGER = "DANGER"

# Risk level thresholds (composite score percentage)
RISK_THRESHOLDS = {
    RiskLevel.SAFE: (0, 30),
    RiskLevel.CAUTION: (31, 60),
    RiskLevel.WARNING: (61, 90),
    RiskLevel.DANGER: (91, 100),
}

# Risk level colors for frontend
RISK_COLORS = {
    RiskLevel.SAFE: "#10b981",
    RiskLevel.CAUTION: "#f59e0b",
    RiskLevel.WARNING: "#f97316",
    RiskLevel.DANGER: "#ef4444",
}

# =============================================================================
# RAINFALL THRESHOLDS (mm) — Based on PAGASA Rainfall Warning System
# Adapted for Leon, Iloilo using localized empirical data
# =============================================================================
RAINFALL_THRESHOLDS = {
    # (caution_mm, warning_mm, danger_mm)
    "1hr":  {"caution": 7.5,  "warning": 15.0,  "danger": 30.0},
    "3hr":  {"caution": 15.0, "warning": 30.0,  "danger": 65.0},
    "24hr": {"caution": 50.0, "warning": 100.0, "danger": 200.0},
    "72hr": {"caution": 100.0, "warning": 200.0, "danger": 350.0},
}

# =============================================================================
# SOIL MOISTURE THRESHOLDS (%) — Per Depth
# Based on typical clay-loam soils in Leon, Iloilo slopes
# =============================================================================
SOIL_MOISTURE_THRESHOLDS = {
    "depth_1": {"caution": 60, "warning": 75, "danger": 85},  # Shallow (~15cm)
    "depth_2": {"caution": 55, "warning": 70, "danger": 82},  # Mid (~30cm)
    "depth_3": {"caution": 50, "warning": 65, "danger": 80},  # Deep (~60cm)
}

# =============================================================================
# SLOPE MOVEMENT THRESHOLDS (degrees) — From MPU6050
# =============================================================================
TILT_THRESHOLDS = {
    "caution": 2.0,   # degrees change from baseline
    "warning": 5.0,
    "danger": 10.0,
}

# =============================================================================
# ENVIRONMENTAL THRESHOLDS
# =============================================================================
HUMIDITY_THRESHOLD_HIGH = 90      # % — saturated air indicates heavy rain
PRESSURE_DROP_THRESHOLD = 3.0    # hPa drop in 3 hours — approaching storm

# =============================================================================
# RISK WEIGHT FACTORS
# Weights for computing composite risk score (must sum to 1.0)
# =============================================================================
RISK_WEIGHTS = {
    "rainfall": 0.35,        # Rainfall is primary trigger
    "soil_moisture": 0.30,   # Soil saturation is second
    "slope_movement": 0.20,  # Direct indicator of instability
    "environmental": 0.15,   # Supporting indicator (humidity + pressure)
}

# =============================================================================
# SENSOR VALUE RANGES (for validation / outlier detection)
# =============================================================================
SENSOR_VALID_RANGES = {
    "soil_moisture": (0, 100),       # %
    "temperature": (-10, 60),        # °C
    "humidity": (0, 100),            # %
    "pressure": (800, 1100),         # hPa
    "tilt_x": (-90, 90),            # degrees
    "tilt_y": (-90, 90),            # degrees
    "rainfall": (0, 500),           # mm (per reading interval)
}
