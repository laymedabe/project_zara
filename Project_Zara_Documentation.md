# Project Zara: Smart IoT-Based Landslide Early Warning System

## 1. Introduction
Welcome to **Project Zara**! This project is a smart, automated system designed to help communities in landslide-prone areas, specifically created for Leon, Iloilo. By using modern robotics and Internet of Things (IoT) technology, Project Zara acts as an "early warning system." It constantly monitors the mountain slopes for dangerous signs like heavy rainfall, very wet soil, or ground movement, and sends out alerts *before* a landslide happens, giving people time to evacuate safely.

## 2. Objectives
* **Save Lives:** Provide early warnings to residents so they can evacuate before a disaster strikes.
* **Monitor the Environment 24/7:** Automatically track rain, soil moisture, and ground movement without needing humans to stand in the rain.
* **Work Completely Offline:** Function perfectly even during internet outages or typhoons, using its own independent Wi-Fi hotspot and long-range radio signals.
* **Easy to Understand:** Provide a simple, color-coded dashboard (Green to Red) so anyone at the Barangay Hall can easily understand the current danger level.

---

## 3. System Architecture (How it Works)
Project Zara is split into two main parts that talk to each other wirelessly:

1. **The Sensor Node (On the Mountain):** This is the robotic "brain" on the slope. It has various sensors that constantly measure the weather and the ground. It takes these measurements and broadcasts them through the air using a long-range radio antenna (LoRa).
2. **The Base Station (At the Barangay Hall):** This is the receiving station. It catches the radio signals from the mountain. It processes the data, calculates the risk of a landslide, and hosts a Wi-Fi network. Anyone connected to this Wi-Fi can view the dashboard on their phone or laptop.

---

## 4. Materials and Components

### The Sensor Node (Mountain)
* **Arduino Uno R3:** The main microcontroller that reads the sensors.
* **Rain Gauge (Tipping Bucket):** Measures exactly how much rain is falling.
* **Soil Moisture Sensors (2x):** Placed in the ground to measure how wet and heavy the soil is getting.
* **MPU6050 Module:** A motion sensor that detects if the ground is tilting or shifting (an early sign of a landslide).
* **BME280 Module:** Measures air temperature, humidity, and atmospheric pressure.
* **LoRa Transmitter (SX1278):** A long-range radio antenna that sends the sensor data miles away to the base station.

### The Base Station (Barangay Hall)
* **Raspberry Pi 5:** A powerful mini-computer that runs the whole system.
* **LoRa Receiver (SX1278):** Catches the data sent from the mountain.
* **Power Supply / Backup Battery:** Keeps the Raspberry Pi running during blackouts.

---

## 5. Instructions for Use

Because Project Zara is built to be smart, using it is incredibly simple and requires no programming knowledge once it is set up.

### Step 1: Powering On
1. Plug in the **Base Station (Raspberry Pi)** at the Barangay Hall. It will turn on and automatically start working in the background.
2. Ensure the **Sensor Node** on the mountain has battery/solar power.

### Step 2: Connecting to the System
The Raspberry Pi acts like its own Wi-Fi router. You do not need internet to use it!
1. Take any smartphone, tablet, or laptop.
2. Go to your Wi-Fi settings and connect to the network named: **`Iraya_BaseStation`**
3. Enter the password: **`iraya1234`**
 *(Note: Your phone might say "No Internet Connection." This is normal. Just tap "Keep Connection".)*

### Step 3: Viewing the Dashboard
1. Open a web browser (like Google Chrome or Safari).
2. In the address bar at the top, type exactly: **`http://192.168.4.1`** and press Go.
3. The Project Zara Dashboard will appear on your screen!

### Step 4: Reading the Dashboard
The dashboard will show you a big, color-coded risk level:
* 🟢 **SAFE (Green):** Normal weather. No action needed.
* 🟡 **CAUTION (Amber):** Rain is starting. Monitor the situation.
* 🟠 **WARNING (Orange):** Heavy rain or very wet soil. Prepare for possible evacuation.
* 🔴 **DANGER (Red):** Extreme danger or ground movement detected. **EVACUATE IMMEDIATELY.**

**If an alert pops up on the screen (like a Warning or Danger alert), tap the "Acknowledge" button so the system knows you have seen it.**

---

## 6. Troubleshooting
* **I can't reach the dashboard:** Make sure you are connected to the `Iraya_BaseStation` Wi-Fi, not your home Wi-Fi. Double-check that you typed `http://192.168.4.1` correctly.
* **No data from the mountain:** Check if the Sensor Node on the mountain has power. Heavy storms might also temporarily block radio signals.
* **The Raspberry Pi turned off:** Check the power cable. If there is a blackout, ensure it is connected to a backup battery or generator.
