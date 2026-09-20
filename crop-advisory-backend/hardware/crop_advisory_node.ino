// crop_advisory_node.ino  (v2)
//
// ESP32 field sensor node for the Voice-First Crop Advisory project.
//
// What changed from v1, and why:
//  - No NTP time sync. The ESP32 no longer computes days-since-sowing --
//    that's now done on the BACKEND from a configured sowing date. This
//    removes an entire failure mode (a bad/missing NTP sync used to
//    silently produce days_since_sowing = 0, which could wrongly trigger a
//    basal-fertilizer alert on a 90-day-old crop). The node now knows
//    almost nothing about farming -- it just reports raw sensor readings.
//  - DHT22 failure sends NULL for temperature/humidity instead of a fake
//    plausible-looking number. A missing key in the JSON = sensor fault,
//    handled honestly by the backend, not hidden.
//  - Sends device_id + an incrementing sequence number, so the backend can
//    reject duplicate/retried sends.
//  - Sends the rain sensor reading (previously read but never transmitted).
//  - Soil moisture is smoothed by averaging 16 readings, so the number
//    doesn't jitter around on stage.
//  - BH1750 light sensor removed -- unused in the current advisory logic,
//    so it was just visual/wiring noise.
//  - Sends a device-key header so random requests can't trigger a real call.
//
// Required libraries (install via Arduino IDE Library Manager):
//   - "DHT sensor library" by Adafruit
//   - "Adafruit Unified Sensor" (dependency of the above)
//   - "ArduinoJson" by Benoit Blanchon
//
// Board: any ESP32 DevKit (select "ESP32 Dev Module" in Tools > Board)

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

#include "config.h"

DHT dht(DHT_PIN, DHT_TYPE);

// Persists only for as long as the device stays powered on. Resets to 0 on
// reboot -- for a single-device one-week demo this is an accepted
// simplification (see state_manager.py comments on the backend side).
unsigned long sequenceNumber = 0;

// ---------- Wi-Fi connection ----------
bool connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting to Wi-Fi");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWi-Fi connected. IP: " + WiFi.localIP().toString());
    return true;
  }
  Serial.println("\nWi-Fi connection failed after ~15 seconds (30 attempts).");
  return false;
}

// ---------- Read soil moisture (averaged, smoothed) and convert to 0-100 index ----------
// NOTE: this is a relative INDEX derived from calibration, not a laboratory
// volumetric-water-content measurement. Present it as such.
float readSoilMoistureIndex() {
  const int samples = 16;
  long total = 0;
  for (int i = 0; i < samples; i++) {
    total += analogRead(SOIL_PIN);
    delay(10);
  }
  float raw = total / (float)samples;

  // For capacitive sensors, a LOWER raw value usually means WETTER soil.
  float index = 100.0 * ((float)(SOIL_ADC_DRY - raw) / (float)(SOIL_ADC_DRY - SOIL_ADC_WET));
  if (index < 0) index = 0;
  if (index > 100) index = 100;
  return index;
}

// ---------- Read rain sensor (lower analog reading = more water detected) ----------
bool readIsRaining() {
  int raw = analogRead(RAIN_PIN);
  // Starting threshold -- tune based on your specific module's dry/wet readings.
  return raw < 2000;
}

// ---------- Send JSON payload to backend ----------
bool sendSensorData(float soilMoisture, bool dhtOk, float temperature, float humidity, bool raining) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi not connected, skipping send.");
    return false;
  }

  HTTPClient http;
  http.begin(BACKEND_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  http.setTimeout(15000);

  StaticJsonDocument<320> doc;
  doc["device_id"] = DEVICE_ID;
  doc["sequence"] = sequenceNumber;
  doc["soil_moisture"] = soilMoisture;
  doc["raining"] = raining;

  // Only include temperature/humidity if the DHT22 read succeeded --
  // otherwise leave them out entirely so the backend receives null,
  // which correctly triggers a SENSOR_FAULT alert instead of a fake reading.
  if (dhtOk) {
    doc["temperature"] = temperature;
    doc["humidity"] = humidity;
  }

  String payload;
  serializeJson(doc, payload);

  Serial.println("Sending payload: " + payload);
  int httpResponseCode = http.POST(payload);

  bool success = false;
  if (httpResponseCode > 0) {
    Serial.printf("HTTP response code: %d\n", httpResponseCode);
    String response = http.getString();
    Serial.println("Response: " + response);
    success = (httpResponseCode == 200);
  } else {
    Serial.printf("HTTP POST failed, error: %s\n", http.errorToString(httpResponseCode).c_str());
  }

  http.end();
  return success;
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== Crop Advisory Field Node Starting (v2) ===");

  dht.begin();
  connectWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi dropped, reconnecting...");
    connectWiFi();
  }

  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();
  bool dhtOk = !(isnan(humidity) || isnan(temperature));

  if (!dhtOk) {
    Serial.println("DHT22 read failed -- reporting sensor fault (NOT fabricating a value).");
  }

  float soilMoisture = readSoilMoistureIndex();
  bool raining = readIsRaining();

  Serial.println("---- Readings ----");
  Serial.printf("Soil moisture index: %.1f / 100\n", soilMoisture);
  if (dhtOk) {
    Serial.printf("Temperature: %.1f C\n", temperature);
    Serial.printf("Humidity: %.1f %%\n", humidity);
  } else {
    Serial.println("Temperature/Humidity: FAULT (DHT22 not responding)");
  }
  Serial.printf("Raining now: %s\n", raining ? "yes" : "no");
  Serial.printf("Sequence: %lu\n", sequenceNumber);

  bool sent = sendSensorData(soilMoisture, dhtOk, temperature, humidity, raining);
  Serial.println(sent ? "Data sent successfully." : "Data send failed (will retry with a fresh reading next cycle).");

  sequenceNumber++;

  Serial.printf("Waiting %lu ms until next reading...\n\n", (unsigned long)READING_INTERVAL_MS);
  delay(READING_INTERVAL_MS);
}
