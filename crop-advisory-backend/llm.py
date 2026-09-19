"""
Turns the rule engine's structured FACTS into a short, natural-language spoken
advisory. The LLM is deliberately constrained to a PARAPHRASE-ONLY role: it must
never invent, infer, or add any fact not present in the JSON it is given. This
is the anti-hallucination guardrail for the whole project.
"""
import requests
from config import GEMINI_API_KEY

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

SYSTEM_INSTRUCTION = """You are a translator, not an advisor.
You will be given a JSON object of agronomic facts that have already been
computed by an expert rule-based system. Your ONLY job is to restate these
exact facts as a short, warm, simple spoken message for a farmer receiving
a phone call, in plain English (a mix of English and Kannada is fine if natural).

Strict rules:
- Do NOT add any fact, number, date, or recommendation that is not present in the JSON.
- Do NOT omit any fact that is marked as true/due/needed in the JSON.
- Do NOT guess or infer anything about the crop beyond what is given.
- If a field is null or false, do not mention it.
- Keep the message under 60 seconds when spoken aloud (roughly 120-150 words maximum).
- Speak directly to the farmer, e.g. "Your paddy field..." not "The farmer's field...".
"""


def generate_advisory_message(facts: dict) -> str:
    """
    Calls Gemini to paraphrase the facts dict into a spoken message.
    Falls back to a simple templated message (built directly from the facts,
    no LLM involved) if the API call fails -- so a rate limit or network issue
    on demo day never breaks the pipeline.
    """
    try:
        prompt = (
            f"{SYSTEM_INSTRUCTION}\n\n"
            f"Here are the facts (JSON):\n{facts}\n\n"
            f"Now produce the spoken message."
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300},
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
        return _fallback_message(facts)


def _fallback_message(facts: dict) -> str:
    """A deterministic, no-LLM backup message built directly from the facts."""
    parts = [f"Hello, this is your farm advisory for {facts.get('crop', 'your crop')}."]
    if facts.get("irrigation_needed"):
        parts.append("Your soil moisture is low. Please irrigate your field soon.")
    if facts.get("waterlogging_risk"):
        parts.append("Your field has excess water. Please check drainage.")
    if facts.get("fertilizer_due"):
        parts.append(facts.get("fertilizer_recommendation", ""))
    if facts.get("harvest_rain_warning"):
        parts.append("Rain is expected soon and your crop is near harvest time. Consider harvesting early or covering your crop.")
    elif facts.get("ready_to_harvest"):
        parts.append("Your crop has reached harvest maturity.")
    elif facts.get("approaching_harvest"):
        parts.append(f"Your crop will be ready for harvest in about {facts.get('days_remaining_to_harvest_estimate')} days.")
    if facts.get("mandi_price_per_quintal"):
        parts.append(f"Today's mandi price is {facts['mandi_price_per_quintal']} rupees per quintal.")
    return " ".join(parts)
