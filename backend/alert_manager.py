"""
Project Zara — Alert Manager
==============================
Generates and manages alerts based on risk assessment results.
Supports on-screen alerts (via WebSocket), GPIO alerts (LED/buzzer), and logging.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from config import RiskLevel
from database import db
from websocket_manager import ws_manager


class AlertManager:
    """Manages alert generation and dispatch based on risk level changes."""

    def __init__(self):
        self._previous_risk_level: Optional[RiskLevel] = RiskLevel.SAFE
        self._pending_risk_level: Optional[RiskLevel] = None
        self._consecutive_count = 0
        self._last_alert_time = datetime.min.replace(tzinfo=timezone.utc)
        self._gpio_available = False
        self._init_gpio()

    def _init_gpio(self):
        """Try to initialize GPIO for LED/buzzer alerts (only works on Pi)."""
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            # LED pins (optional — connect LEDs to these GPIO pins)
            self.LED_GREEN = 17   # Safe
            self.LED_YELLOW = 27  # Caution
            self.LED_ORANGE = 22  # Warning
            self.LED_RED = 23     # Danger
            self.BUZZER = 24      # Buzzer

            for pin in [self.LED_GREEN, self.LED_YELLOW, self.LED_ORANGE,
                        self.LED_RED, self.BUZZER]:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)

            self._gpio_available = True
            print("[ALERT] GPIO initialized -- LED and buzzer alerts enabled")
        except (ImportError, RuntimeError):
            self._gpio_available = False
            print("[ALERT] GPIO not available -- running in software-only mode")

    async def process_risk_assessment(self, assessment: dict):
        """Process a new risk assessment and generate alerts if needed."""
        current_level = RiskLevel(assessment["risk_level"])
        score = assessment["composite_score"]

        should_alert = False
        now = datetime.now(timezone.utc)

        # Risk level priority for quick comparison
        priority = {RiskLevel.SAFE: 0, RiskLevel.CAUTION: 1, RiskLevel.WARNING: 2, RiskLevel.DANGER: 3}

        if current_level != self._previous_risk_level:
            if current_level == self._pending_risk_level:
                self._consecutive_count += 1
            else:
                self._pending_risk_level = current_level
                self._consecutive_count = 1

            # Trigger alert immediately if risk is ESCALATING (priority goes up).
            # If risk is DE-ESCALATING, require 3 consecutive readings to prevent flapping.
            if priority[current_level] > priority[self._previous_risk_level]:
                should_alert = True
            elif self._consecutive_count >= 3:
                should_alert = True
        else:
            self._pending_risk_level = None
            self._consecutive_count = 0
            
            # If we are staying in WARNING or DANGER, repeat the alert every 5 minutes
            if current_level in (RiskLevel.WARNING, RiskLevel.DANGER):
                if (now - self._last_alert_time).total_seconds() >= 300:
                    should_alert = True

        if should_alert:
            message = self._build_alert_message(current_level, score, assessment)

            # Store alert in database
            alert_id = await db.insert_alert(
                risk_level=current_level.value,
                message=message,
                assessment_id=assessment.get("id"),
            )

            # Broadcast to dashboard via WebSocket
            await ws_manager.broadcast_alert({
                "id": alert_id,
                "risk_level": current_level.value,
                "composite_score": score,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Update GPIO LEDs
            self._update_gpio_leds(current_level)

            # Trigger buzzer for WARNING and DANGER
            if current_level in (RiskLevel.WARNING, RiskLevel.DANGER):
                self._trigger_buzzer(current_level)

            await db.log("WARNING" if current_level != RiskLevel.SAFE else "INFO",
                         "AlertManager",
                         f"Alert generated: {current_level.value} (score: {score:.1f}%)")
            
            self._last_alert_time = now
            self._previous_risk_level = current_level

    def _build_alert_message(self, level: RiskLevel, score: float,
                             assessment: dict) -> str:
        """Build a human-readable alert message."""
        messages = {
            RiskLevel.SAFE: f"Conditions are SAFE. Risk score: {score:.1f}%.",
            RiskLevel.CAUTION: (
                f"CAUTION — Elevated landslide risk detected. "
                f"Score: {score:.1f}%. Monitor conditions closely."
            ),
            RiskLevel.WARNING: (
                f"⚠️ WARNING — High landslide risk! Score: {score:.1f}%. "
                f"Prepare for possible evacuation. "
                f"Rainfall 24hr: {assessment.get('rainfall_24hr', 0):.1f}mm."
            ),
            RiskLevel.DANGER: (
                f"🚨 DANGER — Critical landslide risk! Score: {score:.1f}%. "
                f"EVACUATE IMMEDIATELY. "
                f"Rainfall 24hr: {assessment.get('rainfall_24hr', 0):.1f}mm. "
                f"Soil saturation critical."
            ),
        }
        return messages.get(level, f"Risk level: {level.value}, Score: {score:.1f}%")

    def _update_gpio_leds(self, level: RiskLevel):
        """Update LED indicators based on current risk level."""
        if not self._gpio_available:
            return

        import RPi.GPIO as GPIO
        # Turn all off first
        for pin in [self.LED_GREEN, self.LED_YELLOW, self.LED_ORANGE, self.LED_RED]:
            GPIO.output(pin, GPIO.LOW)

        # Turn on appropriate LED
        led_map = {
            RiskLevel.SAFE: self.LED_GREEN,
            RiskLevel.CAUTION: self.LED_YELLOW,
            RiskLevel.WARNING: self.LED_ORANGE,
            RiskLevel.DANGER: self.LED_RED,
        }
        if level in led_map:
            GPIO.output(led_map[level], GPIO.HIGH)

    def _trigger_buzzer(self, level: RiskLevel):
        """Trigger buzzer for WARNING/DANGER levels."""
        if not self._gpio_available:
            return

        import RPi.GPIO as GPIO
        # Short beep pattern for WARNING, continuous for DANGER
        if level == RiskLevel.WARNING:
            GPIO.output(self.BUZZER, GPIO.HIGH)
            # Non-blocking buzzer off after 0.5s would need a timer
            # For now, just a brief pulse
            GPIO.output(self.BUZZER, GPIO.LOW)
        elif level == RiskLevel.DANGER:
            GPIO.output(self.BUZZER, GPIO.HIGH)

    def cleanup(self):
        """Clean up GPIO resources."""
        if self._gpio_available:
            import RPi.GPIO as GPIO
            GPIO.cleanup()


# Global alert manager instance
alert_manager = AlertManager()
