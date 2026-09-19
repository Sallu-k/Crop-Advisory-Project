# Hardware Folder — Setup Instructions

## What's in this folder

| File | What it is |
|---|---|
| `block_diagram.svg` | System-level architecture: field node → backend → LLM → Twilio → farmer |
| `flow_diagram.svg` | Firmware logic flowchart: what the ESP32 does step by step in `loop()` |
| `circuit_diagram.svg` | Wiring diagram: exact pin connections between ESP32 and each sensor |
| `config.h` | Your Wi-Fi credentials, backend URL, pin numbers, sowing date |
| `crop_advisory_node.ino` | Main firmware — reads sensors, POSTs to backend |
| `soil_calibration.ino` | Run this first to calibrate your soil moisture sensor |

## Step 1 — Wire it up

Open `circuit_diagram.svg` (any browser opens SVGs directly) and follow the
connections shown:

- **DHT22**: VCC → 3V3, GND → GND, DATA → GPIO4 (add a 10kΩ resistor between
  DATA and VCC if your module doesn't already have one built in)
- **Capacitive soil moisture sensor**: VCC → 3V3, GND → GND, AOUT → GPIO34
- **FC-37 rain sensor**: VCC → 3V3, GND → GND, AOUT → GPIO35
- **BH1750 (optional)**: VCC → 3V3, GND → GND, SDA → GPIO21, SCL → GPIO22

All grounds are common — connect every sensor's GND to the same ground rail
as the ESP32.

## Step 2 — Install Arduino IDE support for ESP32

1. Open Arduino IDE → **File → Preferences** → in "Additional Board Manager
   URLs" add:
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
2. Go to **Tools → Board → Boards Manager**, search "esp32", install the
   package by Espressif Systems.
3. Select **Tools → Board → ESP32 Dev Module**.
4. Select the correct **Port** once your board is plugged in via USB.

## Step 3 — Install required libraries

In Arduino IDE, go to **Sketch → Include Library → Manage Libraries** and
install:
- **DHT sensor library** (by Adafruit)
- **Adafruit Unified Sensor** (installs automatically as a dependency)
- **ArduinoJson** (by Benoit Blanchon)
- **BH1750** (by Christopher Laws) — only needed if you're using the light sensor

## Step 4 — Calibrate the soil moisture sensor

1. Open `soil_calibration.ino` in Arduino IDE, upload it to your ESP32.
2. Open **Tools → Serial Monitor**, set baud rate to `115200`.
3. Hold the sensor in dry air — note the number it prints. This is your
   `SOIL_ADC_DRY` value.
4. Submerge the sensor tip fully in a glass of water — note that number.
   This is your `SOIL_ADC_WET` value.
5. Open `config.h` and replace the placeholder `SOIL_ADC_DRY` /
   `SOIL_ADC_WET` values with your real numbers.

This step matters — skipping it means your moisture percentage readings
will be meaningless, since every sensor unit reads slightly differently.

## Step 5 — Fill in config.h

Open `config.h` and set:
- `WIFI_SSID` / `WIFI_PASSWORD` — your Wi-Fi hotspot credentials
- `BACKEND_URL` — your deployed Render URL with `/sensor-data` at the end
  (e.g. `https://crop-advisory-backend-xxxx.onrender.com/sensor-data`)
- `SOWING_YEAR` / `SOWING_MONTH` / `SOWING_DAY` — the date you're treating
  as the paddy sowing date for this demo
- The calibrated `SOIL_ADC_DRY` / `SOIL_ADC_WET` values from Step 4

## Step 6 — Upload and test the main firmware

1. Open `crop_advisory_node.ino` in Arduino IDE (make sure `config.h` is in
   the same folder — Arduino IDE will show both as tabs).
2. Upload it to your ESP32.
3. Open Serial Monitor at `115200` baud. You should see it connect to
   Wi-Fi, sync time, then start printing sensor readings and confirming
   each POST to your backend every 5 minutes (or your configured interval).
4. Check your phone — each successful send should trigger a real call and
   SMS from the backend you already built.

## Testing tips

- **For faster demo testing**, temporarily lower `READING_INTERVAL_MS` in
  `config.h` (e.g. to `30000` for 30 seconds) so you don't have to wait
  5 minutes between readings while debugging. Set it back to something
  reasonable (like 5 minutes) before the actual showcase.
- **To simulate different scenarios live** (e.g. "dry soil" vs "normal"),
  physically dip the soil sensor in water or pull it out into dry air —
  the moisture reading will change in real time, which is a great visual
  moment for judges: wet the soil, watch the reading change, and a few
  seconds later your phone rings with an updated advisory.
- **Wi-Fi troubleshooting**: if the ESP32 keeps failing to connect, double
  check the SSID/password have no typos, and that you're on a 2.4GHz
  network — the ESP32 cannot connect to 5GHz-only Wi-Fi.
