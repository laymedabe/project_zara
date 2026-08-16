"""
Project Zara — Data Processor
===============================
Feature extraction and pre-processing for sensor readings.
Computes cumulative rainfall, soil moisture trends, slope movement rates,
and derived variables needed by the risk engine.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from database import db
from config import SENSOR_VALID_RANGES


async def extract_features(reading: dict) -> dict:
    """
    Extract all features needed by the risk engine from raw sensor data.

    Combines the current reading with historical data to compute:
    - Cumulative rainfall (1hr, 3hr, 24hr, 72hr)
    - Average soil moisture and saturation trends
    - Slope movement rate (change in tilt over time)
    - Pressure drop (storm indicator)
    - Rainfall intensity (mm/hr current)

    Returns a feature dict ready for risk_engine.assess().
    """
    features = {}

    # --- Current sensor values ---
    features["soil_moisture_1"] = reading.get("soil_moisture_1", 0)
    features["soil_moisture_2"] = reading.get("soil_moisture_2", 0)
    features["soil_moisture_3"] = reading.get("soil_moisture_3", 0)
    features["tilt_x"] = reading.get("tilt_x", 0)
    features["tilt_y"] = reading.get("tilt_y", 0)
    features["temperature"] = reading.get("temperature", 0)
    features["humidity"] = reading.get("humidity", 0)
    features["pressure"] = reading.get("pressure", 0)
    features["rainfall"] = reading.get("rainfall", 0)

    # --- Cumulative rainfall ---
    features["rainfall_1hr"] = await db.get_rainfall_sum(hours=1)
    features["rainfall_3hr"] = await db.get_rainfall_sum(hours=3)
    features["rainfall_24hr"] = await db.get_rainfall_sum(hours=24)
    features["rainfall_72hr"] = await db.get_rainfall_sum(hours=72)

    # Add current reading to cumulative (it may not be in DB yet)
    current_rain = reading.get("rainfall", 0)
    features["rainfall_1hr"] += current_rain
    features["rainfall_3hr"] += current_rain
    features["rainfall_24hr"] += current_rain
    features["rainfall_72hr"] += current_rain

    # --- Rainfall intensity (mm/hr based on current interval) ---
    features["rainfall_intensity"] = current_rain * 12  # Assuming 5-min intervals

    # --- Soil moisture average and trend ---
    sm_avg = (features["soil_moisture_1"] +
              features["soil_moisture_2"] +
              features["soil_moisture_3"]) / 3.0
    features["soil_moisture_avg"] = sm_avg

    # Compute soil moisture trend (compare with readings from 1 hour ago)
    past_readings = await db.get_readings(hours=1, limit=12)
    if len(past_readings) >= 2:
        oldest = past_readings[-1]
        oldest_avg = (
            (oldest.get("soil_moisture_1", 0) or 0) +
            (oldest.get("soil_moisture_2", 0) or 0) +
            (oldest.get("soil_moisture_3", 0) or 0)
        ) / 3.0
        features["soil_moisture_trend"] = sm_avg - oldest_avg  # Positive = increasing
    else:
        features["soil_moisture_trend"] = 0.0

    # --- Slope movement (change in tilt) ---
    features["tilt_magnitude"] = (features["tilt_x"]**2 + features["tilt_y"]**2) ** 0.5

    if len(past_readings) >= 2:
        oldest = past_readings[-1]
        old_tilt_x = oldest.get("tilt_x", 0) or 0
        old_tilt_y = oldest.get("tilt_y", 0) or 0
        tilt_change_x = features["tilt_x"] - old_tilt_x
        tilt_change_y = features["tilt_y"] - old_tilt_y
        features["tilt_rate"] = (tilt_change_x**2 + tilt_change_y**2) ** 0.5
    else:
        features["tilt_rate"] = 0.0

    # --- Pressure change (storm detection) ---
    three_hr_readings = await db.get_readings(hours=3, limit=36)
    if len(three_hr_readings) >= 2:
        oldest_pressure = three_hr_readings[-1].get("pressure", 0) or 0
        if oldest_pressure > 0:
            features["pressure_drop_3hr"] = oldest_pressure - features["pressure"]
        else:
            features["pressure_drop_3hr"] = 0.0
    else:
        features["pressure_drop_3hr"] = 0.0

    return features


def validate_reading(reading: dict) -> tuple[bool, list[str]]:
    """
    Validate a sensor reading against expected ranges.

    Returns:
        (is_valid, list_of_issues)
    """
    issues = []

    for field, (low, high) in SENSOR_VALID_RANGES.items():
        value = reading.get(field)
        if value is not None:
            if not (low <= value <= high):
                issues.append(
                    f"{field}={value:.2f} out of range [{low}, {high}]"
                )

    return (len(issues) == 0, issues)
