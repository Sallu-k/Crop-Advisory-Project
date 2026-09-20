"""
Loads all secrets/config from environment variables.
Locally these come from a .env file (via python-dotenv).
On Render, these come from the Environment Variables you set in the dashboard.

SECURITY NOTE: this file must contain zero hardcoded credentials or API
keys -- every real value comes from .env (which is gitignored) or Render's
environment settings. If a key is missing, the relevant feature degrades
gracefully (see weather.py / mandi.py) rather than the app crashing.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # reads .env file if present (does nothing on Render, which is fine)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
TWILIO_TO_NUMBER = os.getenv("TWILIO_TO_NUMBER", "")  # your verified personal number

# Voice + language for the phone call. Defaults to an English Indian voice.
# For a Kannada demo, switch to a supported Google Kannada voice, e.g.:
#   TWILIO_VOICE=Google.kn-IN-Standard-A
#   TWILIO_VOICE_LANGUAGE=kn-IN
# Note: Polly.Aditi (the previous default) is bilingual Hindi/Indian-English
# ONLY -- it is not a Kannada voice, so it must not be used for Kannada text.
TWILIO_VOICE = os.getenv("TWILIO_VOICE", "Polly.Aditi")
TWILIO_VOICE_LANGUAGE = os.getenv("TWILIO_VOICE_LANGUAGE", "en-IN")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# No hardcoded fallback key -- if this is missing, mandi.py returns
# "unavailable" instead of silently using a shared public key from source code.
DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY", "")

# Simple shared-secret header check so random internet requests can't trigger
# your phone. Not real security, just enough to stop accidental/abusive hits.
EXPECTED_DEVICE_KEY = os.getenv("EXPECTED_DEVICE_KEY", "")

# Location settings for Bhatkal, Karnataka (used for weather + mandi lookups)
LOCATION_NAME = os.getenv("LOCATION_NAME", "Bhatkal")
LOCATION_LAT = float(os.getenv("LOCATION_LAT", "13.9853"))
LOCATION_LON = float(os.getenv("LOCATION_LON", "74.5550"))
MANDI_STATE = os.getenv("MANDI_STATE", "Karnataka")
MANDI_DISTRICT = os.getenv("MANDI_DISTRICT", "Uttara Kannada")
MANDI_COMMODITY = os.getenv("MANDI_COMMODITY", "Paddy")

# Sowing date lives on the BACKEND now, not the firmware -- the ESP32 no
# longer needs NTP time sync just to compute days-since-sowing. Format: YYYY-MM-DD
SOWING_DATE = os.getenv("SOWING_DATE", "2026-06-15")

# How long (in minutes) to wait before re-alerting on the SAME condition,
# even if it's still active. Prevents repeated calls every 5 minutes for an
# unchanged condition. Set low (e.g. 1) only while actively testing.
ALERT_COOLDOWN_MINUTES = int(os.getenv("ALERT_COOLDOWN_MINUTES", "720"))  # 12 hours default
