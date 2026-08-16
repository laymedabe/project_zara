"""
Project Zara — Risk Assessment Engine
=======================================
Threshold-based risk classification for landslide early warning.
Computes a composite risk score from sensor features and classifies
into SAFE / CAUTION / WARNING / DANGER levels.

Based on PAGASA rainfall thresholds adapted for Leon, Iloilo,
combined with soil moisture, slope movement, and environmental factors.
"""

from config import (
    RiskLevel, RISK_THRESHOLDS, RISK_WEIGHTS,
    RAINFALL_THRESHOLDS, SOIL_MOISTURE_THRESHOLDS,
    TILT_THRESHOLDS, HUMIDITY_THRESHOLD_HIGH, PRESSURE_DROP_THRESHOLD,
)


def _score_rainfall(features: dict) -> tuple[float, dict]:
    """
    Score rainfall danger from 0–100 based on cumulative thresholds.
    Uses the worst (highest) score across all time windows.
    """
    details = {}
    max_score = 0.0

    for window in ["1hr", "3hr", "24hr", "72hr"]:
        value = features.get(f"rainfall_{window}", 0)
        thresholds = RAINFALL_THRESHOLDS[window]

        if value >= thresholds["danger"]:
            score = 100.0
        elif value >= thresholds["warning"]:
            # Interpolate between 61-90
            ratio = (value - thresholds["warning"]) / (thresholds["danger"] - thresholds["warning"])
            score = 61 + ratio * 29
        elif value >= thresholds["caution"]:
            # Interpolate between 31-60
            ratio = (value - thresholds["caution"]) / (thresholds["warning"] - thresholds["caution"])
            score = 31 + ratio * 29
        else:
            # Below caution — interpolate 0-30
            if thresholds["caution"] > 0:
                ratio = value / thresholds["caution"]
            else:
                ratio = 0
            score = ratio * 30

        details[f"rainfall_{window}"] = {
            "value_mm": round(value, 2),
            "score": round(score, 1),
        }
        max_score = max(max_score, score)

    # Bonus: rainfall intensity factor
    intensity = features.get("rainfall_intensity", 0)
    if intensity > 20:  # Very heavy rain
        intensity_bonus = min(10, (intensity - 20) * 0.5)
        max_score = min(100, max_score + intensity_bonus)
        details["intensity_bonus"] = round(intensity_bonus, 1)

    return round(max_score, 1), details


def _score_soil_moisture(features: dict) -> tuple[float, dict]:
    """
    Score soil moisture danger from 0–100.
    Uses weighted average across 3 depths (shallow weighted more).
    """
    details = {}
    depth_weights = [0.45, 0.35, 0.20]  # Shallow most important
    weighted_score = 0.0

    for i, depth_key in enumerate(["depth_1", "depth_2", "depth_3"]):
        field = f"soil_moisture_{i + 1}"
        value = features.get(field, 0)
        thresholds = SOIL_MOISTURE_THRESHOLDS[depth_key]

        if value >= thresholds["danger"]:
            score = 100.0
        elif value >= thresholds["warning"]:
            ratio = (value - thresholds["warning"]) / (thresholds["danger"] - thresholds["warning"])
            score = 61 + ratio * 39
        elif value >= thresholds["caution"]:
            ratio = (value - thresholds["caution"]) / (thresholds["warning"] - thresholds["caution"])
            score = 31 + ratio * 30
        else:
            if thresholds["caution"] > 0:
                ratio = value / thresholds["caution"]
            else:
                ratio = 0
            score = ratio * 30

        details[depth_key] = {
            "value_pct": round(value, 1),
            "score": round(score, 1),
        }
        weighted_score += score * depth_weights[i]

    # Trend bonus: rapidly increasing moisture is more dangerous
    trend = features.get("soil_moisture_trend", 0)
    if trend > 5:  # Increasing by 5% or more in last hour
        trend_bonus = min(10, trend * 1.0)
        weighted_score = min(100, weighted_score + trend_bonus)
        details["trend_bonus"] = round(trend_bonus, 1)

    return round(weighted_score, 1), details


def _score_slope_movement(features: dict) -> tuple[float, dict]:
    """
    Score slope movement danger from 0–100 based on tilt magnitude and rate.
    """
    tilt_mag = features.get("tilt_magnitude", 0)
    tilt_rate = features.get("tilt_rate", 0)

    # Score based on absolute tilt magnitude
    if tilt_mag >= TILT_THRESHOLDS["danger"]:
        mag_score = 100.0
    elif tilt_mag >= TILT_THRESHOLDS["warning"]:
        ratio = (tilt_mag - TILT_THRESHOLDS["warning"]) / (TILT_THRESHOLDS["danger"] - TILT_THRESHOLDS["warning"])
        mag_score = 61 + ratio * 39
    elif tilt_mag >= TILT_THRESHOLDS["caution"]:
        ratio = (tilt_mag - TILT_THRESHOLDS["caution"]) / (TILT_THRESHOLDS["warning"] - TILT_THRESHOLDS["caution"])
        mag_score = 31 + ratio * 30
    else:
        if TILT_THRESHOLDS["caution"] > 0:
            ratio = tilt_mag / TILT_THRESHOLDS["caution"]
        else:
            ratio = 0
        mag_score = ratio * 30

    # Rate of change bonus (rapid movement is more dangerous)
    rate_bonus = min(15, tilt_rate * 5.0)

    total = min(100, mag_score + rate_bonus)

    details = {
        "tilt_magnitude_deg": round(tilt_mag, 2),
        "tilt_rate_deg_per_interval": round(tilt_rate, 2),
        "magnitude_score": round(mag_score, 1),
        "rate_bonus": round(rate_bonus, 1),
    }

    return round(total, 1), details


