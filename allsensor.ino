#include <Adafruit_BME280.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>
#include <math.h>

// --- Pin Assignments ---
const int RAIN_GAUGE_PIN = 2; // Digital Pin 2
const int SOIL_PIN_1 = A0;    // Analog Pin A0 for Soil Sensor 1
const int SOIL_PIN_2 = A1;    // Analog Pin A1 for Soil Sensor 2

// --- Calibration Settings ---
const float MM_PER_TIP = 0.2794;            // Rainfall per tip in mm
const unsigned long DEBOUNCE_TIME_MS = 200; // Switch debounce delay in ms
const float TILT_THRESHOLD_DEG =
    15.0; // Tilt angle in degrees to register direction

// --- Sensor Objects ---
Adafruit_MPU6050 mpu;
Adafruit_BME280 bme;

volatile unsigned long tipCount = 0;
volatile unsigned long lastTipTime = 0;

// Hardware Interrupt Service Routine for Rain Gauge
void countTip() {
  unsigned long currentTime = millis();
  if (currentTime - lastTipTime > DEBOUNCE_TIME_MS) {
    tipCount++;
    lastTipTime = currentTime;
  }
}

// Function to calculate tilt state based on pitch and roll angles
String getOrientation(float ax, float ay, float az) {
  // Convert acceleration vectors into Pitch and Roll angles in degrees
  float roll = atan2(ay, az) * RAD_TO_DEG;
  float pitch = atan2(-ax, sqrt(ay * ay + az * az)) * RAD_TO_DEG;

  String status = "";

  // Check Pitch (Forward / Backward)
  if (pitch > TILT_THRESHOLD_DEG) {
    status += "Tilting Forward";
  } else if (pitch < -TILT_THRESHOLD_DEG) {
    status += "Tilting Backward";
  }

  // Check Roll (Left / Right)
  if (roll > TILT_THRESHOLD_DEG) {
    if (status.length() > 0)
      status += " & ";
    status += "Tilting Right";
  } else if (roll < -TILT_THRESHOLD_DEG) {
    if (status.length() > 0)
      status += " & ";
    status += "Tilting Left";
  }

  // If no tilt threshold is exceeded, consider it flat
  if (status.length() == 0) {
    status = "Flat";
  }

  return status;
}

void setup() {
  Serial.begin(9600);
  while (!Serial)
    delay(10);

  // 1. Setup Tipping Bucket Pin
  pinMode(RAIN_GAUGE_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(RAIN_GAUGE_PIN), countTip, FALLING);

  // 2. Initialize MPU6050
  if (!mpu.begin()) {
    Serial.println(F("Error: MPU6050 not detected!"));
  } else {
    Serial.println(F("MPU6050 Initialized successfully."));
  }

  // 3. Initialize BME280
  bool bmeStatus = bme.begin(0x76);
  if (!bmeStatus) {
    bmeStatus = bme.begin(0x77);
  }

  if (!bmeStatus) {
    Serial.println(F("Error: BME280 not detected!"));
  } else {
    Serial.println(F("BME280 Initialized successfully."));
  }

  Serial.println(F("\n--- Complete Weather Station Active ---\n"));
}

void loop() {
  // 1. Read Soil Moisture Sensors
  int soil1Raw = analogRead(SOIL_PIN_1);
  int soil2Raw = analogRead(SOIL_PIN_2);

  // 2. Read MPU6050 Data & Calculate Orientation
  sensors_event_t accel, gyro, mpuTemp;
  mpu.getEvent(&accel, &gyro, &mpuTemp);
  String orientation = getOrientation(
      accel.acceleration.x, accel.acceleration.y, accel.acceleration.z);

  // 3. Read BME280 Sensor Data
  float tempC = bme.readTemperature();
  float pressureHPa = bme.readPressure() / 100.0F;
  float humidityPct = bme.readHumidity();

  // 4. Safely Copy Interrupt Variable for Rainfall Calculation
  noInterrupts();
  unsigned long currentTips = tipCount;
  interrupts();
  float totalRainfallMM = currentTips * MM_PER_TIP;

  // --- Output Data to Serial Monitor ---
  Serial.println(F("=================================================="));

  // Rain Output
  Serial.print(F("Rainfall: "));
  Serial.print(totalRainfallMM, 2);
  Serial.print(F(" mm  |  Total Tips: "));
  Serial.println(currentTips);

  // Soil Output
  Serial.print(F("Soil 1 (A0): "));
  Serial.print(soil1Raw);
  Serial.print(F("  |  Soil 2 (A1): "));
  Serial.println(soil2Raw);

  // BME280 Output
  Serial.print(F("Air Temp: "));
  Serial.print(tempC, 1);
  Serial.print(F(" °C  |  Humidity: "));
  Serial.print(humidityPct, 1);
  Serial.print(F(" %  |  Pressure: "));
  Serial.print(pressureHPa, 1);
  Serial.println(F(" hPa"));

  // MPU6050 Orientation Output
  Serial.print(F("Orientation: "));
  Serial.println(orientation);

  Serial.println();
  delay(2000);
}