"""
Regression tests for bugs found in the full system test. Each test pins the
CORRECT behaviour of something that used to be broken. Everything outbound is
mocked -- nothing here can send an SMS or touch the network.
"""
import json
import os
import subprocess
import sys
import threading
from datetime import date, timedelta

import pytest
import requests
from fastapi.testclient import TestClient

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

import llm
import main
import mandi
import rule_engine
import state_manager
import telephony
import weather

KEY = {"X-Device-Key": "test-key"}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    state_manager._STATE_STORE.clear()
    state_manager.reset_runtime()
    client.cookies.clear()          # the dashboard remembers the access key in a cookie: start every test locked
    monkeypatch.setattr(state_manager, "TRANSLATE_SMS_TO", "")   # whatever .env says: default to English
    monkeypatch.setattr(main, "EXPECTED_DEVICE_KEY", "test-key")
    monkeypatch.setattr(main, "SOWING_DATE", (date.today() - timedelta(days=5)).isoformat())
    monkeypatch.setattr(main, "ENABLE_VOICE_CALL", False)
    monkeypatch.setattr(state_manager, "ALERT_COOLDOWN_MINUTES", 720)
    monkeypatch.setattr(main, "get_weather", lambda: {"available": True, "rain_expected": False, "forecast": []})
    monkeypatch.setattr(main, "get_mandi_price", lambda: {"available": False})
    sms = []
    monkeypatch.setattr(main, "send_sms", lambda m: (sms.append(m), {"success": True, "status_code": 201})[1])
    yield sms
    state_manager._STATE_STORE.clear()
    state_manager.reset_runtime()


client = TestClient(main.app, raise_server_exceptions=False)


def reading(seq, moisture=20.0, device="D1", **kw):
    body = {"device_id": device, "sequence": seq, "soil_moisture": moisture,
            "temperature": 28.0, "humidity": 60.0, "raining": False}
    body.update(kw)
    return body


def post(seq, moisture=20.0, **kw):
    return client.post("/sensor-data", json=reading(seq, moisture, **kw), headers=KEY)


class FakeResponse:
    def __init__(self, status=200, payload=None, url="https://example.test/x"):
        self.status_code = status
        self._payload = payload
        self.url = url
        self.text = "" if payload is None else json.dumps(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"{self.status_code} Error for url: {self.url}")
            err.response = self
            raise err


# ------------------------------------------------- failed delivery must be retried

def test_failed_sms_does_not_start_the_cooldown(monkeypatch, env):
    monkeypatch.setattr(main, "send_sms", lambda m: {"success": False, "error": "network down"})
    first = post(1).json()
    assert first["delivery"]["sms_status"].startswith("failed") and first["retry_pending"] is True

    monkeypatch.setattr(main, "send_sms", lambda m: (env.append(m), {"success": True})[1])
    second = post(2).json()
    assert second["new_alert_codes"] == ["LOW_MOISTURE"] and len(env) == 1   # retried, not suppressed
    assert post(3).json()["new_alert_codes"] == []                          # ...and NOW the cooldown applies


def test_voice_success_counts_as_delivered_even_if_sms_failed(monkeypatch, env):
    monkeypatch.setattr(main, "ENABLE_VOICE_CALL", True)
    monkeypatch.setattr(main, "build_voice_message", lambda codes: "v")
    monkeypatch.setattr(main, "make_voice_call", lambda m: {"success": True})
    monkeypatch.setattr(main, "send_sms", lambda m: {"success": False, "error": "x"})
    body = post(1).json()
    assert "retry_pending" not in body
    assert post(2).json()["new_alert_codes"] == []


# ------------------------------------------------- demo trigger

def test_demo_trigger_fires_every_time():
    a = client.post("/demo/trigger", headers=KEY).json()
    b = client.post("/demo/trigger", headers=KEY).json()      # immediately, same second
    assert a["new_alert_codes"] == ["LOW_MOISTURE"] == b["new_alert_codes"]
    assert a["delivery"]["sms_status"] == b["delivery"]["sms_status"] == "sent"


