"""
Main FastAPI app.

POST /sensor-data  -> full pipeline: rule engine -> weather/mandi enrichment
                      -> LLM paraphrase -> Twilio voice call + SMS
GET  /              -> health check
GET  /test-advisory -> runs the pipeline with sample hardcoded values (no
                       need to POST anything -- useful for quick browser testing)
"""
from fastapi import FastAPI
from pydantic import BaseModel

from rule_engine import evaluate
from weather import get_rain_risk_next_3_days
from mandi import get_mandi_price
from llm import generate_advisory_message
from telephony import send_sms, make_voice_call

app = FastAPI(title="Crop Advisory Backend")


class SensorData(BaseModel):
    soil_moisture: float       # e.g. 0-100 (qualitative band from capacitive sensor)
    temperature: float         # Celsius
    humidity: float            # percent
    days_since_sowing: int     # how many days since the paddy was sown


def run_pipeline(data: SensorData, deliver: bool = True) -> dict:
    """Runs the full pipeline and optionally delivers the call/SMS."""
    rain_risk = get_rain_risk_next_3_days()
    mandi_price = get_mandi_price()

    facts = evaluate(
        soil_moisture=data.soil_moisture,
        temperature=data.temperature,
        humidity=data.humidity,
        days_since_sowing=data.days_since_sowing,
        rain_risk_next_3_days=rain_risk,
        mandi_price=mandi_price,
    )

    message = generate_advisory_message(facts)

    result = {"facts": facts, "message": message}

    if deliver:
        sms_result = send_sms(message)
        call_result = make_voice_call(message)
        result["sms_result"] = sms_result
        result["call_result"] = call_result

    return result


@app.get("/")
def health_check():
    return {"status": "backend is alive"}


@app.post("/sensor-data")
def receive_sensor_data(data: SensorData):
    return run_pipeline(data, deliver=True)


@app.get("/test-advisory")
def test_advisory():
    """
    Quick manual test with no need to construct a JSON body -- just open this
    URL in a browser (locally or on Render) to trigger the full pipeline with
    sample values simulating a dry field, 20 days after sowing.
    """
    sample = SensorData(
        soil_moisture=20.0,
        temperature=29.5,
        humidity=68.0,
        days_since_sowing=20,
    )
    return run_pipeline(sample, deliver=True)


@app.get("/test-advisory-no-call")
def test_advisory_no_call():
    """Same as above but does NOT place a call/SMS -- just shows what would be sent."""
    sample = SensorData(
        soil_moisture=20.0,
        temperature=29.5,
        humidity=68.0,
        days_since_sowing=20,
    )
    return run_pipeline(sample, deliver=False)
