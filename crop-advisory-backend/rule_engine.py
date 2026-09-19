"""
Deterministic rule engine for PADDY (Bhatkal / coastal Karnataka, Kharif season).

This is the "brain" of the project. It takes sensor + context data and returns
a structured dictionary of FACTS ONLY (no sentences). The LLM layer later turns
these facts into a spoken message -- it never decides anything itself.

Thresholds below are simplified, illustrative values based on general ICAR/KVK
paddy package-of-practices guidance (sowing window, fertilizer staging,
~110-120 days to maturity for typical varieties). For a real deployment these
would be sourced from your local KVK's exact variety-specific recommendation --
that caveat is worth stating openly in your demo.
"""

from datetime import date

# --- Reference data for Paddy (Kharif, coastal Karnataka) ---
SOWING_WINDOW = {
    "start_month": 6, "start_day": 1,    # June 1
    "end_month": 7, "end_day": 15,       # July 15
}

DAYS_TO_MATURITY = 115  # typical range 110-120 days after sowing for common varieties

# Fertilizer schedule: (days_after_sowing_range, stage_name, recommendation)
FERTILIZER_SCHEDULE = [
    (0, 0, "basal", "Apply basal dose of N-P-K fertilizer at the time of sowing/transplanting."),
    (18, 25, "tillering", "Apply first top-dressing of nitrogen fertilizer during the tillering stage."),
    (40, 50, "panicle_initiation", "Apply second top-dressing of nitrogen at panicle initiation stage."),
]

# Soil moisture thresholds (from the capacitive sensor's raw analog band, calibrated
# loosely to dry / moist / wet -- treat as qualitative, not a precise percentage)
MOISTURE_DRY_THRESHOLD = 30.0     # below this = needs irrigation
MOISTURE_WET_THRESHOLD = 70.0     # above this = waterlogged risk


def _is_within_sowing_window(today: date) -> bool:
    start = date(today.year, SOWING_WINDOW["start_month"], SOWING_WINDOW["start_day"])
    end = date(today.year, SOWING_WINDOW["end_month"], SOWING_WINDOW["end_day"])
    return start <= today <= end


def _fertilizer_status(days_since_sowing: int):
    for lo, hi, stage, message in FERTILIZER_SCHEDULE:
        if lo <= days_since_sowing <= hi:
            return {"stage": stage, "due": True, "recommendation": message}
    return {"stage": None, "due": False, "recommendation": None}


def _moisture_status(soil_moisture: float) -> str:
    if soil_moisture < MOISTURE_DRY_THRESHOLD:
        return "low"
    elif soil_moisture > MOISTURE_WET_THRESHOLD:
        return "high"
    return "normal"


def _harvest_status(days_since_sowing: int) -> dict:
    days_remaining = DAYS_TO_MATURITY - days_since_sowing
    ready = days_remaining <= 0
    approaching = 0 < days_remaining <= 10
    return {
        "days_remaining_estimate": max(days_remaining, 0),
        "ready_to_harvest": ready,
        "approaching_harvest": approaching,
    }


def evaluate(
    soil_moisture: float,
    temperature: float,
    humidity: float,
    days_since_sowing: int,
    rain_risk_next_3_days: bool = False,
    mandi_price: float = None,
) -> dict:
    """
    Main entry point. Returns a structured facts dictionary -- this is the ONLY
    source of truth that gets passed to the LLM for paraphrasing.
    """
    today = date.today()
    moisture_status = _moisture_status(soil_moisture)
    fertilizer = _fertilizer_status(days_since_sowing)
    harvest = _harvest_status(days_since_sowing)

    facts = {
        "crop": "paddy",
        "location": "Bhatkal",
        "date": today.isoformat(),
        "days_since_sowing": days_since_sowing,

        "in_sowing_window": _is_within_sowing_window(today),

        "moisture_status": moisture_status,
        "irrigation_needed": moisture_status == "low",
        "waterlogging_risk": moisture_status == "high",

        "temperature_c": temperature,
        "humidity_percent": humidity,

        "fertilizer_stage": fertilizer["stage"],
        "fertilizer_due": fertilizer["due"],
        "fertilizer_recommendation": fertilizer["recommendation"],

        "days_remaining_to_harvest_estimate": harvest["days_remaining_estimate"],
        "approaching_harvest": harvest["approaching_harvest"],
        "ready_to_harvest": harvest["ready_to_harvest"],

        "rain_risk_next_3_days": rain_risk_next_3_days,
        "harvest_rain_warning": harvest["approaching_harvest"] and rain_risk_next_3_days,

        "mandi_price_per_quintal": mandi_price,
    }
    return facts