# ------------------------------------------------- device restarts

def test_device_restart_is_not_mistaken_for_a_duplicate(env):
    for seq in range(0, 40):
        post(seq, 50)
    restarted = post(0, 20).json()                            # ESP32 rebooted: counter back to 0
    assert not restarted.get("duplicate") and restarted["new_alert_codes"] == ["LOW_MOISTURE"]
    assert not post(1, 20).json().get("duplicate")           # and it continues normally from there


def test_a_large_drop_is_a_restart_but_a_small_one_is_still_a_retry():
    post(100, 50)
    assert post(99, 50).json().get("duplicate") is True       # out-of-order retry
    assert post(100, 50).json().get("duplicate") is True      # exact retry
    assert not post(30, 50).json().get("duplicate")           # far lower -> device restarted


def test_retry_of_sequence_zero_on_a_fresh_device_is_still_a_duplicate():
    post(0, 50)
    assert post(0, 50).json().get("duplicate") is True


def test_same_sequence_sent_concurrently_is_processed_once(env):
    results = []

    def go():
        results.append(post(7, 10).json())

    threads = [threading.Thread(target=go) for _ in range(25)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(1 for r in results if not r.get("duplicate")) == 1
    assert len(env) == 1


# ------------------------------------------------- rule engine

@pytest.mark.parametrize("previous,value,expected", [
    ("low", 90, "high"), ("high", 5, "low"),        # jump straight past the opposite threshold
    ("low", 34.9, "low"), ("low", 35, "normal"),    # hysteresis still holds / releases correctly
    ("high", 65.1, "high"), ("high", 65, "normal"),
    (None, 27.9, "low"), (None, 28, "normal"), (None, 75, "normal"), (None, 75.1, "high"),
])
def test_moisture_state_transitions(previous, value, expected):
    assert rule_engine._moisture_state(value, previous) == expected


def test_a_reading_that_never_fetched_weather_is_not_reported_as_a_weather_outage():
    post(1, 20)
    second = post(2, 19).json()                                # cooldown -> weather not fetched
    assert "WEATHER_UNAVAILABLE" not in second["current_alert_codes"]


def test_a_real_weather_outage_is_still_reported(monkeypatch):
    monkeypatch.setattr(main, "get_weather", lambda: {"available": False, "rain_expected": None, "forecast": None})
    body = post(1, 20).json()
    assert body["facts"]["weather_available"] is False and body["facts"]["weather_checked"] is True
    assert "Weather forecast unavailable" in body["sms_message"]
    snapshot_codes = state_manager.get_snapshot("D1")["alert_codes"]
    assert "WEATHER_UNAVAILABLE" in snapshot_codes             # a genuine outage IS recorded


# ------------------------------------------------- input validation

def test_nan_is_a_422_not_a_500():
    r = client.post("/sensor-data-preview", content='{"device_id":"D","sequence":1,"soil_moisture":NaN}',
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and "input" not in r.text


@pytest.mark.parametrize("patch", [
    {"device_id": "   "}, {"sequence": True}, {"sequence": "5"}, {"sequence": 5.5},
    {"sequence": 2**32}, {"soil_moisture": "wet"}, {"temperature": float("inf")},
])
def test_garbage_is_rejected(patch):
    body = reading(1)
    body.update(patch)
    r = client.post("/sensor-data-preview", content=json.dumps(body), headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_device_id_is_trimmed():
    assert client.post("/sensor-data-preview", json=reading(1, device="  FIELD-1  ")).json()["device_id"] == "PREVIEW-TEST"
    post(1, 50, device="  FIELD-1  ")
    assert state_manager.get_dashboard_device_ids() == ["FIELD-1"]


def test_malformed_sowing_date_stops_startup_with_a_clear_message():
    result = subprocess.run(
        [sys.executable, "-c", "import config"], cwd=BACKEND, capture_output=True, text=True,
        env={**os.environ, "SOWING_DATE": "15/06/2026"},
    )
    assert result.returncode != 0 and "SOWING_DATE must be in YYYY-MM-DD" in result.stderr


def test_wrong_device_key_variants_are_all_rejected():
    for headers in ({}, {"X-Device-Key": ""}, {"X-Device-Key": "TEST-KEY"}, {"X-Device-Key": "test-key "}):
        assert client.post("/sensor-data", json=reading(1), headers=headers).status_code == 401
    # the test client can't send non-ASCII headers, but a real client can: must be a clean 401, not a crash
    with pytest.raises(main.HTTPException) as exc:
        main._check_device_key("café")
    assert exc.value.status_code == 401


# ------------------------------------------------- dashboard hardening

def test_dashboard_sends_a_restrictive_content_security_policy():
    r = client.get("/dashboard")
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_dashboard_escapes_a_hostile_device_id():
    post(1, 50, device="<script>alert(1)</script>")
    assert "<script>alert(1)" not in client.get("/dashboard").text


# ------------------------------------------------- secrets never reach logs

def test_gemini_key_is_sent_in_a_header_and_never_logged(monkeypatch, capsys):
    monkeypatch.setattr(llm, "GEMINI_API_KEY", "SUPERSECRETGEMINIKEY")
    seen = {}

    def fake_post(url, json=None, headers=None, **kw):
        seen.update(url=url, headers=headers)
        return FakeResponse(429, {}, url=f"{url}?key=SUPERSECRETGEMINIKEY")

    monkeypatch.setattr(llm.requests, "post", fake_post)
    assert llm.generate_voice_message(["LOW_MOISTURE"])          # fallback template still delivered
    assert "SUPERSECRETGEMINIKEY" not in seen["url"]
    assert seen["headers"]["x-goog-api-key"] == "SUPERSECRETGEMINIKEY"
    assert "SUPERSECRETGEMINIKEY" not in capsys.readouterr().out


def test_mandi_key_is_never_logged(monkeypatch, capsys):
    monkeypatch.setattr(mandi, "DATA_GOV_API_KEY", "SUPERSECRETMANDIKEY")
    monkeypatch.setattr(
        mandi.requests, "get",
        lambda *a, **k: FakeResponse(500, {}, url=f"{mandi.MANDI_API_URL}?api-key=SUPERSECRETMANDIKEY"),
    )
    assert mandi.get_mandi_price() == {"available": False}
    assert "SUPERSECRETMANDIKEY" not in capsys.readouterr().out


def test_a_voice_reply_containing_digits_is_replaced_by_the_template(monkeypatch):
    reply = {"candidates": [{"content": {"parts": [{"text": "Hello! Moisture is 12 percent."}]}}]}
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: FakeResponse(200, reply))
    out = llm.generate_voice_message(["LOW_MOISTURE"])
    assert not any(ch.isdigit() for ch in out) and out.startswith("Hello, this is your farm advisory.")


# ------------------------------------------------- integrations

def test_one_null_day_does_not_discard_the_forecast(monkeypatch):
    data = {"daily": {"time": ["a", "b", "c"], "precipitation_sum": [0.0, None, 7.0]}}
    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: FakeResponse(200, data))
    w = weather.get_weather()
    assert w["available"] is True and w["rain_expected"] is True


def test_a_forecast_of_only_nulls_is_unknown_not_no_rain(monkeypatch):
    data = {"daily": {"time": ["a", "b"], "precipitation_sum": [None, None]}}
    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: FakeResponse(200, data))
    assert weather.get_weather() == {"available": False, "rain_expected": None, "forecast": None}


