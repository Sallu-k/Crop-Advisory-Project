"""
Data models for incoming sensor readings.

soil_moisture, temperature, and humidity are Optional[float] rather than
required floats -- this is deliberate. A DHT22 that fails to read should be
able to send `null` for temperature/humidity rather than the firmware
inventing a plausible-looking fake number. See rule_engine.py for how a
missing value is handled (it raises a SENSOR_FAULT alert code, it does not
get silently treated as fine).
"""
from typing import Optional
from pydantic import BaseModel, Field


class SensorData(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=64)
    sequence: int = Field(..., ge=0)

    # Range limits reject obviously garbage readings before they reach any logic.
    soil_moisture: Optional[float] = Field(None, ge=0, le=100)
    temperature: Optional[float] = Field(None, ge=-10, le=60)
    humidity: Optional[float] = Field(None, ge=0, le=100)
    raining: Optional[bool] = None
    light_level: Optional[float] = Field(None, ge=0, le=100)  # LDR-derived ambient light index, informational only

    class Config:
        json_schema_extra = {
            "example": {
                "device_id": "FIELD-001",
                "sequence": 42,
                "soil_moisture": 24.5,
                "temperature": 29.5,
                "humidity": 68.0,
                "raining": False,
                "light_level": 62.0,
            }
        }
