"""
Fetches a short-range rain forecast using Open-Meteo (free, no API key required).
Docs: https://open-meteo.com/en/docs
"""
import requests
from config import LOCATION_LAT, LOCATION_LON

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def get_rain_risk_next_3_days() -> bool:
    """
    Returns True if meaningful rain (>= 5mm on any of the next 3 days) is forecast.
    Falls back to False (no known rain risk) if the API call fails, so a network
    hiccup never crashes the whole advisory pipeline.
    """
    try:
        params = {
            "latitude": LOCATION_LAT,
            "longitude": LOCATION_LON,
            "daily": "precipitation_sum",
            "forecast_days": 3,
            "timezone": "Asia/Kolkata",
        }
        response = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        daily_precip = data.get("daily", {}).get("precipitation_sum", [])
        return any(mm >= 5.0 for mm in daily_precip)
    except Exception as e:
        print(f"[weather.py] Weather API call failed, defaulting to no rain risk: {e}")
        return False
