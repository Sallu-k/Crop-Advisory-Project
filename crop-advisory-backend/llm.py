"""
Turns a list of ALERT CODES (not raw sensor numbers) into a short, natural
spoken voice message. This is a deliberately stronger constraint than
"paraphrase this JSON" -- the LLM never receives any number at all (no
temperature, no moisture %, no price), so it structurally CANNOT hallucinate
a wrong number, because it never has one to begin with. Numeric facts go
into the SMS via a separate deterministic template (see message_planner.py),
never through the LLM.
"""
import json
import requests
from config import GEMINI_API_KEY

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

ALERT_CODE_DESCRIPTIONS = {
    "LOW_MOISTURE": "The soil moisture is low. The farmer should check the field and irrigate if needed.",
    "EXCESS_MOISTURE": "The soil is showing high moisture. The farmer should check for standing water and drainage.",
    "FERTILIZER_DUE_BASAL": "It is time to apply the basal fertilizer dose at sowing.",
    "FERTILIZER_DUE_TILLERING": "It is time to apply the first nitrogen top-dressing, at the tillering stage.",
    "FERTILIZER_DUE_PANICLE": "It is time to apply the second nitrogen top-dressing, at panicle initiation stage.",
    "HARVEST_APPROACHING": "The crop is approaching its estimated harvest window in the coming days.",
    "HARVEST_CHECK_DUE": "The crop has reached its estimated harvest window. The farmer should check grain color and moisture before deciding to harvest.",
    "RAIN_WARNING": "Rain is forecast in the next few days, which may affect harvesting or field work.",
    "SENSOR_FAULT_DHT22": "The temperature and humidity sensor is not responding and should be checked.",
    "SENSOR_FAULT_SOIL": "The soil moisture sensor is not responding and should be checked.",
    "WEATHER_UNAVAILABLE": "Weather forecast data is temporarily unavailable.",
}

SYSTEM_INSTRUCTION_TEXT = """You are a language renderer, not an advisor.
You will be given a list of short plain-English alert descriptions that have
already been decided by an expert rule-based system. Your ONLY job is to
combine them into ONE short, warm, natural-sounding spoken message for a
farmer receiving a phone call.

Strict rules:
- Do NOT add any fact, number, date, or recommendation that is not present
  in the descriptions given to you.
- Do NOT invent numbers, percentages, prices, or measurements of any kind.
- Do NOT omit any of the given alert descriptions.
- Keep the message under 40 seconds when spoken aloud (roughly 90-110 words maximum).
- Speak directly to the farmer, e.g. "Your paddy field..." not "The farmer's field...".
- Begin with a brief greeting and end with a brief closing.
"""


def generate_voice_message(alert_codes: list, language_note: str = "English") -> str:
    """
    Renders the given alert codes into a spoken message. Falls back to a
    simple deterministic template (no LLM) if the API call fails, so a rate
    limit or network issue on demo day never breaks delivery.
    """
    descriptions = [ALERT_CODE_DESCRIPTIONS.get(code, code) for code in alert_codes]

    if not descriptions:
        return ""

    try:
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION_TEXT}]},
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                f"Render this in {language_note}. Alert descriptions (JSON):\n"
                                f"{json.dumps(descriptions, ensure_ascii=False)}"
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 250},
        }
        response = requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        message = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return message
    except Exception as e:
        print(f"[llm.py] Gemini call failed, using fallback template: {e}")
        return _fallback_voice_message(descriptions)


def _fallback_voice_message(descriptions: list) -> str:
    """A deterministic, no-LLM backup message -- just joins the descriptions."""
    if not descriptions:
        return ""
    intro = "Hello, this is your farm advisory. "
    body = " ".join(descriptions)
    outro = " Thank you."
    return intro + body + outro
