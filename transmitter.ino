#include <Wire.h>
#include <SPI.h>
#include <LoRa.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include <math.h>

// --- Pin Assignments ---
#define LORA_SS     10
#define LORA_RST    9
#define LORA_DIO0   2     // LoRa Interrupt
#define RAIN_PIN    3     // Rain Gauge Interrupt
#define SOIL_PIN_1  A0    // Capacitive Soil Sensor 1
#define SOIL_PIN_2  A1    // Capacitive Soil Sensor 2

#define LORA_BAND   433E6 // Set to 433E6, 868E6, or 915E6 depending on module regional frequency

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
  float roll  = atan2(ay, az) * RAD_TO_DEG;
  float pitch = atan2(-ax, sqrt(ay * ay + az * az)) * RAD_TO_DEG;

  String status = "";

  if (pitch > TILT_THRESHOLD_DEG) {
    status += "Tilting Forward";
  } else if (pitch < -TILT_THRESHOLD_DEG) {
    status += "Tilting Backward";
  }

  if (roll > TILT_THRESHOLD_DEG) {
    if (status.length() > 0) status += " & ";
    status += "Tilting Right";
  } else if (roll < -TILT_THRESHOLD_DEG) {
    if (status.length() > 0) status += " & ";
    status += "Tilting Left";
  }

  if (status.length() == 0) {
    status = "Flat";
  }

  return status;
}

void setup() {
  Serial.begin(9600);
  while (!Serial) delay(10);

  // 1. Setup Rain Gauge Interrupt
  pinMode(RAIN_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(RAIN_PIN), countTip, FALLING);

  // 2. Initialize BME280
  bool bmeStatus = bme.begin(0x76);
  if (!bmeStatus) {
    bmeStatus = bme.begin(0x77);
  }
  if (!bmeStatus) {
    Serial.println(F("Error: BME280 not detected!"));
  } else {
    Serial.println(F("BME280 Initialized."));
  }

  // 3. Initialize MPU6050
  if (!mpu.begin()) {
    Serial.println(F("Error: MPU6050 not detected!"));
  } else {
    Serial.println(F("MPU6050 Initialized."));
  }

  // 4. Initialize SX1278 LoRa Module
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(LORA_BAND)) {
    Serial.println(F("Error: SX1278 LoRa initialization failed!"));
    while (1);
  }
  Serial.println(F("SX1278 LoRa Transmitting..."));
}

void loop() {
  // 1. Read Dual Soil Moisture Sensors
  int soil1Raw = analogRead(SOIL_PIN_1);
  int soil2Raw = analogRead(SOIL_PIN_2);

  // 2. Copy Rain Count Interrupt Variable
  noInterrupts();
  unsigned long currentTips = tipCount;
  interrupts();
  float totalRainfallMM = currentTips * MM_PER_TIP;

  // 3. Read BME280 Data
  float tempC = bme.readTemperature();
  float humidityPct = bme.readHumidity();
  float pressureHPa = bme.readPressure() / 100.0F;

  // 4. Read MPU6050 Data
  sensors_event_t accel, gyro, mpuTemp;
  mpu.getEvent(&accel, &gyro, &mpuTemp);
  String orientation = getOrientation(accel.acceleration.x, accel.acceleration.y, accel.acceleration.z);

  // 5. Construct CSV Payload String
  // Format: [PacketID],[TempC],[Humidity%],[PressureHPa],[Soil1Raw],[Soil2Raw],[RainMM],[Orientation]
  String payload = String(packetCounter) + "," +
                   String(tempC, 1) + "," +
                   String(humidityPct, 1) + "," +
                   String(pressureHPa, 1) + "," +
                   String(soil1Raw) + "," +
                   String(soil2Raw) + "," +
                   String(totalRainfallMM, 2) + "," +
                   orientation;

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