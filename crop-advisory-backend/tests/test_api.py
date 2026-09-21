"""
API / pipeline tests for main.py, run in-process with FastAPI's TestClient.

Every outbound call (Twilio/textbee SMS, voice call, Open-Meteo, data.gov.in,
Gemini) is mocked, so these run offline, instantly, and can never send a real
SMS or place a real call regardless of what is in .env.
"""
import os
import sys
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
import state_manager

KEY = {"X-Device-Key": "test-key"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    """Fresh state + deterministic config + all network mocked, for every test."""
    state_manager._STATE_STORE.clear()

    monkeypatch.setattr(main, "EXPECTED_DEVICE_KEY", "test-key")
    # Day 5 of the crop: no fertilizer / harvest rule fires, so only moisture
    # and sensor-fault codes drive the tests.
    monkeypatch.setattr(main, "SOWING_DATE", (date.today() - timedelta(days=5)).isoformat())
    monkeypatch.setattr(main, "ENABLE_VOICE_CALL", False)
    monkeypatch.setattr(state_manager, "ALERT_COOLDOWN_MINUTES", 720)

    calls = {"sms": [], "voice": []}

    def fake_sms(message):
        calls["sms"].append(message)
        return {"success": True, "status_code": 201}

    def fake_voice(message):
        calls["voice"].append(message)
        return {"success": True, "status_code": 201}

    monkeypatch.setattr(main, "send_sms", fake_sms)
    monkeypatch.setattr(main, "make_voice_call", fake_voice)
    monkeypatch.setattr(
        main, "get_weather",
        lambda: {"available": True, "rain_expected": False, "forecast": []},
    )
    monkeypatch.setattr(main, "get_mandi_price", lambda: {"available": False})
    monkeypatch.setattr(main, "build_voice_message", lambda codes: "VOICE:" + ",".join(codes))

    yield calls
    state_manager._STATE_STORE.clear()


client = TestClient(main.app)


def reading(seq, moisture=50.0, **kw):
    body = {
        "device_id": "FIELD-001", "sequence": seq, "soil_moisture": moisture,
        "temperature": 28.0, "humidity": 60.0, "raining": False,
    }
    body.update(kw)
    return body


# ---------------------------------------------------------------- basics

def test_health():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json() == {"status": "backend is alive", "version": "v2"}


def test_get_on_demo_trigger_is_not_allowed():
    assert client.get("/demo/trigger").status_code == 405


# ------------------------------------------------------------------ auth

def test_sensor_data_requires_device_key(isolated):
    assert client.post("/sensor-data", json=reading(1, 20)).status_code == 401
    assert client.post("/sensor-data", json=reading(1, 20), headers={"X-Device-Key": "bad"}).status_code == 401
    assert isolated["sms"] == []


def test_demo_trigger_requires_device_key(isolated):
    assert client.post("/demo/trigger").status_code == 401
    assert isolated["sms"] == []


def test_auth_check_skipped_when_key_not_configured(monkeypatch, isolated):
    monkeypatch.setattr(main, "EXPECTED_DEVICE_KEY", "")
    r = client.post("/sensor-data", json=reading(1, 20))
    assert r.status_code == 200
    assert len(isolated["sms"]) == 1


# ------------------------------------------------------------ validation

@pytest.mark.parametrize("patch", [
    {"soil_moisture": 101}, {"soil_moisture": -1},
    {"temperature": 61}, {"temperature": -11},
    {"humidity": 101}, {"light_level": 101},
    {"sequence": -1}, {"sequence": "abc"}, {"device_id": ""},
])
def test_out_of_range_or_bad_values_rejected(patch):
    assert client.post("/sensor-data-preview", json=reading(1, **patch)).status_code == 422


def test_missing_device_id_rejected():
    body = reading(1)
    del body["device_id"]
    assert client.post("/sensor-data-preview", json=body).status_code == 422


def test_boundary_values_accepted():
    for patch in ({"soil_moisture": 0}, {"soil_moisture": 100}, {"temperature": -10}, {"temperature": 60}):
        assert client.post("/sensor-data-preview", json=reading(1, **patch)).status_code == 200


# --------------------------------------------------------------- preview

def test_preview_never_delivers_and_shows_message(isolated):
    r = client.post("/sensor-data-preview", json=reading(1, 20))
    body = r.json()
    assert r.status_code == 200
    assert body["device_id"] == "PREVIEW-TEST"
    assert "LOW_MOISTURE" in body["new_alert_codes"]
    assert "soil moisture is low" in body["sms_message"]
    assert "delivery" not in body
    assert isolated["sms"] == [] and isolated["voice"] == []


def test_preview_is_repeatable_and_leaves_no_state(isolated):
    for _ in range(3):
        r = client.post("/sensor-data-preview", json=reading(1, 20))
        assert "LOW_MOISTURE" in r.json()["new_alert_codes"]
    assert state_manager.get_all_device_ids() == []
    assert "Waiting for the first sensor reading" in client.get("/dashboard").text


def test_preview_healthy_field_takes_no_action():
    body = client.post("/sensor-data-preview", json=reading(1, 50)).json()
    assert body["new_alert_codes"] == []
    assert body["action_taken"].startswith("none")
    assert "sms_message" not in body


def test_preview_sensor_faults_are_reported_not_faked():
    body = client.post(
        "/sensor-data-preview",
        json={"device_id": "X", "sequence": 1, "soil_moisture": None, "temperature": None, "humidity": None},
    ).json()
    assert {"SENSOR_FAULT_DHT22", "SENSOR_FAULT_SOIL"} <= set(body["new_alert_codes"])
    assert "Temperature:" not in body["sms_message"]
    assert "Humidity:" not in body["sms_message"]


def test_preview_excess_moisture():
    body = client.post("/sensor-data-preview", json=reading(1, 90)).json()
    assert "EXCESS_MOISTURE" in body["new_alert_codes"]


# ------------------------------------------------------------- delivery

def test_real_reading_with_new_alert_sends_one_sms(isolated):
    r = client.post("/sensor-data", json=reading(1, 20), headers=KEY)
    body = r.json()
    assert r.status_code == 200
    assert body["new_alert_codes"] == ["LOW_MOISTURE"]
    assert body["delivery"] == {"voice_status": "disabled (SMS-only mode)", "sms_status": "sent"}
    assert len(isolated["sms"]) == 1
    assert isolated["voice"] == []


def test_healthy_reading_sends_nothing(isolated):
    body = client.post("/sensor-data", json=reading(1, 50), headers=KEY).json()
    assert body["action_taken"].startswith("none")
    assert isolated["sms"] == []


def test_same_condition_does_not_realert_within_cooldown(isolated):
    """The core v2 fix: a dry field must not text every 5 minutes."""
    for seq in range(1, 6):
        client.post("/sensor-data", json=reading(seq, 20), headers=KEY)
    assert len(isolated["sms"]) == 1


def test_realerts_after_cooldown_expires(monkeypatch, isolated):
    monkeypatch.setattr(state_manager, "ALERT_COOLDOWN_MINUTES", 0)
    client.post("/sensor-data", json=reading(1, 20), headers=KEY)
    client.post("/sensor-data", json=reading(2, 20), headers=KEY)
    assert len(isolated["sms"]) == 2


def test_realerts_when_condition_clears_then_returns(isolated):
    client.post("/sensor-data", json=reading(1, 20), headers=KEY)   # low -> alert
    client.post("/sensor-data", json=reading(2, 50), headers=KEY)   # back to normal
    client.post("/sensor-data", json=reading(3, 20), headers=KEY)   # low again -> alert
    assert len(isolated["sms"]) == 2


def test_duplicate_or_retried_sequence_ignored(isolated):
    client.post("/sensor-data", json=reading(5, 20), headers=KEY)
    dup = client.post("/sensor-data", json=reading(5, 20), headers=KEY).json()
    older = client.post("/sensor-data", json=reading(4, 20), headers=KEY).json()
    assert dup["duplicate"] is True and older["duplicate"] is True
    assert len(isolated["sms"]) == 1


def test_sequences_tracked_per_device(isolated):
    client.post("/sensor-data", json=reading(1, 20, device_id="A"), headers=KEY)
    r = client.post("/sensor-data", json=reading(1, 20, device_id="B"), headers=KEY).json()
    assert "duplicate" not in r
    assert len(isolated["sms"]) == 2


def test_moisture_hysteresis_through_the_api(isolated):
    """27 -> low (alert); 30 and 34 stay low (no new alert); 36 -> normal."""
    client.post("/sensor-data", json=reading(1, 27), headers=KEY)
    r30 = client.post("/sensor-data", json=reading(2, 30), headers=KEY).json()
    r34 = client.post("/sensor-data", json=reading(3, 34), headers=KEY).json()
    r36 = client.post("/sensor-data", json=reading(4, 36), headers=KEY).json()
    assert "LOW_MOISTURE" in r30["current_alert_codes"]
    assert "LOW_MOISTURE" in r34["current_alert_codes"]
    assert "LOW_MOISTURE" not in r36["current_alert_codes"]
    assert len(isolated["sms"]) == 1


def test_sms_failure_is_reported_not_swallowed(monkeypatch):
    monkeypatch.setattr(main, "send_sms", lambda m: {"success": False, "error": "Twilio 21608: unverified"})
    body = client.post("/sensor-data", json=reading(1, 20), headers=KEY).json()
    assert body["delivery"]["sms_status"] == "failed: Twilio 21608: unverified"


def test_voice_enabled_sends_call_and_sms(monkeypatch, isolated):
    monkeypatch.setattr(main, "ENABLE_VOICE_CALL", True)
    body = client.post("/sensor-data", json=reading(1, 20), headers=KEY).json()
    assert body["voice_message"] == "VOICE:LOW_MOISTURE"
    assert body["delivery"]["voice_status"] == "sent"
    assert isolated["voice"] == ["VOICE:LOW_MOISTURE"]
    assert len(isolated["sms"]) == 1


def test_voice_failure_does_not_block_sms(monkeypatch, isolated):
    monkeypatch.setattr(main, "ENABLE_VOICE_CALL", True)
    monkeypatch.setattr(main, "make_voice_call", lambda m: {"success": False, "status_code": 500})
    body = client.post("/sensor-data", json=reading(1, 20), headers=KEY).json()
    assert body["delivery"]["voice_status"] == "failed: 500"
    assert body["delivery"]["sms_status"] == "sent"


def test_demo_trigger_delivers_with_key(isolated):
    r = client.post("/demo/trigger", headers=KEY)
    assert r.status_code == 200
    assert r.json()["device_id"] == "DEMO"
    assert len(isolated["sms"]) == 1


# ------------------------------------------- weather / mandi in the message

def test_weather_failure_says_unavailable_never_no_rain(monkeypatch, isolated):
    monkeypatch.setattr(main, "get_weather", lambda: {"available": False, "rain_expected": None, "forecast": None})
    body = client.post("/sensor-data", json=reading(1, 20), headers=KEY).json()
    sms = isolated["sms"][0]
    assert body["facts"]["rain_expected_next_days"] is None
    assert "Weather forecast unavailable" in sms
    assert "No significant rain" not in sms


def test_mandi_price_included_when_available(monkeypatch, isolated):
    monkeypatch.setattr(main, "get_mandi_price", lambda: {
        "available": True, "market": "Bhatkal", "arrival_date": "21/09/2026", "modal_price": 2300.0,
    })
    client.post("/sensor-data", json=reading(1, 20), headers=KEY)
    assert "Mandi (Bhatkal, 21/09/2026): Rs 2300.0/quintal" in isolated["sms"][0]


def test_mandi_alone_never_triggers_a_message(monkeypatch, isolated):
    monkeypatch.setattr(main, "get_mandi_price", lambda: {"available": True, "market": "M", "modal_price": 1.0})
    client.post("/sensor-data", json=reading(1, 50), headers=KEY)
    assert isolated["sms"] == []


# The dashboard's rendering is covered in tests/test_dashboard.py.
