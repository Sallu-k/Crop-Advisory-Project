"""
Delivers the final advisory message as a voice call (text-to-speech) and an
SMS, using Twilio. Uses the raw Twilio REST API via HTTP requests + basic auth
so we don't require the twilio Python SDK to be installed (fewer dependencies).
"""
import requests
from requests.auth import HTTPBasicAuth
from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWILIO_TO_NUMBER

TWILIO_BASE_URL = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}"


def send_sms(message: str) -> dict:
    """Sends an SMS via Twilio. Returns the API response as a dict."""
    url = f"{TWILIO_BASE_URL}/Messages.json"
    payload = {
        "From": TWILIO_FROM_NUMBER,
        "To": TWILIO_TO_NUMBER,
        "Body": message,
    }
    response = requests.post(
        url, data=payload, auth=HTTPBasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    )
    return {"status_code": response.status_code, "body": response.json()}


def make_voice_call(message: str) -> dict:
    """
    Places an automated voice call that reads `message` aloud using Twilio's
    <Say> TwiML verb. We pass TwiML directly as a Twiml parameter (no need to
    host a separate TwiML endpoint for this simple case).
    """
    # Escape XML special characters minimally
    safe_message = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    twiml = f'<Response><Say voice="Polly.Aditi" language="hi-IN">{safe_message}</Say></Response>'

    url = f"{TWILIO_BASE_URL}/Calls.json"
    payload = {
        "From": TWILIO_FROM_NUMBER,
        "To": TWILIO_TO_NUMBER,
        "Twiml": twiml,
    }
    response = requests.post(
        url, data=payload, auth=HTTPBasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    )
    return {"status_code": response.status_code, "body": response.json()}
