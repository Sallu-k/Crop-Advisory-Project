# Crop Advisory IoT System

An IoT-based crop advisory platform that combines field sensing, rule-based agricultural decision logic, weather data, market information, and SMS delivery to provide actionable crop advisories.

> **Prototype:** This system is a proof-of-concept. Agronomic thresholds require validation against the target crop variety, local soil conditions, and region-specific agricultural recommendations before real-world deployment.

---

## Overview

The system connects an ESP32-based field node to a Python backend that processes environmental readings and determines relevant agricultural conditions.

The platform is designed around a simple principle:

**Sense → Validate → Analyse → Advise → Deliver**

Field measurements are evaluated using deterministic, versioned rules. Relevant advisories are then delivered to configured recipients through SMS.

The architecture also includes weather cross-verification, multilingual messaging, delivery management, a monitoring dashboard, and reproducible demonstration scenarios.

---

## System Architecture

```text
┌──────────────────────┐
│     ESP32 Node       │
│                      │
│ Soil / Environmental │
│      Sensors         │
└──────────┬───────────┘
           │
           │ HTTP
           ▼
┌──────────────────────┐
│    FastAPI Backend   │
│                      │
│ Validation           │
│ State Management     │
│ Rule Engine          │
│ Advisory Generation  │
└───────┬───────┬──────┘
        │       │
        │       ├──────────────► Weather Data
        │       │
        │       └──────────────► Mandi Data
        │
        ▼
┌──────────────────────┐
│   Delivery Layer     │
│                      │
│ SMS / Voice          │
│ Multi-recipient      │
│ Retry & Backoff      │
└──────────┬───────────┘
           │
           ▼
     Farmer / Users

           ▲
           │
┌──────────┴───────────┐
│     Web Dashboard    │
│                      │
│ Live readings        │
│ Active alerts        │
│ Delivery status      │
│ Demonstration tools  │
└──────────────────────┘
```

---

## Key Capabilities

### Deterministic Advisory Engine

Agricultural decisions are generated through versioned rules rather than relying on an LLM to interpret raw sensor values.

The system supports:

- Soil-moisture condition detection
- Hysteresis-based threshold handling
- Sensor-fault detection
- Fertilizer timing advisories
- Harvest-related decision-support signals
- Rain-versus-irrigation cross-verification
- Rule version tracking

### Intelligent Alert Management

The system does not repeatedly notify users for an unchanged condition.

State-change detection and configurable cooldown periods prevent unnecessary SMS delivery while allowing new or persistent conditions to be communicated.

### Sensor Fault Handling

Invalid or unavailable sensor measurements are treated as faults rather than being replaced with fabricated values.

For example, a failed DHT22 reading is represented as a sensor fault instead of generating a plausible temperature or humidity value.

### Weather Cross-Verification

Excess-moisture conditions can be cross-checked against observed rainfall data before generating the advisory.

The system distinguishes between:

- Rain-confirmed moisture
- Likely irrigation
- Unknown weather condition

### Multi-recipient Delivery

Advisories can be delivered to multiple configured recipients.

Each recipient has an independent delivery job, allowing retry and backoff handling without one failed recipient blocking other deliveries.

### Multilingual SMS

Built-in SMS templates support:

- English
- Hindi
- Kannada

Numeric values are inserted programmatically rather than translated through an LLM.

### Live Monitoring Dashboard

The dashboard provides:

- Latest field readings
- Active alerts
- Last SMS status
- Delivery information
- Demonstration controls
- Language selection
- Simulated advisory scenarios

### Reproducible Demonstration Scenarios

Named demonstration scenarios allow specific advisory conditions to be reproduced without waiting for the corresponding physical condition to occur naturally.

This provides a controlled way to demonstrate the system during presentations and evaluations.

---

## Engineering Approach

A key design decision is separating **agricultural decision logic** from **language generation and message delivery**.

```text
Sensor Data
    │
    ▼
Validation
    │
    ▼
Rule Engine
    │
    ├──► Alert Code
    │
    ├──► Rule Version
    │
    └──► Supporting Facts
             │
             ▼
      Message Planner
             │
        ┌────┴────┐
        ▼         ▼
       SMS      Voice
```

The LLM is not responsible for determining agricultural thresholds or inventing numerical measurements.

This keeps the core advisory path deterministic and auditable.

---

## Technology Stack

### Backend

- Python
- FastAPI
- Pydantic
- Uvicorn

### Embedded

- ESP32
- Arduino framework
- Environmental sensors
- Soil-moisture sensing
- HTTP communication

### External Services

- Twilio / TextBee for SMS delivery
- Open-Meteo for weather information
- data.gov.in for mandi information
- Gemini for voice-message language rendering

### Testing

