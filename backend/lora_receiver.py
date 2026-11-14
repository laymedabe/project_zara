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
import math
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
    Convert raw soil moisture ADC reading to percentage.
    Automatically handles both Capacitive (DRY > WET) and Resistive (WET > DRY) sensors.
    """
    # Determine which bound is higher
    high_bound = max(SOIL_ADC_DRY, SOIL_ADC_WET)
    low_bound = min(SOIL_ADC_DRY, SOIL_ADC_WET)
    
    # Clamp the raw ADC reading between the bounds
    clamped = max(low_bound, min(high_bound, raw_adc))
    
    # Map the clamped value to 0-100%
    if SOIL_ADC_DRY == SOIL_ADC_WET:
        return 0.0 # Prevent division by zero if uncalibrated
        
    pct = (SOIL_ADC_DRY - clamped) / (SOIL_ADC_DRY - SOIL_ADC_WET) * 100.0
    return round(max(0, min(100, pct)), 1)


# =============================================================================
# ORIENTATION STRING TO TILT ESTIMATE
# =============================================================================
def orientation_to_tilt(orientation: str) -> tuple[float, float]:
    """
    Estimate tilt_x (pitch) and tilt_y (roll) from Arduino orientation string.
    Supports direct angles (e.g. "Tilt X: 3.5 Y: -2.1") or text ("Tilting Forward").
    """
    import re
    # Extract any explicit numeric coordinates (e.g. "Tilt X:3.2 Y:-1.5" or "3.2, -1.5")
    nums = re.findall(r'[-+]?\d*\.?\d+', orientation)
    if len(nums) >= 2:
        try:
            return round(float(nums[0]), 2), round(float(nums[1]), 2)
        except ValueError:
            pass

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
        raw_clean = payload_str.strip()

        # Support Key-Value packet format (e.g. ID:12, T:NAN, H:NAN, P:NAN, AX:6.13, AY:-77.23, AZ:115.23)
        if ":" in raw_clean and any(k in raw_clean.upper() for k in ["ID:", "T:", "AX:"]):
            kv = {}
            for item in raw_clean.split(","):
                if ":" in item:
                    k, v = item.split(":", 1)
                    kv[k.strip().upper()] = v.strip()

            def safe_float(val_str, default=0.0):
                try:
                    f = float(val_str)
                    return default if (math.isnan(f) or math.isinf(f)) else f
                except (ValueError, TypeError):
                    return default

            packet_id = int(safe_float(kv.get("ID", 0)))
            temperature = safe_float(kv.get("T", 0.0))
            humidity = safe_float(kv.get("H", 0.0))
            pressure = safe_float(kv.get("P", 0.0))
            soil1_raw = int(safe_float(kv.get("S1", kv.get("SOIL1", 0))))
            soil2_raw = int(safe_float(kv.get("S2", kv.get("SOIL2", 0))))
            rainfall_total_mm = safe_float(kv.get("R", kv.get("RAIN", 0.0)))

            tilt_x = safe_float(kv.get("AX", kv.get("TILTX", 0.0)))
            tilt_y = safe_float(kv.get("AY", kv.get("TILTY", 0.0)))

            orientation = kv.get("O", kv.get("ORIENT", ""))
            if not orientation:
                if abs(tilt_x) > 15 or abs(tilt_y) > 15:
                    orientation = f"Tilt X:{tilt_x:.1f}° Y:{tilt_y:.1f}°"
                else:
                    orientation = "Flat"

            soil_moisture_1 = adc_to_moisture_pct(soil1_raw) if soil1_raw > 0 else 0.0
            soil_moisture_2 = adc_to_moisture_pct(soil2_raw) if soil2_raw > 0 else 0.0

            return {
                "packet_id": packet_id,
                "soil_moisture_1": soil_moisture_1,
                "soil_moisture_2": soil_moisture_2,
                "soil_moisture_3": None,
                "soil1_raw": soil1_raw,
                "soil2_raw": soil2_raw,
                "tilt_x": tilt_x,
                "tilt_y": tilt_y,
                "orientation": orientation,
                "temperature": temperature,
                "humidity": humidity,
                "pressure": pressure,
                "rainfall": rainfall_total_mm,
                "raw_packet": raw_clean,
                "is_valid": 1,
            }

        # Standard CSV format: PacketID,TempC,Humidity%,PressureHPa,Soil1Raw,Soil2Raw,RainMM,Orientation
        parts = raw_clean.split(",", 7)

        if len(parts) < 8:
            print(f"[LORA] Malformed packet -- expected 8 fields, got {len(parts)}: {raw_clean[:60]}")
            return None

        packet_id = int(parts[0])
        
        # Safely parse floats, replacing any NaN or out-of-range sensor glitches
        try:
            temperature = float(parts[1])
            if math.isnan(temperature) or temperature > 100 or temperature < -40:
                temperature = 0.0
        except ValueError:
            temperature = 0.0

        try:
            humidity = float(parts[2])
            if math.isnan(humidity):
                humidity = 0.0
        except ValueError:
            humidity = 0.0

        try:
            pressure = float(parts[3])
            if math.isnan(pressure):
                pressure = 0.0
        except ValueError:
            pressure = 0.0

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
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(LORA_RST_PIN, GPIO.OUT)
                GPIO.setup(LORA_DIO0_PIN, GPIO.IN)

                # Reset the module
                GPIO.output(LORA_RST_PIN, GPIO.LOW)
                await asyncio.sleep(0.01)
                GPIO.output(LORA_RST_PIN, GPIO.HIGH)
                await asyncio.sleep(0.01)
            except Exception as e:
                print(f"[LORA] GPIO setup note: {e}", flush=True)

            # Initialize SPI
            self._spi = spidev.SpiDev()
            self._spi.open(LORA_SPI_BUS, LORA_SPI_CS)
            self._spi.max_speed_hz = 1000000  # 1 MHz (stable with jumper wires)

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
        # 1. Verify SPI communication by reading chip version
        version = self._read_register(0x42)
        print(f"[LORA] SX1278 Chip Version: 0x{version:02X} (Expected: 0x12)", flush=True)
        if version != 0x12:
            print(f"[LORA] WARNING: SX1278 SPI read returned 0x{version:02X}! Check SPI/power wiring on Raspberry Pi.", flush=True)

        # 433 MHz requires LowFrequencyModeOn (Bit 3 = 1) in RegOpMode
        low_freq_bit = 0x08 if LORA_FREQUENCY < 525E6 else 0x00

        # Set sleep mode with LoRa mode and correct frequency band
        self._write_register(0x01, 0x00)
        await asyncio.sleep(0.01)
        self._write_register(0x01, 0x80 | low_freq_bit)  # LoRa sleep mode
        await asyncio.sleep(0.01)

        # Standby mode
        self._write_register(0x01, 0x81 | low_freq_bit)
        await asyncio.sleep(0.01)

        # Set frequency (433 MHz)
        freq_int = int(LORA_FREQUENCY / 61.03515625)  # FSTEP = 61.03515625 Hz
        self._write_register(0x06, (freq_int >> 16) & 0xFF)
        self._write_register(0x07, (freq_int >> 8) & 0xFF)
        self._write_register(0x08, freq_int & 0xFF)

        # Base FIFO addresses
        self._write_register(0x0E, 0x00)  # TxBaseAddr
        self._write_register(0x0F, 0x00)  # RxBaseAddr
        self._write_register(0x0D, 0x00)  # FifoAddrPtr

        # LNA Boost for maximum receive sensitivity
        lna = self._read_register(0x0C)
        self._write_register(0x0C, lna | 0x03)

        # Set bandwidth, coding rate, spreading factor
        bw_map = {7800: 0, 10400: 1, 15600: 2, 20800: 3, 31250: 4,
                  41700: 5, 62500: 6, 125000: 7, 250000: 8, 500000: 9}
        bw_val = bw_map.get(int(LORA_BANDWIDTH), 7)
        self._write_register(0x1D, (bw_val << 4) | ((LORA_CODING_RATE - 4) << 1))

        # Explicit header mode: receiver accepts both CRC-enabled and CRC-disabled packets
        self._write_register(0x1E, (LORA_SPREADING_FACTOR << 4))

        # Turn on AGC Auto (RegModemConfig3)
        self._write_register(0x26, 0x04)

        # Sync word: 0x12 (matches default Arduino LoRa library)
        self._write_register(0x39, 0x12)

        # DIO0 mapping: 00 = RxDone
        self._write_register(0x40, 0x00)

        # Implicit header mode OFF (explicit header — variable length packets)
        self._write_register(0x1D, self._read_register(0x1D) & 0xFE)

        # Set max payload length (CSV packets can be up to ~80 chars)
        self._write_register(0x23, 128)

        # Set continuous receive mode with LowFrequencyModeOn enabled (0x8D for 433MHz)
        self._write_register(0x01, 0x85 | low_freq_bit)

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

        loop_count = 0
        while self._running:
            loop_count += 1
            irq_flags = self._read_register(0x12)
            dio0_high = False
            try:
                dio0_high = bool(GPIO.input(LORA_DIO0_PIN))
            except Exception:
                pass

            if loop_count % 100 == 0:  # Every ~10 seconds
                current_mode = self._read_register(0x01)
                current_rssi = self._read_register(0x1B) - 157
                print(f"[LORA] Receiver active (RegOpMode: 0x{current_mode:02X}, IrqFlags: 0x{irq_flags:02X}, DIO0: {dio0_high}, RSSI: {current_rssi}dBm)", flush=True)
            # Check DIO0 pin OR read SX1278 RegIrqFlags (0x12) directly via SPI
            irq_flags = self._read_register(0x12)
            dio0_high = False
            try:
                dio0_high = bool(GPIO.input(LORA_DIO0_PIN))
            except Exception:
                pass

            if irq_flags != 0xFF and ((irq_flags & 0x40) or dio0_high):  # RxDone
                # Refresh flags
                irq_flags = self._read_register(0x12)
                has_crc_error = bool(irq_flags & 0x20)

                if has_crc_error:
                    print("[LORA] Notice: CRC error flag set (possible CRC mismatch or weak signal). Attempting to decode payload...", flush=True)

                # Read payload length
                payload_length = self._read_register(0x13)
                if payload_length == 0 or payload_length > 128:
                    self._write_register(0x12, 0xFF)
                    await asyncio.sleep(0.05)
                    continue

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