def test_a_2xx_reply_with_a_non_json_body_is_still_a_success(monkeypatch):
    monkeypatch.setattr(telephony.requests, "post", lambda *a, **k: FakeResponse(201, None))
    assert telephony._send_sms_twilio("x")["success"] is True
    assert telephony.make_voice_call("x")["success"] is True


# ------------------------------------------------- the one receiver-number setting

def test_every_channel_sends_to_the_advisory_number(monkeypatch):
    seen = []
    monkeypatch.setattr(telephony, "ADVISORY_TO_NUMBER", "+919999999999")
    monkeypatch.setattr(telephony.requests, "post", lambda url, data=None, **k: (seen.append(data["To"]), FakeResponse(201, {}))[1])
    telephony._send_sms_twilio("x")
    telephony.make_voice_call("x")
    assert seen == ["+919999999999", "+919999999999"]


@pytest.mark.parametrize("advisory,expected", [("", "+911111111111"), ("   ", "+911111111111"), ("+922222222222", "+922222222222")])
def test_blank_advisory_number_falls_back_to_the_twilio_number(advisory, expected):
    result = subprocess.run(
        [sys.executable, "-c", "import config; print(config.ADVISORY_TO_NUMBER)"], cwd=BACKEND,
        capture_output=True, text=True,
        env={**os.environ, "ADVISORY_TO_NUMBER": advisory, "TWILIO_TO_NUMBER": "+911111111111"},
    )
    assert result.stdout.strip() == expected, result.stderr


