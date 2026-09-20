"""
Fetches a short-range rain forecast using Open-Meteo (free, no API key required).
Docs: https://open-meteo.com/en/docs

IMPORTANT: on failure this returns {"available": False, "rain_expected": None},
NEVER {"rain_expected": False}. A failed API call means "we don't know", not
"no rain" -- silently treating unknown as "safe/no" is a real correctness bug,
not just a style choice, since it could suppress a genuine rain warning.
"""
import requests
from config import LOCATION_LAT, LOCATION_LON

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
RAIN_THRESHOLD_MM = 5.0


def get_weather() -> dict:
    """
    Returns a structured dict:
      {"available": True,  "rain_expected": bool, "forecast": [{"date": ..., "rain_mm": ...}, ...]}
      {"available": False, "rain_expected": None, "forecast": None}
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

        dates = data.get("daily", {}).get("time", [])
        rain_values = data.get("daily", {}).get("precipitation_sum", [])
        forecast = [
            {"date": d, "rain_mm": mm} for d, mm in zip(dates, rain_values)
        ]
        rain_expected = any(mm >= RAIN_THRESHOLD_MM for mm in rain_values)

        return {"available": True, "rain_expected": rain_expected, "forecast": forecast}
    except Exception as e:
        print(f"[weather.py] Weather API call failed, marking as unavailable: {e}")
        return {"available": False, "rain_expected": None, "forecast": None}
