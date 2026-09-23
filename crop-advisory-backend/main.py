"""
Main FastAPI app -- v2.

Key behavior change from v1: a sensor reading only results in a phone
call/SMS when something ACTUALLY changed (new condition, or an existing one
crossed its cooldown period). An unchanged "still dry" reading does NOT
re-trigger delivery until the cooldown (ALERT_COOLDOWN_MINUTES) has passed.
This also means weather/mandi/LLM/Twilio are only called when there's
actually something to say -- not on every single reading.
"""
import hmac
import logging
from datetime import datetime
from typing import Optional

from fastapi import Cookie, FastAPI, Header, HTTPException, Request, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from models import SensorData
from rule_engine import evaluate, compute_days_since_sowing
from weather import get_weather, get_recent_rainfall
from mandi import get_mandi_price
from message_planner import build_voice_message, build_sms_message
from telephony import send_sms, make_voice_call
from dashboard import render_dashboard
from urllib.parse import quote
import state_manager
import demo_scenarios
import sms_i18n
import re

from config import (
    ADVISORY_TO_NUMBER, EXPECTED_DEVICE_KEY, SOWING_DATE, ENABLE_VOICE_CALL, TRANSLATE_SMS_TO, PUBLIC_MODE,
)

_WEAK_KEYS = {"demo-key-123", "change-me", "changeme", "test-key", "password", "secret"}


def public_mode_problem(key: str) -> Optional[str]:
    """Why this key is not acceptable for a server on the public internet (None if it is fine)."""
    if not key:
        return "EXPECTED_DEVICE_KEY is empty"
    if len(key) < 16 or key.lower() in _WEAK_KEYS:
        return "EXPECTED_DEVICE_KEY is too short or a well-known placeholder (use 16+ random characters)"
    return None


if PUBLIC_MODE and public_mode_problem(EXPECTED_DEVICE_KEY):
    # Fail closed: anyone who can reach a public server could otherwise send SMS from it.
    raise RuntimeError(
        f"PUBLIC_MODE=true but {public_mode_problem(EXPECTED_DEVICE_KEY)}. Set a strong key in the "
        "environment (and the same value as DEVICE_KEY in the ESP32's config.h), e.g.: "
        'python -c "import secrets; print(secrets.token_urlsafe(24))"'
    )

# On a public server the interactive API docs are switched off (they advertise every endpoint).
app = FastAPI(
    title="Crop Advisory Backend v2",
    **({"docs_url": None, "redoc_url": None, "openapi_url": None} if PUBLIC_MODE else {}),
)

if not EXPECTED_DEVICE_KEY:
    logging.warning(
        "EXPECTED_DEVICE_KEY is not set: /sensor-data and /demo/trigger accept requests from "
        "ANYONE, and can send real SMS. Set it in .env (and the same value as DEVICE_KEY in the "
        "ESP32's config.h) before exposing this server to a network."
    )


if not re.fullmatch(r"\+\d{8,15}", ADVISORY_TO_NUMBER or ""):
    logging.warning(
        "ADVISORY_TO_NUMBER is missing or not in international format (e.g. +919876543210): "
        "SMS alerts will not reach anyone. Set it in .env."
    )


