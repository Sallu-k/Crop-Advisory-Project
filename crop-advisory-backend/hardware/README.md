# Hardware Folder — Setup Instructions (v2)

## What changed from v1

- **BH1750 light sensor removed.** It was never actually used by the
  advisory logic — three well-integrated sensors beat four half-integrated
  ones. If you want light data later, add it back deliberately.
- **No NTP time sync.** The ESP32 no longer needs to know the date at all —
  `days_since_sowing` is now computed on the backend from a configured
  sowing date (see the main `README.md`, `SOWING_DATE` in `.env`).
- **DHT22 failures are now honest.** If the sensor fails to read, the
  firmware **omits** temperature/humidity from the payload entirely
  (sent as absent/null) instead of quietly sending a fake default reading.
- **Soil moisture is now a 16-sample average**, reducing jitter.
- **The rain sensor reading is now actually sent** to the backend (in v1 it
  was read and printed but never transmitted).
- **`config.h` is now `config.example.h`.** Copy it to `config.h` yourself
  — `config.h` contains your real Wi-Fi password and device key, and is
  gitignored so it never gets committed.

## What's in this folder

| File | What it is |
|---|---|
| `block_diagram.svg` | System-level architecture (v2, includes the state manager) |
| `flow_diagram.svg` | Firmware logic flowchart — matches `crop_advisory_node.ino` exactly |
| `circuit_diagram.svg` | Wiring diagram: DHT22, soil moisture, rain sensor only |
| `config.example.h` | Template — copy to `config.h` and fill in your real values |
| `crop_advisory_node.ino` | Main firmware |
| `soil_calibration.ino` | Run this first to calibrate your soil moisture sensor |

## Step 1 — Wire it up

Open `circuit_diagram.svg` in any browser and follow the connections:

- **DHT22**: VCC → 3V3, GND → GND, DATA → GPIO4 (add a 10kΩ pull-up resistor
  between DATA and VCC if your module doesn't already have one built in)
- **Capacitive soil moisture sensor**: VCC → 3V3, GND → GND, AOUT → GPIO34
- **FC-37 rain sensor**: VCC → 3V3, GND → GND, AOUT → GPIO35

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

(BH1750 is no longer needed.)

## Step 4 — Calibrate the soil moisture sensor

1. Open `soil_calibration.ino` in Arduino IDE, upload it to your ESP32.
2. Open **Tools → Serial Monitor**, set baud rate to `115200`.
3. Hold the sensor in dry air — note the number it prints. This is your
   `SOIL_ADC_DRY` value.
4. Submerge the sensor tip fully in a glass of water — note that number.
   This is your `SOIL_ADC_WET` value.
5. Open `config.h` (see Step 5) and set those two values.

This step matters — skipping it means your moisture index will be
meaningless, since every sensor unit reads slightly differently. Also
note: this gives you a **relative moisture index**, not a laboratory
volumetric-water-content measurement — describe it that way in your pitch.

## Step 5 — Create and fill in config.h

1. Copy `config.example.h` and rename the copy to `config.h`.
2. Open `config.h` and set:
   - `WIFI_SSID` / `WIFI_PASSWORD` — your Wi-Fi hotspot credentials
   - `BACKEND_URL` — your deployed Render URL with `/sensor-data` at the end
   - `DEVICE_ID` — must match what your backend expects (default `FIELD-001`)
   - `DEVICE_KEY` — must match `EXPECTED_DEVICE_KEY` in your backend's `.env`
   - The calibrated `SOIL_ADC_DRY` / `SOIL_ADC_WET` values from Step 4

`config.h` is gitignored — it will never be committed, since it holds your
real Wi-Fi password and device key.

## Step 6 — Upload and test the main firmware

1. Open `crop_advisory_node.ino` in Arduino IDE (make sure `config.h` is in
   the same folder — Arduino IDE will show both as tabs).
2. Upload it to your ESP32.
3. Open Serial Monitor at `115200` baud. You should see it connect to
   Wi-Fi, then start printing sensor readings and confirming each POST to
   your backend every 5 minutes (or your configured interval).
4. Because of the backend's new state-change logic, you will **only** get a
   real call/SMS when a condition is NEW or has cleared its cooldown — an
   unchanged "still dry" reading every 5 minutes will NOT re-trigger a call.
   This is intentional (see the main README's "What changed" section).

## Testing tips

- **For faster demo testing**, temporarily lower `READING_INTERVAL_MS` in
  `config.h` (e.g. to `30000` for 30 seconds), and lower
  `ALERT_COOLDOWN_MINUTES` in the backend's `.env` (e.g. to `1`) so you can
  see repeated alerts fire during development. Set both back to realistic
  values (5 min / 720 min) before the actual showcase.
- **To simulate different scenarios live**, physically dip the soil sensor
  in water or pull it out into dry air — the moisture reading changes in
  real time. A good demo sequence: show it dry (triggers a call), then show
  it "still dry" a few minutes later (no second call — this proves the
  anti-spam fix works), then unplug the DHT22 (triggers an honest sensor-
  fault alert instead of fake data).
- **Wi-Fi troubleshooting**: double-check the SSID/password have no typos,
  and that you're on a 2.4GHz network — the ESP32 cannot connect to
  5GHz-only Wi-Fi.

## What was deliberately NOT built this week (and why)

- **Solar + battery power.** A 6V panel is not safely compatible with a
  typical 5V-input TP4056 charger without additional regulation — that's a
  real subsystem to design properly, not a one-week add-on. Use USB power
  for the prototype and mention solar as future work.
- **BH1750 / additional sensors.** Adding sensors the rule engine doesn't
  actually use just adds wiring risk for zero functional benefit.
