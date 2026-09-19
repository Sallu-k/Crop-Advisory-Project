# Voice-First Crop Advisory System

Full project repo: backend pipeline (this root folder) + ESP32 hardware/firmware
(in `hardware/`, with its own [hardware/README.md](hardware/README.md) and
wiring/flow/block diagrams).

This root README covers the **backend** — everything is already written,
follow the steps below to save it, run it, and test it end-to-end. For
wiring the sensors and flashing the ESP32, see `hardware/README.md` instead.

## What's in this folder

| File | What it does |
|---|---|
| `main.py` | The FastAPI app — the entry point that ties everything together |
| `rule_engine.py` | The "brain" — paddy sowing/fertilizer/harvest logic (no AI, pure rules) |
| `weather.py` | Calls the free Open-Meteo API for rain forecast |
| `mandi.py` | Calls the data.gov.in Agmarknet API for today's paddy price |
| `llm.py` | Calls Gemini to turn the rule engine's facts into a spoken message |
| `telephony.py` | Calls Twilio to make the voice call and send the SMS |
| `config.py` | Loads all your API keys/settings from the `.env` file |
| `requirements.txt` | List of Python packages needed |
| `.env.example` | Template showing which keys to fill in |

## Step 1 — Save the files

1. Create a folder on your computer called `crop-advisory-backend`.
2. Save each file above into that folder, using the exact filenames shown
   (including `main.py`, `rule_engine.py`, etc.) — copy the content exactly
   as given.
3. Copy `.env.example`, rename the copy to `.env`, and fill in your real
   values:
   - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` — from your Twilio console
   - `TWILIO_FROM_NUMBER` — your Twilio number (with country code, e.g. `+1...`)
   - `TWILIO_TO_NUMBER` — your verified personal number (e.g. `+91...`)
   - `GEMINI_API_KEY` — from Google AI Studio
   - `DATA_GOV_API_KEY` — leave blank if you haven't found yours yet; a public
     demo key is already built in as a fallback

## Step 2 — Run it on your own computer first

Open a terminal inside the `crop-advisory-backend` folder and run:

```bash
python -m venv venv
```

Activate it:
- Windows: `venv\Scripts\activate`
- Mac/Linux: `source venv/bin/activate`

Install the required packages:

```bash
pip install -r requirements.txt
```

Start the server:

```bash
uvicorn main:app --reload
```

You should see something like `Uvicorn running on http://127.0.0.1:8000`.

## Step 3 — Test it locally

Open your browser and go to:

```
http://127.0.0.1:8000/test-advisory-no-call
```

This runs the full pipeline (rule engine + weather + mandi price + Gemini
message generation) **without** placing a real call or SMS — use this first
to confirm everything except Twilio is working, and to read the generated
`message` field in the response.

Once that looks correct, test the real delivery:

```
http://127.0.0.1:8000/test-advisory
```

This does the same thing but **also places a real voice call and sends a
real SMS** to your verified number (`TWILIO_TO_NUMBER`). Your phone should
ring within a few seconds and read out the advisory message, and you should
also receive an SMS with the same text.

If you want to test with your own custom sensor values instead of the
built-in sample, go to `http://127.0.0.1:8000/docs`, find the `POST
/sensor-data` endpoint, click "Try it out," and enter values like:

```json
{
  "soil_moisture": 15,
  "temperature": 31,
  "humidity": 70,
  "days_since_sowing": 45
}
```

Try a few different `days_since_sowing` and `soil_moisture` values to see
the message change (e.g. low moisture triggers an irrigation alert, day 45
triggers a fertilizer alert, day 110+ triggers a harvest alert).

## Step 4 — Save it to GitHub

```bash
git init
git add .
git commit -m "Complete backend pipeline"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

Your `.env` file will **not** be uploaded (it's excluded by `.gitignore`) —
that's intentional, so your real keys never end up on GitHub.

## Step 5 — Deploy to Render (so it has a public URL)

1. Go to your Render dashboard → **New → Web Service**.
2. Connect the GitHub repo you just pushed to.
3. Set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Go to the **Environment** tab and add each variable from your `.env`
   file one by one (same names: `TWILIO_ACCOUNT_SID`, `GEMINI_API_KEY`,
   etc.) — this is how your real keys get to the live server safely.
5. Click **Deploy**. Wait for the build to finish (a few minutes).
6. Once deployed, you'll get a URL like
   `https://crop-advisory-backend-xxxx.onrender.com`.
7. Test it exactly the same way as locally, just using that URL instead of
   `127.0.0.1:8000` — e.g.
   `https://crop-advisory-backend-xxxx.onrender.com/test-advisory-no-call`

## Troubleshooting

- **Call/SMS doesn't arrive:** Double-check `TWILIO_TO_NUMBER` is exactly
  your verified number (with country code) and that you haven't hit
  Twilio's trial daily message cap.
- **Gemini call fails silently:** Check the terminal/Render logs — if
  Gemini fails for any reason, the code automatically falls back to a
  plain templated message instead of crashing, so the call/SMS will still
  go out, just with simpler wording.
- **Mandi price shows as `null`:** This is expected sometimes — not every
  mandi reports prices every day, and Sundays/holidays have no data. The
  pipeline handles this gracefully and just leaves that part out of the
  message.
- **"ModuleNotFoundError"**: Make sure your virtual environment is
  activated (`venv\Scripts\activate` or `source venv/bin/activate`) before
  running `pip install` or `uvicorn`.

## What this proves for your demo

By the end of this, you have a live, public backend URL that takes sensor
data and produces a real, factually-grounded phone call. Once your ESP32
hardware is built, it just needs to `POST` its readings to
`https://your-app.onrender.com/sensor-data` — nothing else in this backend
needs to change.
