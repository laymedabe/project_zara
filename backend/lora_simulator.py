"""
Project Zara — LoRa Simulator
===============================
Generates realistic fake sensor data for development and testing
without LoRa hardware. Mimics the exact data format that the Arduino
transmitter sends (post-parsing by lora_receiver.py).

Same callback interface as LoRaReceiver — swap seamlessly in main.py.
"""

import asyncio
import math
import random
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

from config import SIMULATOR_INTERVAL_SECONDS


class Scenario:
    """Pre-defined weather/terrain scenarios for realistic simulation."""

    @staticmethod
    def normal() -> dict:
        """Clear day — low risk."""
        return {
            "soil_moisture_1": random.uniform(25, 40),
            "soil_moisture_2": random.uniform(20, 35),
            "soil_moisture_3": None,
            "tilt_x": random.uniform(-0.5, 0.5),
            "tilt_y": random.uniform(-0.3, 0.3),
            "orientation": "Flat",
            "temperature": random.uniform(26, 32),
            "humidity": random.uniform(55, 70),
            "pressure": random.uniform(1008, 1015),
            "rainfall": random.uniform(0, 0.2),
        }

    @staticmethod
    def light_rain() -> dict:
        """Light rain — caution level."""
        return {
            "soil_moisture_1": random.uniform(45, 60),
            "soil_moisture_2": random.uniform(40, 55),
            "soil_moisture_3": None,
            "tilt_x": random.uniform(-1.0, 1.0),
            "tilt_y": random.uniform(-0.8, 0.8),
            "orientation": "Flat",
            "temperature": random.uniform(23, 27),
            "humidity": random.uniform(75, 85),
            "pressure": random.uniform(1003, 1008),
            "rainfall": random.uniform(1.0, 3.5),
        }

    @staticmethod
    def heavy_rain() -> dict:
        """Heavy rain — warning level."""
        return {
            "soil_moisture_1": random.uniform(65, 80),
            "soil_moisture_2": random.uniform(58, 72),
            "soil_moisture_3": None,
            "tilt_x": random.uniform(-3.0, 3.0),
            "tilt_y": random.uniform(-2.5, 2.5),
            "orientation": "Tilting Forward",
            "temperature": random.uniform(21, 25),
            "humidity": random.uniform(88, 95),
            "pressure": random.uniform(998, 1003),
            "rainfall": random.uniform(5.0, 12.0),
        }

    @staticmethod
    def typhoon() -> dict:
        """Typhoon conditions — danger level."""
        orientations = ["Tilting Forward", "Tilting Forward & Tilting Right",
                        "Tilting Backward & Tilting Left", "Tilting Right"]
        return {
            "soil_moisture_1": random.uniform(82, 95),
            "soil_moisture_2": random.uniform(75, 88),
            "soil_moisture_3": None,
            "tilt_x": random.uniform(-8.0, 8.0),
            "tilt_y": random.uniform(-6.0, 6.0),
            "orientation": random.choice(orientations),
            "temperature": random.uniform(20, 23),
            "humidity": random.uniform(93, 99),
            "pressure": random.uniform(985, 998),
            "rainfall": random.uniform(15.0, 35.0),
        }


class LoRaSimulator:
    """
    Simulates LoRa sensor data for development without hardware.

    Implements the same callback interface as LoRaReceiver,
    so it can be used as a drop-in replacement.
    """

    def __init__(self, interval: float = SIMULATOR_INTERVAL_SECONDS):
        self.interval = interval
        self._running = False
        self._on_data_callback: Optional[Callable[[dict], Awaitable[None]]] = None
        self._tick = 0
        self._scenario_name = "normal"

    def on_data(self, callback: Callable[[dict], Awaitable[None]]):
        """Register a callback for when new sensor data is generated."""
        self._on_data_callback = callback

    async def start(self):
        """Start generating simulated sensor data."""
        self._running = True
        print(f"[SIMULATOR] Started -- generating data every {self.interval}s", flush=True)
        print(f"[SIMULATOR] Scenario cycle: normal -> light_rain -> heavy_rain -> typhoon -> normal", flush=True)

        while self._running:
            data = self._generate_data()

            if self._on_data_callback:
                await self._on_data_callback(data)
                print(
                    f"[SIMULATOR] [{self._scenario_name.upper()}] "
                    f"Temp: {data['temperature']:.1f}°C, "
                    f"Humidity: {data['humidity']:.1f}%, "
                    f"Rain: {data['rainfall']:.1f}mm, "
                    f"Soil: {data['soil_moisture_1']:.0f}%/{data['soil_moisture_2']:.0f}%, "
                    f"Orient: {data['orientation']}",
                    flush=True
                )

            self._tick += 1
            await asyncio.sleep(self.interval)

    def _generate_data(self) -> dict:
        """Generate sensor data based on the current scenario in the cycle."""
        # Cycle through scenarios every ~2 minutes (24 ticks at 5s interval)
        cycle_position = self._tick % 48  # Full cycle = 48 ticks

        if cycle_position < 16:
            data = Scenario.normal()
            self._scenario_name = "normal"
        elif cycle_position < 26:
            data = Scenario.light_rain()
            self._scenario_name = "light_rain"
        elif cycle_position < 38:
            data = Scenario.heavy_rain()
            self._scenario_name = "heavy_rain"
        else:
            data = Scenario.typhoon()
            self._scenario_name = "typhoon"

        # Add smooth transitions using sine waves for more natural data
        time_factor = self._tick * 0.1
        data["temperature"] += math.sin(time_factor) * 0.5
        data["humidity"] += math.cos(time_factor) * 1.0
        data["pressure"] += math.sin(time_factor * 0.3) * 0.5

        # Metadata
        data["packet_id"] = self._tick
        data["raw_packet"] = "SIMULATED"
        data["is_valid"] = 1

        return data

    async def stop(self):
        """Stop the simulator."""
        self._running = False
        print("[SIMULATOR] Stopped", flush=True)