- Pytest
- API tests
- Rule-engine tests
- Integration tests
- Dashboard tests
- Regression tests

---

## Repository Structure

```text
crop-advisory-iot-system/
│
├── agronomy/
│   ├── paddy_profile.py
│   └── AGRONOMY_SOURCES.md
│
├── hardware/
│   ├── crop_advisory_node/
│   ├── analog_sensor_calibration.ino
│   ├── soil_calibration.ino
│   ├── circuit_diagram.svg
│   ├── block_diagram.svg
│   └── flow_diagram.svg
│
├── repositories/
│
├── services/
│
├── tests/
│
├── main.py
├── rule_engine.py
├── state_manager.py
├── message_planner.py
├── sms_i18n.py
├── telephony.py
├── weather.py
├── mandi.py
├── dashboard.py
├── config.py
├── database.py / db_models.py
├── .env.example
├── requirements.txt
├── start_server.bat
├── V5_UPGRADE_GUIDE.md
└── README.md
```

---

## Hardware

The field node is based on an ESP32 and communicates sensor readings to the backend over HTTP.

Hardware documentation and diagrams are available in:

```text
hardware/
```

This directory contains:

- Firmware
- Sensor calibration programs
- Circuit diagram
- System block diagram
- System flow diagram
- Hardware configuration template

Private credentials are intentionally excluded from the repository.

---

## Backend Components

| Component | Responsibility |
|---|---|
| `main.py` | FastAPI application and request handling |
| `models.py` | Input validation |
| `rule_engine.py` | Agricultural decision logic |
| `state_manager.py` | State-change and cooldown management |
| `message_planner.py` | Advisory message construction |
| `sms_i18n.py` | Multilingual SMS templates |
| `telephony.py` | SMS and voice delivery |
| `weather.py` | Weather and rainfall data |
| `mandi.py` | Market-price data |
| `dashboard.py` | Monitoring and demonstration interface |
| `config.py` | Environment-based configuration |
| `agronomy/` | Versioned crop rules and sources |
| `tests/` | Automated test suite |

---

## Security

Credentials are not stored directly in the source code.

Runtime configuration is supplied through environment variables and private hardware configuration.

The repository includes:

```text
.env.example
hardware/config.example.h
hardware/crop_advisory_node/config.example.h
```

while sensitive and local files such as:

```text
.env
config.h
crop_advisory.db
```

are excluded through `.gitignore`.

Device requests are protected using a shared device key, and incoming data is subject to validation and duplicate-sequence checks.

---

## Getting Started

> Upgrading from v4? See [V5_UPGRADE_GUIDE.md](V5_UPGRADE_GUIDE.md) for exactly what changed.
> Hardware wiring, calibration and flashing are covered in [hardware/README.md](hardware/README.md).

### Step 1 — Install dependencies

```bash
python -m venv venv
```

Activate it (`venv\Scripts\activate` on Windows, `source venv/bin/activate` on Mac/Linux), then:

```bash
pip install -r requirements.txt        # add requirements-dev.txt to run the tests
```

### Step 2 — Fill in your `.env`

Copy `.env.example` to `.env` and fill in:

- Your SMS provider keys (Twilio or textbee, see below) and the Gemini key if voice is on
- `EXPECTED_DEVICE_KEY`, which must match `DEVICE_KEY` in the ESP32's `config.h`
- `SOWING_DATE`
- **Recipients.** `ADVISORY_TO_NUMBER` takes a single number. `ADVISORY_TO_NUMBERS` takes a comma-separated list (`+919876543210,+919812345678`), and each number gets its own delivery job with independent retry/backoff.
- **Alert cadence.** `ALERT_COOLDOWN_MINUTES` defaults to `360`, so an unchanged condition repeats every 6 hours (about 4 updates a day). For a live demo where you want to see repeats quickly, set it to `5`.

For the ESP32, copy `hardware/crop_advisory_node/config.example.h` to `config.h` in the same folder and fill in the Wi-Fi details, `BACKEND_URL` and `DEVICE_KEY`. `config.h` is git-ignored and must never be committed.

### Step 3 — Run the tests (no network needed)

```bash
pytest tests/ -v
```

Every test should pass. The tests cover every threshold (hysteresis enter/exit points, fertilizer windows, harvest timing, sensor-fault handling), the API, the dashboard, the delivery queue and the SMS timing rules. None of them need real API keys or internet access, and none can send an SMS.

### Step 4 — Run the server locally

On Windows, double-click **`start_server.bat`** or run it from a terminal. It starts the server with `--host 0.0.0.0`, which is what lets the ESP32 reach it. The equivalent command is:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Plain `uvicorn main:app` only listens on this PC, so an ESP32 could never reach it. Run a single server process.

Device, reading, alert and delivery state is stored in SQLite (`crop_advisory.db`, set by `DATABASE_URL`). It is created on first start, survives restarts and is git-ignored.

