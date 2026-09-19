"""
Fetches today's mandi (market) price for the configured commodity/district using
the data.gov.in Agmarknet dataset API.

Resource ID used: 9ef84268-d588-465a-a308-a864a43d0070
(Current daily price of various commodities from various markets - Mandi)
"""
import requests
from config import DATA_GOV_API_KEY, MANDI_STATE, MANDI_DISTRICT, MANDI_COMMODITY

MANDI_API_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"


def get_mandi_price():
    """
    Returns the modal price (Rs per quintal) as a float, or None if unavailable.
    Never raises -- a failed lookup should not break the rest of the pipeline.
    """
    try:
        params = {
            "api-key": DATA_GOV_API_KEY,
            "format": "json",
            "limit": 10,
            "filters[state]": MANDI_STATE,
            "filters[district]": MANDI_DISTRICT,
            "filters[commodity]": MANDI_COMMODITY,
        }
        response = requests.get(MANDI_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        records = data.get("records", [])
        if not records:
            return None
        modal_price = records[0].get("modal_price")
        return float(modal_price) if modal_price else None
    except Exception as e:
        print(f"[mandi.py] Mandi price API call failed: {e}")
        return None
