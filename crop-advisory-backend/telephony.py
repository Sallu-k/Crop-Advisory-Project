"""
Delivers messages via Twilio. SMS and voice call are fully independent --
if one fails, it does not prevent or delay the other, and each has its own
explicit timeout so a slow/hanging request can't stall the whole pipeline.
"""
import requests
from requests.auth import HTTPBasicAuth
from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
    TWILIO_TO_NUMBER,
    TWILIO_VOICE,
    TWILIO_VOICE_LANGUAGE,
)

TWILIO_BASE_URL = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}"
REQUEST_TIMEOUT_SECONDS = 15


def send_sms(message: str) -> dict:
    """Sends an SMS via Twilio. Never raises -- failures are returned as a dict."""
    try:
        url = f"{TWILIO_BASE_URL}/Messages.json"
        payload = {
            "From": TWILIO_FROM_NUMBER,
            "To": TWILIO_TO_NUMBER,
            "Body": message,
        }
        response = requests.post(
            url,
            data=payload,
            auth=HTTPBasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        return {"success": response.status_code < 300, "status_code": response.status_code, "body": response.json()}
    except Exception as e:
        print(f"[telephony.py] SMS send failed: {e}")
        return {"success": False, "error": str(e)}


def make_voice_call(message: str) -> dict:
    """
    Places an automated voice call reading `message` aloud via Twilio's
    <Say> TwiML verb. Voice + language are configurable (see config.py) --
    do not hardcode a Hindi-only voice if the message might be in Kannada
    or another language.
    """
    try:
        safe_message = (
            message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        twiml = (
            f'<Response><Say voice="{TWILIO_VOICE}" language="{TWILIO_VOICE_LANGUAGE}">'
            f"{safe_message}</Say></Response>"
        )

        url = f"{TWILIO_BASE_URL}/Calls.json"
        payload = {
            "From": TWILIO_FROM_NUMBER,
            "To": TWILIO_TO_NUMBER,
            "Twiml": twiml,
        }
        response = requests.post(
            url,
            data=payload,
            auth=HTTPBasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        return {"success": response.status_code < 300, "status_code": response.status_code, "body": response.json()}
    except Exception as e:
        print(f"[telephony.py] Voice call failed: {e}")
        return {"success": False, "error": str(e)}
