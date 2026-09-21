"""
Builds the two outgoing messages from a set of alert codes + facts:

  - VOICE message: short, LLM-rendered, alert-codes-only (see llm.py) --
    no raw numbers, kept under ~40 seconds spoken.
  - SMS message: longer, fully deterministic (no LLM at all), includes the
    actual numbers (moisture index, temperature, mandi price) since SMS is
    read at the farmer's own pace and numbers matter there.

This split means: language generation is the LLM's job, numeric facts are
always handled by plain code. Neither one does the other's job.
"""
from llm import generate_voice_message, ALERT_CODE_DESCRIPTIONS


def build_voice_message(alert_codes: list) -> str:
    return generate_voice_message(alert_codes)


def build_sms_message(alert_codes: list, facts: dict) -> str:
    lines = ["CROP ADVISORY - Paddy"]

    if facts.get("soil_moisture_index") is not None:
        lines.append(f"Soil moisture index: {facts['soil_moisture_index']:.0f}/100")
    if facts.get("temperature_c") is not None:
        lines.append(f"Temperature: {facts['temperature_c']:.1f}C")
    if facts.get("humidity_percent") is not None:
        lines.append(f"Humidity: {facts['humidity_percent']:.0f}%")
    if facts.get("light_level") is not None:
        lines.append(f"Ambient light index: {facts['light_level']:.0f}/100")

    lines.append("")
    lines.append("Alerts:")
    for code in alert_codes:
        if code == "WEATHER_UNAVAILABLE":
            continue  # already covered by the dedicated weather section below
        lines.append(f"- {ALERT_CODE_DESCRIPTIONS.get(code, code)}")

    weather_available = facts.get("weather_available")
    rain_expected = facts.get("rain_expected_next_days")
    if weather_available and rain_expected is not None:
        lines.append("")
        lines.append(
            "Rain expected in next 3 days." if rain_expected else "No significant rain expected in next 3 days."
        )
    elif not weather_available:
        lines.append("")
        lines.append("(Weather forecast unavailable right now.)")

    mandi = facts.get("mandi") or {}
    if mandi.get("available"):
        lines.append("")
        lines.append(
            f"Mandi ({mandi.get('market', 'unknown market')}, {mandi.get('arrival_date', 'date unknown')}): "
            f"Rs {mandi.get('modal_price')}/quintal"
        )

    lines.append("")
    lines.append(f"Rule version: {facts.get('rule_version', 'unknown')}")

    return "\n".join(lines)
