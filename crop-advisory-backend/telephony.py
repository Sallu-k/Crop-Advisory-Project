"""
Delivers messages via SMS (Twilio or textbee, selected by SMS_PROVIDER) and,
if enabled, voice call (Twilio only). Every send is fully independent --
if one fails, it does not prevent or delay any other, and each has its own
explicit timeout so a slow/hanging request can't stall the whole pipeline.
"""
import requests
from requests.auth import HTTPBasicAuth
from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
    TWILIO_VOICE,
    TWILIO_VOICE_LANGUAGE,
    SMS_PROVIDER,
    TEXTBEE_API_KEY,
    TEXTBEE_DEVICE_ID,
    ADVISORY_TO_NUMBER,
)

TWILIO_BASE_URL = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}"
TEXTBEE_SEND_URL = "https://api.textbee.dev/api/v1/gateway/send-sms"
REQUEST_TIMEOUT_SECONDS = 15


def _json_or_raw(response) -> dict:
    """Parse a JSON body, tolerating a non-JSON one (a 2xx must not be reported as a failure for that)."""
    try:
        body = response.json()
        return body if isinstance(body, dict) else {"raw": body}
    except Exception:
        return {"raw": getattr(response, "text", "")}


def send_sms(message: str) -> dict:
    """Routes to the configured SMS provider. Never raises -- failures come back as a dict."""
    if SMS_PROVIDER == "textbee":
        return _send_sms_textbee(message)
    return _send_sms_twilio(message)


def _send_sms_twilio(message: str) -> dict:
    try:
        url = f"{TWILIO_BASE_URL}/Messages.json"
        payload = {
            "From": TWILIO_FROM_NUMBER,
            "To": ADVISORY_TO_NUMBER,
            "Body": message,
        }
        response = requests.post(
            url,
            data=payload,
            auth=HTTPBasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        body = _json_or_raw(response)
        success = response.status_code < 300
        result = {"success": success, "status_code": response.status_code, "body": body}
        if not success:
            # Twilio's error responses include a human-readable "message" and
            # a "code" (e.g. 21608 = unverified number, 572006 = trial
            # accounts can only send predefined templates) -- surface both
            # instead of just the bare HTTP status.
            result["error"] = f"Twilio {body.get('code', '?')}: {body.get('message', 'unknown error')}"
        return result
    except Exception as e:
        print(f"[telephony.py] Twilio SMS send failed: {e}")
        return {"success": False, "error": str(e)}


def _send_sms_textbee(message: str) -> dict:
    """
    Sends SMS via textbee (https://textbee.dev) -- turns your own Android
    phone into the SMS sender, using its existing SIM/carrier plan. No
    trial-template restriction, no per-message cost, no DLT registration
    needed for this kind of low-volume personal/prototype use.

    Setup: install the textbee app on an Android phone, register it at
    textbee.dev to get an API key, put that in TEXTBEE_API_KEY.
    """
    try:
        headers = {"x-api-key": TEXTBEE_API_KEY}
        payload = {"recipients": [ADVISORY_TO_NUMBER], "message": message}
        if TEXTBEE_DEVICE_ID:
            payload["deviceId"] = TEXTBEE_DEVICE_ID
        response = requests.post(
            TEXTBEE_SEND_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
        )
        success = response.status_code < 300
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}
        result = {"success": success, "status_code": response.status_code, "body": body}
        if not success:
            result["error"] = f"textbee {response.status_code}: {body.get('message', body)}"
        return result
    except Exception as e:
        print(f"[telephony.py] textbee SMS send failed: {e}")
        return {"success": False, "error": str(e)}


def make_voice_call(message: str) -> dict:
    """
    Places an automated voice call reading `message` aloud via Twilio's
    <Say> TwiML verb. Voice is Twilio-only (textbee is SMS-only). Voice +
    language are configurable (see config.py).
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
            "To": ADVISORY_TO_NUMBER,
            "Twiml": twiml,
        }
        response = requests.post(
            url,
            data=payload,
            auth=HTTPBasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        body = _json_or_raw(response)
        success = response.status_code < 300
        result = {"success": success, "status_code": response.status_code, "body": body}
        if not success:
            result["error"] = f"Twilio {body.get('code', '?')}: {body.get('message', 'unknown error')}"
        return result
    except Exception as e:
        print(f"[telephony.py] Voice call failed: {e}")
        return {"success": False, "error": str(e)}
