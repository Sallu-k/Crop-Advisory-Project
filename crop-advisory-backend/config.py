"""
Loads all secrets/config from environment variables.
Locally these come from a .env file (via python-dotenv).
On Render, these come from the Environment Variables you set in the dashboard.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # reads .env file if present (does nothing on Render, which is fine)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
TWILIO_TO_NUMBER = os.getenv("TWILIO_TO_NUMBER", "")  # your verified personal number

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# If you haven't found your personal data.gov.in key yet, this public demo key
# works but is capped at 10 records per request and rate-limited.
DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY", "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571")

# Location settings for Bhatkal, Karnataka (used for weather + mandi lookups)
LOCATION_NAME = os.getenv("LOCATION_NAME", "Bhatkal")
LOCATION_LAT = float(os.getenv("LOCATION_LAT", "13.9853"))
LOCATION_LON = float(os.getenv("LOCATION_LON", "74.5550"))
MANDI_STATE = os.getenv("MANDI_STATE", "Karnataka")
MANDI_DISTRICT = os.getenv("MANDI_DISTRICT", "Uttara Kannada")
MANDI_COMMODITY = os.getenv("MANDI_COMMODITY", "Paddy")
