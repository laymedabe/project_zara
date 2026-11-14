#include <Adafruit_BME280.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <LoRa.h>
#include <SPI.h>
#include <Wire.h>
#include <math.h>

// --- Pin Assignments ---
#define LORA_SS 10
#define LORA_RST 9
#define LORA_DIO0 2   // LoRa Interrupt
#define RAIN_PIN 3    // Rain Gauge Interrupt
#define SOIL_PIN_1 A0 // Capacitive Soil Sensor 1
#define SOIL_PIN_2 A1 // Capacitive Soil Sensor 2

#define LORA_BAND                                                              \
  433E6 // Set to 433E6, 868E6, or 915E6 depending on module regional frequency

// --- Rain Gauge Settings ---
const float MM_PER_TIP = 0.2794;
const unsigned long DEBOUNCE_TIME_MS = 200;
volatile unsigned long tipCount = 0;
volatile unsigned long lastTipTime = 0;

// --- Motion Settings ---
const float TILT_THRESHOLD_DEG = 15.0;

// --- Sensor Objects ---
Adafruit_MPU6050 mpu;
Adafruit_BME280 bme;

unsigned int packetCounter = 0;

// Hardware Interrupt for Rain Gauge
void countTip() {
  unsigned long currentTime = millis();
  if (currentTime - lastTipTime > DEBOUNCE_TIME_MS) {
    tipCount++;
    lastTipTime = currentTime;
  }
}

// Calculate tilt orientation
String getOrientation(float ax, float ay, float az) {
  float roll = atan2(ay, az) * RAD_TO_DEG;
  float pitch = atan2(-ax, sqrt(ay * ay + az * az)) * RAD_TO_DEG;

  String status = "";

  if (pitch > TILT_THRESHOLD_DEG) {
    status += "Tilting Forward";
  } else if (pitch < -TILT_THRESHOLD_DEG) {
    status += "Tilting Backward";
  }

  if (roll > TILT_THRESHOLD_DEG) {
    if (status.length() > 0)
      status += " & ";
    status += "Tilting Right";
  } else if (roll < -TILT_THRESHOLD_DEG) {
    if (status.length() > 0)
      status += " & ";
    status += "Tilting Left";
  }

  if (status.length() == 0) {
    status = "Flat";
  }

  return status;
}

void setup() {
  Serial.begin(9600);
  while (!Serial)
    delay(10);

  Wire.begin();
  #if defined(WIRE_HAS_TIMEOUT)
  Wire.setWireTimeout(3000, true); // Prevent I2C bus lockup
  #endif

  // 1. Setup Rain Gauge Interrupt
  pinMode(RAIN_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(RAIN_PIN), countTip, FALLING);

  // 2. BME280 & MPU6050 (Simulated values sent in loop)
  Serial.println(F("BME280 & MPU6050: Simulated mode active"));

  // 4. Initialize SX1278 LoRa Module
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  int loraRetries = 0;
  while (!LoRa.begin(LORA_BAND)) {
    Serial.println(F("Error: SX1278 LoRa initialization failed! Retrying in 1s..."));
    delay(1000);
    loraRetries++;
    if (loraRetries >= 5) {
      Serial.println(F("Check LoRa wiring: SS=10, RST=9, DIO0=2, MOSI=11, MISO=12, SCK=13, 3.3V, GND"));
      loraRetries = 0;
    }
  }
  LoRa.enableCrc(); // Enable CRC matching Raspberry Pi SX1278 settings
}

void loop() {
  // 1. Read Dual Soil Moisture Sensors (REAL SENSORS)
  int soil1Raw = analogRead(SOIL_PIN_1);
  int soil2Raw = analogRead(SOIL_PIN_2);

  // 2. Read Rain Gauge Tipping Bucket (REAL SENSOR)
  noInterrupts();
  unsigned long currentTips = tipCount;
  interrupts();
  float totalRainfallMM = currentTips * MM_PER_TIP;

  // 3. Simulated BME280 (Smooth dynamic weather drift)
  float t = millis() / 10000.0;
  float tempC = 28.5 + sin(t * 0.5) * 1.5;            // Smoothly drifts: 27.0°C - 30.0°C
  float humidityPct = 78.0 + cos(t * 0.4) * 4.0;      // Smoothly drifts: 74.0% - 82.0%
  float pressureHPa = 1012.3 + sin(t * 0.2) * 1.2;    // Smoothly drifts: 1011.1 - 1013.5 hPa

  // 4. Simulated MPU6050 (Dynamic slope movement)
  // Tilt X and Tilt Y oscillate smoothly so the dot glides across the dashboard radar
  float tiltX = sin(t * 0.8) * 6.5;                   // Pitch: -6.5° to +6.5°
  float tiltY = cos(t * 0.6) * 5.0;                   // Roll: -5.0° to +5.0°

  // Format orientation with live angles for the dashboard reticle
  String orientation = "Tilt X:" + String(tiltX, 2) + " Y:" + String(tiltY, 2);
  if (abs(tiltX) < 1.5 && abs(tiltY) < 1.5) {
    orientation += " (Flat)";
  }

  // 5. Construct CSV Payload String
  // Format:
  // [PacketID],[TempC],[Humidity%],[PressureHPa],[Soil1Raw],[Soil2Raw],[RainMM],[Orientation]
  String payload = String(packetCounter) + "," + String(tempC, 1) + "," +
                   String(humidityPct, 1) + "," + String(pressureHPa, 1) + "," +
                   String(soil1Raw) + "," + String(soil2Raw) + "," +
                   String(totalRainfallMM, 2) + "," + orientation;

  // 6. Transmit via LoRa
  Serial.print(F("Sending packet #"));
  Serial.print(packetCounter);
  Serial.print(F(" | Payload: "));
  Serial.println(payload);

  LoRa.beginPacket();
  LoRa.print(payload);
  LoRa.endPacket();

  packetCounter++;
  delay(2000);
}