if TRANSLATE_SMS_TO and not sms_i18n.is_supported(TRANSLATE_SMS_TO):
    logging.warning(
        "TRANSLATE_SMS_TO=%r is not supported (built-in templates exist for: %s). "
        "SMS will be sent in English.", TRANSLATE_SMS_TO, ", ".join(sms_i18n.SUPPORTED_LANGUAGES),
    )


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    """
    A 422 that never echoes the offending input back. FastAPI's default handler
    includes the raw input in the response, and for a value like NaN that cannot
    be serialised to JSON at all -- which turned a bad request into a 500.
    """
    errors = [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


# The dashboard remembers the access key in this cookie after it has been entered once, so the
# buttons keep working (and the key never has to sit in the address bar). HttpOnly + SameSite=Strict:
# scripts can't read it and other sites can't make the browser send it with a form post.
_KEY_COOKIE = "advisory_key"
_KEY_COOKIE_MAX_AGE = 12 * 3600


def _check_device_key(x_device_key: str = None, query_key: str = None, cookie_key: str = None):
    """
    Simple shared-secret check. If EXPECTED_DEVICE_KEY is not configured,
    the check is skipped entirely (useful for local testing) -- but for any
    real deployment, set EXPECTED_DEVICE_KEY so random requests can't
    trigger a real phone call.

    Accepts the key via the X-Device-Key header (ESP32, API clients), a
    `key` query parameter, or the dashboard's cookie (plain HTML <form> buttons
    can't set custom headers without JavaScript, and this dashboard deliberately
    stays JS-free -- see dashboard.py).
    """
    if not EXPECTED_DEVICE_KEY:
        return
    supplied = (x_device_key or query_key or cookie_key or "").encode("utf-8")
    # constant-time comparison, so the key can't be guessed from response timing
    if not hmac.compare_digest(supplied, EXPECTED_DEVICE_KEY.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid or missing device key")


def _key_is_valid(query_key: Optional[str]) -> bool:
    """Non-raising version of _check_device_key, for pages that only need to know whether to unlock."""
    if not EXPECTED_DEVICE_KEY:
        return True
    return hmac.compare_digest((query_key or "").encode("utf-8"), EXPECTED_DEVICE_KEY.encode("utf-8"))


def _dashboard_url(device: Optional[str], key: Optional[str], error: Optional[str] = None) -> str:
    """Where dashboard form posts send the browser back to. The path is fixed; only the values vary."""
    query = []
    if device:
        query.append(f"device={quote(device, safe='')}")
    if key:
        query.append(f"key={quote(key, safe='')}")
    if error:
        query.append(f"error={quote(error, safe='')}")
    return "/dashboard" + ("?" + "&".join(query) if query else "")


def _check_key_or_go_back(x_device_key, key, back, device, cookie_key=None):
    """
    _check_device_key, except that a wrong key from a dashboard button sends the browser
    back to the dashboard with a clear "wrong key" message (and the wrong key dropped from
    the URL) instead of stranding the user on a page of raw JSON. Returns the redirect to
    send, or None if the key is fine. API callers (no back=dashboard) still get a plain 401.
    """
    try:
        _check_device_key(x_device_key, key, cookie_key)
    except HTTPException:
        if back == "dashboard":
            # #demo-controls: land on the key box, where the "incorrect key" message is shown
            return RedirectResponse(_dashboard_url(device, None, error="key") + "#demo-controls", status_code=303)
        raise
    return None


def run_pipeline(
    data: SensorData,
    deliver: bool,
    is_preview: bool = False,
    days_since_sowing_override: int = None,
    language: Optional[str] = None,
    test_mode: bool = False,
    problem_title: Optional[str] = None,
) -> dict:
    # When the backend received this reading. The ESP32 has no clock, so this is
    # the reading's timestamp, and it is printed in the SMS.
    received_at = datetime.now()
    device_id = "PREVIEW-TEST" if is_preview else data.device_id
    # SMS language: an explicit per-call choice, else the dashboard/.env setting.
    lang = sms_i18n.normalize_language(language) if language else state_manager.get_sms_language()

    # ---- Duplicate/retry detection (skipped for preview so it can be reused freely) ----
    if not is_preview:
        # atomic check-and-record (a restarted device's counter reset is not a duplicate)
        if not state_manager.accept_sequence(device_id, data.sequence):
            return {"success": True, "duplicate": True, "message": "Duplicate/retried sequence number, ignored."}

    previous_moisture_state = None if is_preview else state_manager.get_previous_moisture_state(device_id)
    # A days_since_sowing override is ONLY used by demo scenarios (see
    # demo_scenarios.py) so a live showcase can demonstrate every
    # fertilizer/harvest condition on demand. Real readings (/sensor-data)
    # never pass this -- they always use the actual configured SOWING_DATE.
    days_since_sowing = (
        days_since_sowing_override if days_since_sowing_override is not None
        else compute_days_since_sowing(SOWING_DATE)
    )

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
        "timestamp": received_at.isoformat(),
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

    # Everything below can raise (rules, message templates, ...). By now get_new_alerts() has
    # already started the cooldown for these alerts, so if we crash before the farmer was told,
    # undo that -- otherwise the alert would be silently suppressed for the whole cooldown.
    delivered = False
    try:
        if not new_alerts:
            response["action_taken"] = "none (no new or renewed alert conditions)"
            if not is_preview:
                state_manager.save_snapshot(device_id, {"facts": result["facts"], "alert_codes": result["alert_codes"]})
            return response

        # ---- Only now (something to say) do we fetch external context ----
        weather = get_weather()
        mandi = get_mandi_price()
        # Recent (observed, not forecast) rainfall is only fetched when it can
        # actually change what's said -- i.e. when EXCESS_MOISTURE is one of the
        # new alerts, since that's the only place the rain-vs-irrigation
        # cross-check is used.
        recent_rainfall = get_recent_rainfall() if "EXCESS_MOISTURE" in new_alerts else None

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
            recent_rainfall=recent_rainfall,
        )
        facts = result_with_context["facts"]

        # Voice message generation (and the Gemini call it needs) is skipped
        # entirely when voice calling is disabled -- SMS-only mode has one
        # fewer external dependency to worry about.
        voice_message = build_voice_message(new_alerts) if ENABLE_VOICE_CALL else None
        # The SMS is built entirely from built-in templates (sms_i18n.py) plus the
        # numbers in `facts`: no translation service is involved, so every language
        # carries exactly the same values as the English original.
        # Demo buttons use made-up readings, so their SMS is marked and can't be mistaken for a real alert.
        prefix = "[TEST] " if test_mode else ""
        sms_message = prefix + build_sms_message(result_with_context["alert_codes"], facts, lang=lang, reading_time=received_at)

        response["facts"] = facts
        response["voice_message"] = voice_message
        response["sms_language"] = lang
        response["sms_message"] = sms_message
        if lang != "en":
            response["sms_message_english"] = prefix + build_sms_message(
                result_with_context["alert_codes"], facts, lang="en", reading_time=received_at
            )

        if deliver:
            sms_result = send_sms(sms_message)
            delivered = bool(sms_result.get("success"))   # from here on the farmer HAS been told: no rollback
            # Remember the outcome so the dashboard can confirm (or flag) this SMS.
            state_manager.record_sms_event({
                "device_id": device_id,
                "language": lang,
                "ok": bool(sms_result.get("success")),
                "error": None if sms_result.get("success") else str(sms_result.get("error", sms_result.get("status_code"))),
                "message": sms_message,
                "reading_at": received_at.isoformat(),
                "sent_at": datetime.now().isoformat(),
                # a problem introduced by hand from the dashboard (made-up readings), not a real alert
                "simulated": test_mode,
                "problem": problem_title,
            })
            voice_ok = False
            if ENABLE_VOICE_CALL:
                call_result = make_voice_call(voice_message)
                voice_ok = bool(call_result.get("success"))
                delivered = delivered or voice_ok
                voice_status = "sent" if voice_ok else f"failed: {call_result.get('error', call_result.get('status_code'))}"
            else:
                voice_status = "disabled (SMS-only mode)"
            response["delivery"] = {
                "voice_status": voice_status,
                "sms_status": "sent" if sms_result.get("success") else f"failed: {sms_result.get('error', sms_result.get('status_code'))}",
            }

            # If NOTHING got through, the farmer was never told -- so don't start the
            # cooldown. Roll the alerts back so the next reading retries them instead of
            # staying silent for the whole cooldown period.
            if not (sms_result.get("success") or voice_ok):
                if not is_preview:
                    state_manager.rollback_alerts(device_id, new_alerts)
                response["retry_pending"] = True

        if not is_preview:
            state_manager.save_snapshot(device_id, {
                "facts": facts,
                "alert_codes": result_with_context["alert_codes"],
                "delivery": response.get("delivery"),
            })

        return response
    except Exception:
        if not is_preview and not delivered:
            state_manager.rollback_alerts(device_id, new_alerts)
        raise


@app.get("/")
def health_check():
    return {"status": "backend is alive", "version": "v2"}


@app.post("/sensor-data")
def receive_sensor_data(data: SensorData, x_device_key: str = Header(default=None)):
    _check_device_key(x_device_key)
    return run_pipeline(data, deliver=True)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    # Browsers ask for this on every visit; answering "no icon" (rather than 404) keeps the logs clean.
    return Response(status_code=204)


@app.post("/sensor-data-preview")
def preview_sensor_data(data: SensorData, x_device_key: str = Header(default=None)):
    """
    Never delivers and never touches real device state. Use this to test any
    combination of values without using SMS quota or disturbing your real
    device's cooldown/state tracking. No device key is needed on a local
    server; with PUBLIC_MODE=true it needs one, because every call fetches
    weather/mandi data and would otherwise let anyone on the internet burn
    those quotas and tie up the server.
    """
    if PUBLIC_MODE:
        _check_device_key(x_device_key)
    return run_pipeline(data, deliver=False, is_preview=True)


@app.post("/demo/trigger")
def demo_trigger(x_device_key: str = Header(default=None)):
    """
    A POST (not GET) endpoint for triggering a real demo call with fixed
    sample values -- deliberately not a GET, since GET requests should never
    have side effects like placing a phone call.
    """
    _check_device_key(x_device_key)
    # A demo must fire EVERY time it is pressed. Forget the DEMO device's cooldown and
    # sequence history first, otherwise the second press within the cooldown does nothing.
    state_manager.reset_device("DEMO")
    sample = SensorData(
        device_id="DEMO",
        sequence=int(datetime.now().timestamp()),
        soil_moisture=20.0,
        temperature=29.5,
        humidity=68.0,
        raining=False,
    )
    return run_pipeline(sample, deliver=True, test_mode=True, problem_title="Low soil moisture (sample)")


@app.get("/demo/scenarios")
def list_demo_scenarios():
    """
    The decision table: every condition the system can alert on, what
    triggers it, and why it matters. The dashboard's demo buttons are built
    from this same data, so the list shown to a judge and the list actually
    wired up to fire can never drift apart.
    """
    return {
        name: {
            "title": s["title"],
            "why_it_matters": s["why_it_matters"],
            "expected_alert": s["expected_alert"],
            "can_force_trigger": s["sensor"] is not None,
        }
        for name, s in demo_scenarios.SCENARIOS.items()
    }


@app.post("/demo/scenario/{name}")
def demo_scenario(
    name: str,
    x_device_key: str = Header(default=None),
    key: str = Query(default=None),
    lang: Optional[str] = Query(default=None),
    back: Optional[str] = Query(default=None),
    device: Optional[str] = Query(default=None),
    advisory_key: Optional[str] = Cookie(default=None),
):
    """
    Introduces ONE specific named problem on demand (see demo_scenarios.py for
    the full decision table), so each alert type can be shown individually
    instead of waiting for it to occur naturally: it runs the made-up reading
    through the normal pipeline and sends the SMS. Each call resets that
    scenario's own simulated device first, so pressing the same button twice in
    a row fires twice -- cooldown logic is for real field devices, not for a
    live demo you're actively controlling. Real devices are never touched.

    `lang` (en/hi/kn) overrides the SMS language for this one call. The
    dashboard's buttons pass `back=dashboard`: the browser is then sent to the
    simulated device's page, where the banner confirms the problem and whether
    the SMS was sent, instead of landing on a page of raw JSON.
    """
    bad_key = _check_key_or_go_back(x_device_key, key, back, device, advisory_key)
    if bad_key:
        return bad_key
    if lang is not None and not sms_i18n.is_supported(lang):
        raise HTTPException(status_code=400, detail=f"Unsupported lang '{lang}'. Use one of: {', '.join(sms_i18n.SUPPORTED_LANGUAGES)}.")

    scenario = demo_scenarios.SCENARIOS.get(name)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Unknown scenario '{name}'. See GET /demo/scenarios for the list.")
    if scenario["sensor"] is None:
        raise HTTPException(
            status_code=400,
            detail=f"'{name}' cannot be force-triggered: {scenario['why_it_matters']}",
        )

    demo_device_id = f"DEMO-{name.upper()}"
    state_manager.reset_device(demo_device_id)

    sample = SensorData(
        device_id=demo_device_id,
        sequence=int(datetime.now().timestamp()),
        **scenario["sensor"],
    )
    result = run_pipeline(
        sample, deliver=True, days_since_sowing_override=scenario["days_override"],
        language=lang.strip().lower() if lang else None, test_mode=True, problem_title=scenario["title"],
    )
    result["scenario"] = name
    result["expected_alert"] = scenario["expected_alert"]
    if back == "dashboard":
        return RedirectResponse(_dashboard_url(demo_device_id, None), status_code=303)
    return result


@app.post("/demo/reset")
def back_to_real_values(
    x_device_key: str = Header(default=None),
    key: str = Query(default=None),
    back: Optional[str] = Query(default=None),
    advisory_key: Optional[str] = Cookie(default=None),
):
    """
    Clears every simulated problem (the DEMO-* devices and their notification) and returns
    to the real field readings. Real devices, their alert state and the SMS language are untouched.
    """
    bad_key = _check_key_or_go_back(x_device_key, key, back, None, advisory_key)
    if bad_key:
        return bad_key
    state_manager.clear_simulation()
    if back == "dashboard":
        return RedirectResponse(_dashboard_url(None, None), status_code=303)
    return {"reset": True}


@app.post("/settings/sms-language")
def set_sms_language(
    lang: str = Query(...),
    x_device_key: str = Header(default=None),
    key: str = Query(default=None),
    back: Optional[str] = Query(default=None),
    device: Optional[str] = Query(default=None),
    advisory_key: Optional[str] = Cookie(default=None),
):
    """
    Sets the language (en / hi / kn) of every SMS from now on -- automatic ones
    and the demo buttons alike -- until the server restarts (then TRANSLATE_SMS_TO
    from .env applies again). Needs the device key, like every other action that
    changes what gets sent to a phone.
    """
    bad_key = _check_key_or_go_back(x_device_key, key, back, device, advisory_key)
    if bad_key:
        return bad_key
    if not sms_i18n.is_supported(lang):
        raise HTTPException(status_code=400, detail=f"Unsupported lang '{lang}'. Use one of: {', '.join(sms_i18n.SUPPORTED_LANGUAGES)}.")
    state_manager.set_sms_language(lang)
    if back == "dashboard":
        return RedirectResponse(_dashboard_url(device, None), status_code=303)
    return {"sms_language": state_manager.get_sms_language()}


@app.post("/dashboard/lock")
def lock_dashboard():
    """Forget the remembered access key: the dashboard's controls lock again."""
    response = RedirectResponse("/dashboard", status_code=303)
    response.delete_cookie(_KEY_COOKIE, path="/")
    return response


# Defence in depth for the dashboard: no scripts, no external loads, no framing.
# form-action 'self' lets the dashboard's own <form> buttons post to this server
# (and only this server); 'none' would make browsers silently refuse every button.
_DASHBOARD_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
    # the access key can be in this page's URL for a moment: never hand it to other sites via the Referer header
    "Referrer-Policy": "no-referrer",
}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    device: Optional[str] = None,
    key: Optional[str] = None,
    error: Optional[str] = None,
    unlock: Optional[str] = None,
    advisory_key: Optional[str] = Cookie(default=None),
):
    # Entering the access key (the box on the page, or ?key=...) unlocks the controls ONCE: the right key
    # is remembered in a cookie and dropped from the URL, so it does not sit in the address bar, browser
    # history or server logs, and the buttons keep working across page reloads. Still: don't share a
    # dashboard link that contains ?key=..., and rotate EXPECTED_DEVICE_KEY if one is ever exposed.
    if key and _key_is_valid(key):
        response = RedirectResponse(_dashboard_url(device, None), status_code=303)
        response.set_cookie(
            _KEY_COOKIE, key, max_age=_KEY_COOKIE_MAX_AGE, httponly=True, samesite="strict",
            secure=PUBLIC_MODE, path="/",
        )
        return response

    # A wrong key never unlocks anything; the page says so (a button press with a wrong key is
    # redirected here with error=key).
    unlocked = _key_is_valid(advisory_key)
    key_error = (error == "key" or bool(key)) and not unlocked
    return HTMLResponse(
        render_dashboard(device, unlocked=unlocked, key_error=key_error, unlock=bool(unlock)),
        headers=_DASHBOARD_HEADERS,
    )