def _score_environmental(features: dict) -> tuple[float, dict]:
    """
    Score environmental conditions from 0–100.
    High humidity + rapid pressure drop = approaching storm.
    """
    humidity = features.get("humidity", 0)
    pressure_drop = features.get("pressure_drop_3hr", 0)

    # Humidity score
    if humidity >= 95:
        humidity_score = 80
    elif humidity >= HUMIDITY_THRESHOLD_HIGH:
        ratio = (humidity - HUMIDITY_THRESHOLD_HIGH) / (95 - HUMIDITY_THRESHOLD_HIGH)
        humidity_score = 40 + ratio * 40
    elif humidity >= 70:
        ratio = (humidity - 70) / (HUMIDITY_THRESHOLD_HIGH - 70)
        humidity_score = ratio * 40
    else:
        humidity_score = 0

    # Pressure drop score (rapid drop = storm approaching)
    if pressure_drop >= PRESSURE_DROP_THRESHOLD * 2:
        pressure_score = 100
    elif pressure_drop >= PRESSURE_DROP_THRESHOLD:
        ratio = (pressure_drop - PRESSURE_DROP_THRESHOLD) / PRESSURE_DROP_THRESHOLD
        pressure_score = 50 + ratio * 50
    elif pressure_drop > 0:
        ratio = pressure_drop / PRESSURE_DROP_THRESHOLD
        pressure_score = ratio * 50
    else:
        pressure_score = 0

    # Weighted combination
    total = humidity_score * 0.5 + pressure_score * 0.5

    details = {
        "humidity_pct": round(humidity, 1),
        "humidity_score": round(humidity_score, 1),
        "pressure_drop_hpa": round(pressure_drop, 2),
        "pressure_score": round(pressure_score, 1),
    }

    return round(total, 1), details


def classify_risk_level(score: float) -> RiskLevel:
    """Classify composite score into a risk level."""
    for level, (low, high) in RISK_THRESHOLDS.items():
        if low <= score <= high:
            return level
    # Fallback
    if score > 90:
        return RiskLevel.DANGER
    return RiskLevel.SAFE


def assess(features: dict) -> dict:
    """
    Perform full risk assessment on extracted features.

    Returns a dict with:
    - risk_level: SAFE / CAUTION / WARNING / DANGER
    - composite_score: 0–100
    - Individual component scores
    - Detailed breakdown
    """
    # Score each component
    rainfall_score, rainfall_details = _score_rainfall(features)
    soil_score, soil_details = _score_soil_moisture(features)
    slope_score, slope_details = _score_slope_movement(features)
    env_score, env_details = _score_environmental(features)

    # Compute weighted composite score
    composite = (
        rainfall_score * RISK_WEIGHTS["rainfall"] +
        soil_score * RISK_WEIGHTS["soil_moisture"] +
        slope_score * RISK_WEIGHTS["slope_movement"] +
        env_score * RISK_WEIGHTS["environmental"]
    )

    # Apply critical override: if ANY single component is at DANGER level,
    # ensure composite is at least WARNING (61)
    if any(s >= 91 for s in [rainfall_score, soil_score, slope_score]):
        composite = max(composite, 61)

    # If BOTH rainfall and soil moisture are DANGER, force composite to DANGER
    if rainfall_score >= 91 and soil_score >= 91:
        composite = max(composite, 91)

    composite = min(100, round(composite, 1))
    risk_level = classify_risk_level(composite)

    return {
        "risk_level": risk_level.value,
        "composite_score": composite,
        "rainfall_score": rainfall_score,
        "soil_moisture_score": soil_score,
        "slope_movement_score": slope_score,
        "environmental_score": env_score,
        "rainfall_1hr": features.get("rainfall_1hr", 0),
        "rainfall_3hr": features.get("rainfall_3hr", 0),
        "rainfall_24hr": features.get("rainfall_24hr", 0),
        "rainfall_72hr": features.get("rainfall_72hr", 0),
        "details": {
            "rainfall": rainfall_details,
            "soil_moisture": soil_details,
            "slope_movement": slope_details,
            "environmental": env_details,
            "weights": RISK_WEIGHTS,
        },
    }
