"""
Project Zara — LoRa Receiver Driver
=====================================
SX1278 LoRa receiver driver using SPI on Raspberry Pi 5.
Receives CSV-formatted sensor data packets from the Arduino field node.

Packet format from Arduino (CSV string):
  [PacketID],[TempC],[Humidity%],[PressureHPa],[Soil1Raw],[Soil2Raw],[RainMM],[Orientation]

Example:
  42,28.5,78.3,1012.4,512,480,1.40,Flat

Orientation values: "Flat", "Tilting Forward", "Tilting Backward",
                    "Tilting Right", "Tilting Left", or combinations
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

from config import (
    LORA_SPI_BUS, LORA_SPI_CS, LORA_RST_PIN, LORA_DIO0_PIN,
    LORA_FREQUENCY, LORA_SPREADING_FACTOR, LORA_BANDWIDTH,
    LORA_CODING_RATE, SOIL_ADC_DRY, SOIL_ADC_WET,
)


# =============================================================================
# SOIL MOISTURE CONVERSION
# =============================================================================
def adc_to_moisture_pct(raw_adc: int) -> float:
    """
    Convert raw capacitive soil moisture ADC reading to percentage.

    Capacitive sensors are inverted:
      - DRY = high ADC value (~620 in air)
      - WET = low ADC value (~310 in water)

    Returns 0-100% where 100% = saturated.
    """
    # Clamp to calibration range
    clamped = max(SOIL_ADC_WET, min(SOIL_ADC_DRY, raw_adc))
    # Invert: lower ADC = wetter
    pct = (SOIL_ADC_DRY - clamped) / (SOIL_ADC_DRY - SOIL_ADC_WET) * 100.0
    return round(max(0, min(100, pct)), 1)


# =============================================================================
# ORIENTATION STRING TO TILT ESTIMATE
# =============================================================================
def orientation_to_tilt(orientation: str) -> tuple[float, float]:
    """
    Estimate tilt_x (pitch) and tilt_y (roll) from Arduino orientation string.

    The Arduino code uses a 15° threshold, so we estimate:
      - "Flat" → 0°, 0°
      - "Tilting Forward" → +20° pitch
      - "Tilting Backward" → -20° pitch
      - "Tilting Right" → +20° roll
      - "Tilting Left" → -20° roll
      - Combinations: both axes affected

    These are rough estimates. For precise angles, the Arduino code should
    be modified to send raw pitch/roll values.
    """
    tilt_x = 0.0  # Pitch
    tilt_y = 0.0  # Roll

    orient_lower = orientation.lower().strip()

    if "forward" in orient_lower:
        tilt_x = 20.0
    elif "backward" in orient_lower:
        tilt_x = -20.0

    if "right" in orient_lower:
        tilt_y = 20.0
    elif "left" in orient_lower:
        tilt_y = -20.0

    return tilt_x, tilt_y


# =============================================================================
# CSV PACKET PARSER
# =============================================================================
def parse_csv_packet(payload_str: str) -> Optional[dict]:
    """
    Parse the Arduino's CSV payload string into a sensor reading dict.

    Expected format:
      PacketID,TempC,Humidity%,PressureHPa,Soil1Raw,Soil2Raw,RainMM,Orientation

    Returns None if the packet is malformed.
    """
    try:
        # The orientation field may contain commas in combinations like
        # "Tilting Forward & Tilting Right", but the Arduino uses " & " not ","
        # so a simple split on "," should work for 8 fields.
        # However, orientation is the last field, so we split with maxsplit=7
        parts = payload_str.strip().split(",", 7)

        if len(parts) < 8:
            print(f"[LORA] Malformed packet -- expected 8 fields, got {len(parts)}: {payload_str[:60]}")
            return None

        packet_id = int(parts[0])
        temperature = float(parts[1])
        humidity = float(parts[2])
        pressure = float(parts[3])
        soil1_raw = int(parts[4])
        soil2_raw = int(parts[5])
        rainfall_total_mm = float(parts[6])
        orientation = parts[7].strip()

        # Convert soil ADC to percentage
        soil_moisture_1 = adc_to_moisture_pct(soil1_raw)
        soil_moisture_2 = adc_to_moisture_pct(soil2_raw)

        # Convert orientation to tilt angles
        tilt_x, tilt_y = orientation_to_tilt(orientation)

        return {
            "packet_id": packet_id,
            "soil_moisture_1": soil_moisture_1,
            "soil_moisture_2": soil_moisture_2,
            "soil_moisture_3": None,              # Only 2 sensors installed
            "soil1_raw": soil1_raw,
            "soil2_raw": soil2_raw,
            "tilt_x": tilt_x,
            "tilt_y": tilt_y,
            "orientation": orientation,
            "temperature": temperature,
            "humidity": humidity,
            "pressure": pressure,
            "rainfall": rainfall_total_mm,        # Cumulative — delta computed by data_processor
            "raw_packet": payload_str.strip(),
            "is_valid": 1,
        }

    except (ValueError, IndexError) as e:
        print(f"[LORA] Failed to parse packet: {e} | Raw: {payload_str[:80]}")
        return None


# =============================================================================
# LORA RECEIVER CLASS
# =============================================================================
class LoRaReceiver:
    """
    SX1278 LoRa receiver using SPI on Raspberry Pi 5.

    Receives CSV text packets from the Arduino transmitter and parses
    them into sensor reading dictionaries.
    """

    def __init__(self):
        self._spi = None
        self._running = False
        self._on_data_callback: Optional[Callable[[dict], Awaitable[None]]] = None
        self._last_rainfall_total = 0.0  # Track cumulative rainfall for delta computation

    def on_data(self, callback: Callable[[dict], Awaitable[None]]):
        """Register a callback for when new sensor data is received."""
        self._on_data_callback = callback

    async def start(self):
        """Initialize the SX1278 module and start listening."""
        try:
            import spidev
            import RPi.GPIO as GPIO

            # Setup GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(LORA_RST_PIN, GPIO.OUT)
            GPIO.setup(LORA_DIO0_PIN, GPIO.IN)

            # Reset the module
            GPIO.output(LORA_RST_PIN, GPIO.LOW)
            await asyncio.sleep(0.01)
            GPIO.output(LORA_RST_PIN, GPIO.HIGH)
            await asyncio.sleep(0.01)

            # Initialize SPI
            self._spi = spidev.SpiDev()
            self._spi.open(LORA_SPI_BUS, LORA_SPI_CS)
            self._spi.max_speed_hz = 5000000  # 5 MHz

            # Configure SX1278 registers
            await self._configure_sx1278()

            self._running = True
            print(f"[LORA] Receiver initialized -- Freq: {LORA_FREQUENCY/1e6}MHz, "
                  f"SF: {LORA_SPREADING_FACTOR}", flush=True)

            # Start receive loop
            await self._receive_loop()

        except ImportError:
            print("[LORA] ERROR -- spidev or RPi.GPIO not available.", flush=True)
            print("[LORA] Use LoRaSimulator for development without hardware.", flush=True)
            raise RuntimeError("LoRa hardware libraries not available. Use simulator mode.")

    async def _configure_sx1278(self):
        """Write configuration registers to SX1278."""
        # Set sleep mode
        self._write_register(0x01, 0x00)
        await asyncio.sleep(0.01)

        # Set LoRa mode
        self._write_register(0x01, 0x80)
        await asyncio.sleep(0.01)

        # Set frequency (433 MHz)
        freq_int = int(LORA_FREQUENCY / 61.035)  # FSTEP = 61.035 Hz
        self._write_register(0x06, (freq_int >> 16) & 0xFF)
        self._write_register(0x07, (freq_int >> 8) & 0xFF)
        self._write_register(0x08, freq_int & 0xFF)

        # Set bandwidth, coding rate, spreading factor
        bw_map = {7800: 0, 10400: 1, 15600: 2, 20800: 3, 31250: 4,
                  41700: 5, 62500: 6, 125000: 7, 250000: 8, 500000: 9}
        bw_val = bw_map.get(int(LORA_BANDWIDTH), 7)
        self._write_register(0x1D, (bw_val << 4) | ((LORA_CODING_RATE - 4) << 1))
        self._write_register(0x1E, (LORA_SPREADING_FACTOR << 4) | 0x04)  # CRC on

        # Implicit header mode OFF (explicit header — variable length packets)
        # This is important for CSV text packets of varying length
        self._write_register(0x1D, self._read_register(0x1D) & 0xFE)

        # Set max payload length (CSV packets can be up to ~80 chars)
        self._write_register(0x23, 128)  # Max payload length

        # Set continuous receive mode
        self._write_register(0x01, 0x85)

    def _write_register(self, address: int, value: int):
        """Write a value to an SX1278 register via SPI."""
        self._spi.xfer2([address | 0x80, value])

    def _read_register(self, address: int) -> int:
        """Read a value from an SX1278 register via SPI."""
        result = self._spi.xfer2([address & 0x7F, 0x00])
        return result[1]

    async def _receive_loop(self):
        """Main receive loop — polls for incoming LoRa packets."""
        import RPi.GPIO as GPIO

        print("[LORA] Listening for Arduino CSV packets...", flush=True)

        while self._running:
            # Check DIO0 for RxDone interrupt
            if GPIO.input(LORA_DIO0_PIN):
                # Read IRQ flags
                irq_flags = self._read_register(0x12)

                if irq_flags & 0x40:  # RxDone
                    if irq_flags & 0x20:
                        print("[LORA] CRC error in received packet", flush=True)
                    else:
                        # Read payload length
                        payload_length = self._read_register(0x13)

                        # Set FIFO address to current RX address
                        current_addr = self._read_register(0x10)
                        self._write_register(0x0D, current_addr)

                        # Read payload bytes
                        rx_bytes = bytes(
                            self._read_register(0x00) for _ in range(payload_length)
                        )

                        # Decode CSV text
                        try:
                            payload_str = rx_bytes.decode('ascii')
                        except UnicodeDecodeError:
                            print(f"[LORA] Non-ASCII payload received ({len(rx_bytes)} bytes)", flush=True)
                            self._write_register(0x12, 0xFF)
                            continue

                        # Read RSSI for signal quality monitoring
                        rssi = self._read_register(0x1A) - 157

                        # Parse the CSV payload
                        data = parse_csv_packet(payload_str)
                        if data:
                            # Compute rainfall delta (Arduino sends cumulative total)
                            data["rainfall"] = self._compute_rainfall_delta(data["rainfall"])
                            data["rssi"] = rssi

                            if self._on_data_callback:
                                await self._on_data_callback(data)

                            print(
                                f"[LORA] Packet #{data['packet_id']} | "
                                f"Temp: {data['temperature']:.1f}°C, "
                                f"Humidity: {data['humidity']:.1f}%, "
                                f"Rain: {data['rainfall']:.2f}mm, "
                                f"Soil: {data['soil_moisture_1']:.0f}%/{data['soil_moisture_2']:.0f}%, "
                                f"Orient: {data['orientation']} | "
                                f"RSSI: {rssi}dBm",
                                flush=True
                            )

                    # Clear IRQ flags
                    self._write_register(0x12, 0xFF)

            await asyncio.sleep(0.1)  # Poll every 100ms

    def _compute_rainfall_delta(self, current_total: float) -> float:
        """
        Compute per-interval rainfall from Arduino's cumulative total.

        The Arduino sends total rainfall since boot. We compute the delta
        since the last reading to get per-interval rainfall.
        """
        if self._last_rainfall_total == 0.0:
            # First reading — assume delta is 0 (can't know previous)
            self._last_rainfall_total = current_total
            return 0.0

        delta = current_total - self._last_rainfall_total
        self._last_rainfall_total = current_total

        # Handle Arduino reboot (total resets to 0)
        if delta < 0:
            delta = current_total

        return round(max(0, delta), 4)

    async def stop(self):
        """Stop the receiver and clean up."""
        self._running = False
        if self._spi:
            self._spi.close()
        try:
            import RPi.GPIO as GPIO
            GPIO.cleanup()
        except ImportError:
            pass
        print("[LORA] Receiver stopped", flush=True)
