"""
Main FastAPI app -- v2.

Key behavior change from v1: a sensor reading only results in a phone
call/SMS when something ACTUALLY changed (new condition, or an existing one
crossed its cooldown period). An unchanged "still dry" reading every 5
minutes does NOT re-trigger delivery. This also means weather/mandi/LLM/
Twilio are only called when there's actually something to say -- not on
every single reading.
"""
from datetime import datetime

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

from models import SensorData
from rule_engine import evaluate, compute_days_since_sowing
from weather import get_weather
from mandi import get_mandi_price
from message_planner import build_voice_message, build_sms_message
from telephony import send_sms, make_voice_call
from dashboard import render_dashboard
import state_manager
from config import EXPECTED_DEVICE_KEY, SOWING_DATE, ENABLE_VOICE_CALL

app = FastAPI(title="Crop Advisory Backend v2")


def _check_device_key(x_device_key: str = None):
    """
    Simple shared-secret check. If EXPECTED_DEVICE_KEY is not configured,
    the check is skipped entirely (useful for local testing) -- but for any
    real deployment, set EXPECTED_DEVICE_KEY so random requests can't
    trigger a real phone call.
    """
    if EXPECTED_DEVICE_KEY and x_device_key != EXPECTED_DEVICE_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing device key")


def run_pipeline(data: SensorData, deliver: bool, is_preview: bool = False) -> dict:
    device_id = "PREVIEW-TEST" if is_preview else data.device_id

    # ---- Duplicate/retry detection (skipped for preview so it can be reused freely) ----
    if not is_preview:
        if state_manager.is_duplicate_sequence(device_id, data.sequence):
            return {"success": True, "duplicate": True, "message": "Duplicate/retried sequence number, ignored."}
        state_manager.record_sequence(device_id, data.sequence)

    previous_moisture_state = None if is_preview else state_manager.get_previous_moisture_state(device_id)
    days_since_sowing = compute_days_since_sowing(SOWING_DATE)

    # ---- First pass: evaluate WITHOUT external context, to see if anything changed ----
    result = evaluate(
        soil_moisture=data.soil_moisture,
        temperature=data.temperature,
        humidity=data.humidity,
        raining=data.raining,
        light_level=data.light_level,
        days_since_sowing=days_since_sowing,
        previous_moisture_state=previous_moisture_state,
    )

    if not is_preview:
        state_manager.update_moisture_state(device_id, result["moisture_state"])
        new_alerts = state_manager.get_new_alerts(device_id, result["alert_codes"])
    else:
        # Preview always treats every active code as "new" so you can see the
        # full message for any scenario, without cooldown/state interference.
        new_alerts = [c for c in result["alert_codes"] if c in state_manager.ACTIONABLE_CODES]

    response = {
        "success": True,
        "device_id": device_id,
        "timestamp": datetime.now().isoformat(),
        "sensor": {
            "soil_moisture_index": data.soil_moisture,
            "temperature_c": data.temperature,
            "humidity_percent": data.humidity,
            "rain_detected_now": data.raining,
            "light_level": data.light_level,
        },
        "days_since_sowing": days_since_sowing,
        "current_alert_codes": result["alert_codes"],
        "new_alert_codes": new_alerts,
    }

    if not new_alerts:
        response["action_taken"] = "none (no new or renewed alert conditions)"
        if not is_preview:
            # Weather/mandi were deliberately not fetched on this reading, so
            # flag it -- the dashboard must not present "not checked" as "unavailable".
            state_manager.save_snapshot(device_id, {
                "facts": {**result["facts"], "weather_checked": False},
                "alert_codes": result["alert_codes"],
            })
        return response

    # ---- Only now (something to say) do we fetch external context ----
    weather = get_weather()
    mandi = get_mandi_price()

    result_with_context = evaluate(
        soil_moisture=data.soil_moisture,
        temperature=data.temperature,
        humidity=data.humidity,
        raining=data.raining,
        light_level=data.light_level,
        days_since_sowing=days_since_sowing,
        previous_moisture_state=previous_moisture_state,
        weather=weather,
        mandi=mandi,
    )
    facts = result_with_context["facts"]

    # Voice message generation (and the Gemini call it needs) is skipped
    # entirely when voice calling is disabled -- SMS-only mode has one
    # fewer external dependency to worry about.
    voice_message = build_voice_message(new_alerts) if ENABLE_VOICE_CALL else None
    sms_message = build_sms_message(result_with_context["alert_codes"], facts)

    response["facts"] = facts
    response["voice_message"] = voice_message
    response["sms_message"] = sms_message

    if deliver:
        sms_result = send_sms(sms_message)
        if ENABLE_VOICE_CALL:
            call_result = make_voice_call(voice_message)
            voice_status = "sent" if call_result.get("success") else f"failed: {call_result.get('error', call_result.get('status_code'))}"
        else:
            voice_status = "disabled (SMS-only mode)"
        response["delivery"] = {
            "voice_status": voice_status,
            "sms_status": "sent" if sms_result.get("success") else f"failed: {sms_result.get('error', sms_result.get('status_code'))}",
        }

    if not is_preview:
        state_manager.save_snapshot(device_id, {
            "facts": {**facts, "weather_checked": True},
            "alert_codes": result_with_context["alert_codes"],
            "delivery": response.get("delivery"),
        })

    return response


@app.get("/")
def health_check():
    return {"status": "backend is alive", "version": "v2"}


@app.post("/sensor-data")
def receive_sensor_data(data: SensorData, x_device_key: str = Header(default=None)):
    _check_device_key(x_device_key)
    return run_pipeline(data, deliver=True)


@app.post("/sensor-data-preview")
def preview_sensor_data(data: SensorData):
    """
    No device key required, never delivers, never touches real device state.
    Use this to test any combination of values without using Twilio quota
    or disturbing your real device's cooldown/state tracking.
    """
    return run_pipeline(data, deliver=False, is_preview=True)


@app.post("/demo/trigger")
def demo_trigger(x_device_key: str = Header(default=None)):
    """
    A POST (not GET) endpoint for triggering a real demo call with fixed
    sample values -- deliberately not a GET, since GET requests should never
    have side effects like placing a phone call.
    """
    _check_device_key(x_device_key)
    sample = SensorData(
        device_id="DEMO",
        sequence=int(datetime.now().timestamp()),
        soil_moisture=20.0,
        temperature=29.5,
        humidity=68.0,
        raining=False,
    )
    return run_pipeline(sample, deliver=True)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(device: str = None):
    return render_dashboard(device)
