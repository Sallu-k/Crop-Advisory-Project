# Voice-First Crop Advisory System (v2)

Full project repo: backend pipeline (this root folder) + ESP32 hardware/firmware
(in `hardware/`, with its own [hardware/README.md](hardware/README.md) and
wiring/flow/block diagrams).

> **Prototype status:** This is a proof-of-concept. Agronomic thresholds are
> illustrative and would need validation against the actual paddy variety,
> local soil conditions, and Bhatkal KVK recommendations before real
> deployment. See `agronomy/AGRONOMY_SOURCES.md` for exactly which numbers
> are sourced from where.

## What changed in v2 (responding to a full technical audit)

The original v1 backend worked, but had a real spam bug and several
honesty/security gaps. v2 fixes the highest-impact ones:

1. **State-change alerting, not every-reading alerting.** A field that stays
   dry for hours no longer triggers a phone call every 5 minutes — only a
   *new* condition, or one whose cooldown has expired, triggers delivery.
   See `state_manager.py`.
2. **Sensor faults are reported honestly, never faked.** If the DHT22 fails,
   the system says so (`SENSOR_FAULT_DHT22`) instead of sending a plausible
   fake temperature/humidity.
3. **Hysteresis, not a single threshold**, for soil moisture — prevents the
   system flickering between states when a reading sits near a boundary.
4. **The LLM only ever sees alert codes, never raw numbers** — it cannot
   hallucinate a wrong figure because it's never given one. All numeric
   facts (moisture index, temperature, mandi price) go into the SMS via a
   deterministic template, never through the LLM.
5. **"Harvest ready" became "harvest check due"** — a decision-support
   signal, not a command; the actual call is left to the farmer.
6. **Weather API failure means "unknown", never "no rain".** Silently
   turning an API failure into "safe/no" was a real correctness bug.
7. **Rule versioning + sourcing** — see `agronomy/`.
8. **Basic security**: a shared device-key header (`X-Device-Key`) so random
   requests can't trigger a real phone call, plus input-range validation and
   duplicate-sequence rejection. No API keys are hardcoded in source code
   anymore (previously a shared data.gov.in demo key was baked in).
9. **Separate voice (short) and SMS (detailed) messages**, instead of one
   long message read aloud on both channels.
10. **A tiny live dashboard** at `/dashboard` for demo day.

## What's in this folder

| File / folder | What it does |
|---|---|
| `main.py` | FastAPI app — ties everything together, handles auth + dedup |
| `models.py` | Input validation (range limits, required fields) |
| `rule_engine.py` | The "brain" — hysteresis, sensor-fault detection, versioned rules |
| `state_manager.py` | State-change + cooldown logic (the anti-spam fix) |
| `message_planner.py` | Builds separate voice (short) vs SMS (detailed) messages |
| `llm.py` | Gemini call — sees alert codes only, never raw numbers |
| `telephony.py` | Twilio voice call + SMS, independent error handling |
| `weather.py` | Open-Meteo rain forecast — "unavailable" is distinct from "no rain" |
| `mandi.py` | data.gov.in mandi price lookup — full record detail, no hardcoded key |
| `dashboard.py` | Simple live-status HTML page |
| `config.py` | Loads all settings from `.env` — zero hardcoded credentials |
| `agronomy/` | Versioned crop rules + `AGRONOMY_SOURCES.md` documenting where every number comes from |
| `tests/test_rules.py` | Boundary tests for every threshold (run with `pytest`) |

## Step 1 — Save the files and install dependencies

```bash
python -m venv venv
```
Activate it (`venv\Scripts\activate` on Windows, `source venv/bin/activate` on Mac/Linux), then:
```bash
pip install -r requirements.txt
```

## Step 2 — Fill in your `.env`

Copy `.env.example` → rename to `.env` → fill in your real Twilio/Gemini
keys, `EXPECTED_DEVICE_KEY` (must match your ESP32's `config.h`), and
`SOWING_DATE`.

## Step 3 — Run the tests (no network needed)

```bash
pytest tests/ -v
```
All 13 boundary tests should pass — these check every threshold (hysteresis
enter/exit points, fertilizer windows, harvest timing, sensor-fault
handling) without needing any real API keys or internet access.

## Step 4 — Run the server locally

```bash
uvicorn main:app --reload
```

## Step 5 — Test the logic freely (costs ZERO SMS/calls)

Go to `http://127.0.0.1:8000/docs`, find **`POST /sensor-data-preview`**,
and try different scenarios — no device key needed, never delivers, never
touches your real device's cooldown state:

```json
{"device_id": "TEST", "sequence": 1, "soil_moisture": 15, "temperature": 30, "humidity": 65, "raining": false}
```

Try soil_moisture values across the hysteresis bands (below 28, 28–35,
above 75), omit `temperature`/`humidity` to see sensor-fault handling, etc.

## Step 6 — Confirm real delivery (uses Twilio quota — do sparingly)

```
POST /sensor-data
```
with header `X-Device-Key: <your EXPECTED_DEVICE_KEY>` and a real body.
Because of the state-change logic, sending the **same** reading twice in a
row will **not** trigger a second call — this is intentional, not a bug.
To force a fresh demo call, either change the values enough to cross a
threshold, or use:
```
POST /demo/trigger
```
(also requires the `X-Device-Key` header) — a fixed low-moisture scenario
for a repeatable live demo.

## Step 7 — View the dashboard

```
http://127.0.0.1:8000/dashboard
```
Shows the last reading, active alerts, and last delivery status. Auto-
refreshes every 15 seconds — good to have open during a live demo.

## Step 8 — Deploy to Render

Push to GitHub, connect the repo on Render, set:
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

Add every variable from `.env` under Render's **Environment** tab.

**Known limitation (stated honestly):** the state/cooldown store is
in-memory. If Render's free tier restarts your process (e.g. after
inactivity), that state resets. This is an accepted simplification for a
one-week prototype — a real deployment would use a small persistent store
(SQLite/Redis) instead; the architecture already isolates this into
`state_manager.py` specifically so that swap is a one-file change later.

## Troubleshooting

- **401 Unauthorized on `/sensor-data`**: check that `X-Device-Key` matches
  `EXPECTED_DEVICE_KEY` exactly.
- **No call/SMS on a repeated reading:** expected — see Step 6.
- **Gemini call fails silently:** falls back to a deterministic template
  automatically — check logs for the reason, but delivery still proceeds.
- **Mandi price shows unavailable:** either `DATA_GOV_API_KEY` isn't set, or
  that mandi/commodity/date combination has no record today (expected on
  Sundays/holidays).

## For your demo pitch

Don't say "Gemini analyzes the field and tells the farmer what to do." Say:
"The agricultural decision is produced by deterministic, versioned rules
(`rule_version` is returned with every response). Gemini is used only to
turn that already-decided alert into a short, natural spoken message — it
never sees a single raw number, so it structurally cannot invent one. If
Gemini fails, the system falls back to a plain template automatically."

A strong live demo sequence:
1. **Action** — dip the soil sensor in water/dry it out → watch the
   dashboard change → phone rings.
2. **No-action** — same dry reading again a few minutes later → dashboard
   updates, but no second call (the anti-spam fix, visibly proven).
3. **Failure handling** — unplug the DHT22 → dashboard shows a sensor-fault
   alert instead of a fake reading.
