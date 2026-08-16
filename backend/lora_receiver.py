"""
Project Zara — LoRa Receiver Driver
=====================================
SX1278 LoRa receiver driver using SPI on Raspberry Pi 5.
Receives sensor data packets from the Arduino field node.

NOTE: This is a placeholder driver. The packet parsing format will be
finalized once the Arduino code is shared by the colleague.
Currently uses a generic binary packet format.
"""

import asyncio
import struct
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

from config import (
    LORA_SPI_BUS, LORA_SPI_CS, LORA_RST_PIN, LORA_DIO0_PIN,
    LORA_FREQUENCY, LORA_SPREADING_FACTOR, LORA_BANDWIDTH,
    SENSOR_INTERVAL_SECONDS,
)


# =============================================================================
# PACKET FORMAT (Default — update once Arduino code is analyzed)
# =============================================================================
# Total: 22 bytes
# [HEADER:2B][SOIL1:2B][SOIL2:2B][SOIL3:2B][TILT_X:2B][TILT_Y:2B]
# [TEMP:2B][HUMIDITY:2B][PRESSURE:2B][RAIN:2B][CRC:2B]
PACKET_HEADER = 0x5A52  # "ZR" — Zara Reading
PACKET_FORMAT = ">H10hH"  # Big-endian: header(H), 10 signed shorts(h), CRC(H)
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)


def parse_packet(raw_bytes: bytes) -> Optional[dict]:
    """
    Parse a raw LoRa packet into sensor readings.

    The values are transmitted as integers (multiplied by 100 on Arduino side)
    to avoid floating point issues. We divide back here.

    Returns None if packet is invalid.
    """
    if len(raw_bytes) < PACKET_SIZE:
        return None

    try:
        unpacked = struct.unpack(PACKET_FORMAT, raw_bytes[:PACKET_SIZE])
    except struct.error:
        return None

    header = unpacked[0]
    if header != PACKET_HEADER:
        return None

    # Verify CRC (simple XOR checksum)
    crc_received = unpacked[-1]
    crc_computed = 0
    for b in raw_bytes[:PACKET_SIZE - 2]:
        crc_computed ^= b
    crc_computed &= 0xFFFF

    if crc_received != crc_computed:
        print(f"[LORA] CRC mismatch: received={crc_received:#06x}, computed={crc_computed:#06x}")
        return None

    # Parse sensor values (divided by 100 to get actual values)
    return {
        "soil_moisture_1": unpacked[1] / 100.0,
        "soil_moisture_2": unpacked[2] / 100.0,
        "soil_moisture_3": unpacked[3] / 100.0,
        "tilt_x": unpacked[4] / 100.0,
        "tilt_y": unpacked[5] / 100.0,
        "temperature": unpacked[6] / 100.0,
        "humidity": unpacked[7] / 100.0,
        "pressure": unpacked[8] / 10.0,    # Pressure needs less precision
        "rainfall": unpacked[9] / 100.0,
        "raw_packet": raw_bytes[:PACKET_SIZE].hex(),
        "is_valid": 1,
    }


class LoRaReceiver:
    """
    SX1278 LoRa receiver using SPI on Raspberry Pi 5.
    
    This class wraps the SPI communication and provides an async 
    interface for receiving parsed sensor data packets.
    """

    def __init__(self):
        self._spi = None
        self._running = False
        self._on_data_callback: Optional[Callable[[dict], Awaitable[None]]] = None

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
            print(f"[LORA] Receiver initialized — Freq: {LORA_FREQUENCY/1e6}MHz, "
                  f"SF: {LORA_SPREADING_FACTOR}")

            # Start receive loop
            await self._receive_loop()

        except ImportError:
            print("[LORA] ERROR — spidev or RPi.GPIO not available.")
            print("[LORA] Use LoRaSimulator for development without hardware.")
            raise RuntimeError("LoRa hardware libraries not available. Use simulator mode.")

    async def _configure_sx1278(self):
        """Write configuration registers to SX1278."""
        # Set sleep mode
        self._write_register(0x01, 0x00)
        await asyncio.sleep(0.01)

        # Set LoRa mode
        self._write_register(0x01, 0x80)
        await asyncio.sleep(0.01)

        # Set frequency
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

        # Set payload length
        self._write_register(0x22, PACKET_SIZE)

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

        print("[LORA] Listening for packets...")

        while self._running:
            # Check DIO0 for RxDone interrupt
            if GPIO.input(LORA_DIO0_PIN):
                # Read IRQ flags
                irq_flags = self._read_register(0x12)

                if irq_flags & 0x40:  # RxDone
                    # Check for CRC error
                    if irq_flags & 0x20:
                        print("[LORA] CRC error in received packet")
                    else:
                        # Read payload
                        current_addr = self._read_register(0x10)
                        self._write_register(0x0D, current_addr)
                        rx_bytes = bytes(
                            self._read_register(0x00) for _ in range(PACKET_SIZE)
                        )

                        # Parse the packet
                        data = parse_packet(rx_bytes)
                        if data and self._on_data_callback:
                            await self._on_data_callback(data)
                            print(f"[LORA] Packet received — "
                                  f"Temp: {data['temperature']:.1f}°C, "
                                  f"Humidity: {data['humidity']:.1f}%")

                    # Clear IRQ flags
                    self._write_register(0x12, 0xFF)

            await asyncio.sleep(0.1)  # Poll every 100ms

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
        print("[LORA] Receiver stopped")