# --------------------------------------------- SMS timing, crashes, public hosting

def test_a_crash_before_delivery_does_not_swallow_the_alert(monkeypatch, env):
    """get_new_alerts() starts the cooldown; if the pipeline then crashes the farmer was never told."""
    def boom(*a, **k):
        raise RuntimeError("template bug")
    with monkeypatch.context() as broken:
        broken.setattr(main, "build_sms_message", boom)
        assert post(1).status_code == 500 and env == []

    retry = post(2).json()                                      # the bug is gone: the alert was NOT lost
    assert retry["new_alert_codes"] == ["LOW_MOISTURE"] and len(env) == 1


def test_a_crash_after_the_sms_went_out_does_not_cause_a_duplicate(monkeypatch, env):
    def boom(*a, **k):
        raise RuntimeError("dashboard snapshot bug")
    with monkeypatch.context() as broken:
        broken.setattr(state_manager, "save_snapshot", boom)
        assert post(1).status_code == 500 and len(env) == 1      # the SMS did go out
    assert post(2).json()["new_alert_codes"] == []               # still cooling down: no second SMS


def test_persistent_problem_repeats_every_five_minutes_but_calendar_reminders_do_not(monkeypatch):
    monkeypatch.setattr(state_manager, "ALERT_COOLDOWN_MINUTES", 5)
    monkeypatch.setattr(state_manager, "TIME_BASED_ALERT_COOLDOWN_MINUTES", 1440)
    codes = ["LOW_MOISTURE", "HARVEST_CHECK_DUE"]
    assert state_manager.get_new_alerts("D", codes) == ["HARVEST_CHECK_DUE", "LOW_MOISTURE"]   # new: immediate
    assert state_manager.get_new_alerts("D", codes) == []                                      # same minute: quiet

    last_sent = state_manager.get_device_state("D")["last_sent"]
    for code in last_sent:
        last_sent[code] -= timedelta(minutes=6)
    assert state_manager.get_new_alerts("D", codes) == ["LOW_MOISTURE"]        # 5 min passed: the sensor problem repeats
    for code in last_sent:
        last_sent[code] -= timedelta(hours=25)
    assert state_manager.get_new_alerts("D", codes) == ["HARVEST_CHECK_DUE", "LOW_MOISTURE"]   # a day later: both


def test_a_cleared_and_returned_problem_is_sent_again_immediately(monkeypatch):
    monkeypatch.setattr(state_manager, "ALERT_COOLDOWN_MINUTES", 5)
    assert state_manager.get_new_alerts("D", ["LOW_MOISTURE"]) == ["LOW_MOISTURE"]
    assert state_manager.get_new_alerts("D", []) == []
    assert state_manager.get_new_alerts("D", ["LOW_MOISTURE"]) == ["LOW_MOISTURE"]