#### Prototype in a room (ESP32 + this PC on one Wi-Fi)

1. Put the ESP32 and this PC on the **same Wi-Fi network**. The ESP32 only supports 2.4 GHz. School and office networks often isolate devices from each other or use a login page, so if the ESP32 can't reach the PC, put both on a phone hotspot.
2. Find the PC's IPv4 address (`ipconfig` → "IPv4 Address") and put it in `hardware/crop_advisory_node/config.h`:
   `#define BACKEND_URL "http://192.168.x.x:8000/sensor-data"`.
   The address can change when the router hands out a new one, so re-check it if readings stop arriving.
3. Allow the port through Windows Firewall. Do this once, in an **Administrator** terminal:
   ```
   netsh advfirewall firewall add rule name="CropAdvisory8000" dir=in action=allow protocol=TCP localport=8000 profile=any
   ```
4. From a phone on the same Wi-Fi, open `http://<PC-IP>:8000/dashboard`. The page should load.
5. Flash the ESP32. The Serial Monitor should show a reading every 15 s, and the dashboard's "Last update" should stay under about 15 s.

**When SMS are sent:** a new condition or an error (dry soil, too wet, a sensor fault…) is texted immediately. While the condition lasts, it is texted again every `ALERT_COOLDOWN_MINUTES` (default 360). A healthy field sends nothing. Fertilizer and harvest reminders repeat at most once a day (`TIME_BASED_ALERT_COOLDOWN_MINUTES`). You can also send one on demand from the dashboard's demo controls; those messages are marked `[TEST]`.

### Step 5 — Test the logic freely (costs zero SMS/calls)

Go to `http://127.0.0.1:8000/docs`, find **`POST /sensor-data-preview`**, and try different scenarios. It needs no device key, never delivers, and never touches your real device's cooldown state:

```json
{"device_id": "TEST", "sequence": 1, "soil_moisture": 15, "temperature": 30, "humidity": 65, "raining": false}
```

Try soil_moisture values in each hysteresis band (below 28, 28–35, above 75). Omit `temperature`/`humidity` to see sensor-fault handling.

### Step 6 — Confirm real delivery (uses SMS quota, so do it sparingly)

```
POST /sensor-data
```

Send it with the header `X-Device-Key: <your EXPECTED_DEVICE_KEY>` and a real body. Sending the **same** reading twice in a row does **not** trigger a second SMS. This is the state-change logic working as intended. To force a fresh alert, either change the values enough to cross a threshold, or use:

```
POST /demo/trigger
```

This also needs the `X-Device-Key` header. It fires a fixed low-moisture scenario for a repeatable live demo. By default it sends SMS only; it also places a voice call if `ENABLE_VOICE_CALL=true`.

### Step 7 — View the dashboard

```
http://127.0.0.1:8000/dashboard
```

The dashboard shows:

- The last reading
- Active alerts
- The last SMS, sent or failed, with its full text
- The last delivery status

It auto-refreshes every 15 seconds; use the "Refresh" link for an immediate refresh. If the field node stops reporting, after `STALE_AFTER_MINUTES` (2) the page says "No recent data" and dims the old numbers.

**Introducing a problem by hand (for a demo):**

1. Press **Enter access key** in the "Introduce a problem" panel.
2. Type your `EXPECTED_DEVICE_KEY`. This is the secret from `.env`, the same value as `DEVICE_KEY` in `config.h`, *not* the device name. The browser remembers it in a cookie until you press **Lock** or 12 hours pass.

Once unlocked, the panel offers:

- **A problem button** (DHT22 fault, low moisture, fertilizer due, …). It makes up a reading with that problem, sends its SMS marked `[TEST]`, and opens a **simulated** page. The banner reports whether the SMS was sent or failed, and an amber bar reminds you the numbers are made up.
- **Back to real values**, which returns to the real field readings. The real device and its alert state are never touched.
- **SMS language** chips (English / हिन्दी / ಕನ್ನಡ). These set the language of every SMS until the server restarts. To change the default, set `TRANSLATE_SMS_TO=en`, `hi` or `kn` in `.env`.

Never share a dashboard link that contains `?key=...`. If one leaks, rotate `EXPECTED_DEVICE_KEY`.

### Step 8 — Host it on a domain (Render)

Push to GitHub (never commit `.env` or `config.h`), create a **Web Service** on Render, and set:

- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT` (one worker only)

Add these under Render's **Environment** tab. Do not upload your `.env`.

| Variable | Value |
|---|---|
| `PUBLIC_MODE` | `true`. Refuses to start with a weak key, hides `/docs`, and protects the preview endpoint |
| `EXPECTED_DEVICE_KEY` | a **new long random key**: `python -c "import secrets; print(secrets.token_urlsafe(24))"` |
| `TZ` | `Asia/Kolkata`. Render runs in UTC; this keeps SMS times and the rain check correct |
| `PYTHON_VERSION` | `3.12.10` |
| `SMS_PROVIDER`, `TEXTBEE_API_KEY`, `TEXTBEE_DEVICE_ID` | as in your `.env` |
| `ADVISORY_TO_NUMBERS` | every number that should be reached, in international format (`+91...`) |
| `DATABASE_URL` | a Postgres URL (`postgresql+psycopg://...`) or a SQLite path on a persistent disk. Render's default disk is wiped on redeploy |
| `SOWING_DATE`, `LOCATION_NAME`, `TRANSLATE_SMS_TO`, … | as in your `.env` |

For your own domain, add it under the service's **Custom Domains** and create the DNS record Render shows. HTTPS is automatic.

**Point the ESP32 at it.** In `config.h`, set `#define BACKEND_URL "https://<your-domain>/sensor-data"` and `#define DEVICE_KEY "<the same new key>"`, then re-flash. Use the `https://` address directly, because an `http://` address that gets redirected will fail. The sketch encrypts the traffic but does not verify the server certificate; to verify it, pin a root certificate with `setCACert()`.

**What is public:** anyone with the address can *view* the dashboard. Sending SMS, changing the language and the preview endpoint all require the key.

---

## SMS providers: Twilio vs. textbee

Twilio trial accounts restrict SMS to predefined templates (error `572006`) and verified recipients. These are Twilio's documented limits, not bugs in this code. There are two ways around them:

1. **Upgrade Twilio.** A small minimum payment, typically about $20, removes both restrictions.
2. **Switch to textbee.** It is free and turns an Android phone into the SMS sender, using its own SIM. Install the app, register at textbee.dev, and in `.env` set `SMS_PROVIDER=textbee` and `TEXTBEE_API_KEY=...`. `telephony.py` routes to whichever provider is configured.

**Voice calls** are fully implemented (`telephony.py` + `llm.py`) but off by default (`ENABLE_VOICE_CALL=false`). Set it to `true` to enable them with no code changes. Gemini only ever receives alert codes, never raw numbers.

---

## Troubleshooting

- **401 Unauthorized on `/sensor-data`:** check that `X-Device-Key` matches `EXPECTED_DEVICE_KEY` exactly.
- **No SMS on a repeated reading:** this is expected; see Step 6 and `ALERT_COOLDOWN_MINUTES`.
- **Only one of several numbers receives SMS:** use `ADVISORY_TO_NUMBERS` (plural). The server logs a warning at startup for any entry that isn't in `+<country><number>` format.
- **Gemini call fails:** the system falls back to a deterministic template automatically, and delivery still proceeds. The logs give the reason.
- **Mandi price shows unavailable:** either `DATA_GOV_API_KEY` isn't set, or there is no record for that mandi/commodity/date today. That is expected on Sundays and holidays.

---

## Demo Guide

The agricultural decision comes from deterministic, versioned rules, and every response returns its `rule_version`. SMS text is built from deterministic templates with no LLM involved, so none of the numbers a farmer sees can be hallucinated.

A strong live demo sequence (set `ALERT_COOLDOWN_MINUTES=5` first):

1. **Action:** dip the soil sensor in water or dry it out, watch the dashboard change, and the SMS arrives.
2. **No action:** send the same reading again within a few minutes. The dashboard updates, but no second SMS arrives until the cooldown ends.
3. **Failure handling:** unplug the DHT22. The dashboard shows a sensor-fault alert instead of a fake reading.

---

## Limitations

This is a prototype and has several known limitations:

- Agricultural thresholds require field validation (see `agronomy/AGRONOMY_SOURCES.md`).
- Alert and delivery state is persisted in SQLite, but there are no schema migrations yet (`init_db()` is `create_all()`). Alembic is needed before real device history accumulates.
- The dashboard's SMS-language override lives in memory and resets on restart.
- Rate limiting is not implemented.
- Sensor silence shows on the dashboard ("No recent data") but does not trigger an SMS.
- HTTPS from the ESP32 does not perform certificate pinning.

---

## Project Status

**Current stage:** Functional prototype (v5)

The system currently includes:

- ESP32 field sensing
- Backend processing
- Deterministic advisory rules
- Sensor fault handling
- Weather cross-verification
- SMS delivery
- Multi-recipient delivery
- Multilingual SMS
- Live dashboard
- Demonstration scenarios
- Automated tests

---

## Authors

Built jointly as a co-authored project. v5 adds multi-recipient delivery and the production alert cadence on top of the shared v1–v4 foundation; see [V5_UPGRADE_GUIDE.md](V5_UPGRADE_GUIDE.md).