def test_demo_sms_are_marked_as_test_but_real_ones_are_not(env):
    real = post(1).json()
    assert not real["sms_message"].startswith("[TEST]")
    demo = client.post("/demo/scenario/low_moisture", headers=KEY).json()
    assert demo["sms_message"].startswith("[TEST] ")
    assert env[-1].startswith("[TEST] ")                       # and that is what was actually sent
    trigger = client.post("/demo/trigger", headers=KEY).json()
    assert trigger["sms_message"].startswith("[TEST] ")


@pytest.mark.parametrize("key, problem", [
    ("", "empty"), ("demo-key-123", "placeholder"), ("short", "short"), ("CHANGE-ME", "placeholder"),
    ("test-key", "placeholder"), ("a" * 15, "short"),
])
def test_public_mode_rejects_weak_keys(key, problem):
    assert main.public_mode_problem(key), problem


def test_public_mode_accepts_a_strong_key():
    assert main.public_mode_problem("Zk3-pQ9vLm2xRt7WcH5aYn8B") is None


def _run_in_subprocess(code, **env):
    return subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, env={**os.environ, **env},
    )


def test_public_mode_refuses_to_start_with_a_weak_key():
    r = _run_in_subprocess("import main", PUBLIC_MODE="true", EXPECTED_DEVICE_KEY="demo-key-123")
    assert r.returncode != 0 and "PUBLIC_MODE=true" in r.stderr
    r = _run_in_subprocess("import main", PUBLIC_MODE="true", EXPECTED_DEVICE_KEY="")
    assert r.returncode != 0 and "empty" in r.stderr


def test_public_mode_hides_the_api_docs_and_local_mode_keeps_them():
    probe = (
        "from fastapi.testclient import TestClient; import main; c = TestClient(main.app); "
        "print(c.get('/docs').status_code, c.get('/openapi.json').status_code, c.get('/dashboard').status_code)"
    )
    public = _run_in_subprocess(probe, PUBLIC_MODE="true", EXPECTED_DEVICE_KEY="Zk3-pQ9vLm2xRt7WcH5aYn8B")
    assert public.stdout.split() == ["404", "404", "200"], public.stderr
    local = _run_in_subprocess(probe, PUBLIC_MODE="false")
    assert local.stdout.split() == ["200", "200", "200"], local.stderr


def test_preview_needs_the_key_only_in_public_mode(monkeypatch):
    body = reading(1)
    monkeypatch.setattr(main, "PUBLIC_MODE", False)
    assert client.post("/sensor-data-preview", json=body).status_code == 200
    monkeypatch.setattr(main, "PUBLIC_MODE", True)
    assert client.post("/sensor-data-preview", json=body).status_code == 401
    assert client.post("/sensor-data-preview", json=body, headers=KEY).status_code == 200


def test_favicon_is_answered_quietly():
    r = client.get("/favicon.ico")
    assert r.status_code == 204 and r.content == b""


def test_dashboard_never_leaks_the_key_through_the_referer():
    assert client.get("/dashboard").headers["referrer-policy"] == "no-referrer"


@pytest.mark.skipif(not hasattr(__import__("time"), "tzset"), reason="TZ is only applied on Linux/macOS (Windows uses the PC clock)")
def test_server_time_defaults_to_india_time():
    env_no_tz = {k: v for k, v in os.environ.items() if k != "TZ"}
    r = subprocess.run(
        [sys.executable, "-c", "import config, os, time; print(os.environ['TZ'], time.strftime('%z'))"],
        cwd=BACKEND, capture_output=True, text=True, env=env_no_tz,
    )
    assert r.stdout.split() == ["Asia/Kolkata", "+0530"], r.stderr
