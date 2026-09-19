// crop_advisory_node.ino
//
// ESP32 field sensor node for the Voice-First Crop Advisory project.
// Reads soil moisture, temperature/humidity, and rain status, computes
// days-since-sowing from NTP time, and POSTs a JSON payload to the backend.
//
// Required libraries (install via Arduino IDE Library Manager):
//   - "DHT sensor library" by Adafruit
//   - "Adafruit Unified Sensor" (dependency of the above)
//   - "ArduinoJson" by Benoit Blanchon
//   - "BH1750" by Christopher Laws   (only if using the optional light sensor)
//
// Board: any ESP32 DevKit (select "ESP32 Dev Module" in Tools > Board)

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <time.h>

#include "config.h"

DHT dht(DHT_PIN, DHT_TYPE);

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
  Serial.println("\nWi-Fi connection failed.");
  return false;
}

// ---------- NTP time sync ----------
bool syncTime() {
  // "IST-5:30" sets the timezone to India Standard Time
  configTime(5 * 3600 + 1800, 0, "pool.ntp.org", "time.google.com");

  struct tm timeinfo;
  int attempts = 0;
  while (!getLocalTime(&timeinfo) && attempts < 10) {
    Serial.println("Waiting for NTP time sync...");
    delay(1000);
    attempts++;
  }
  return getLocalTime(&timeinfo);
}

// ---------- Compute days since sowing ----------
int computeDaysSinceSowing() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    Serial.println("Time not available, defaulting days_since_sowing to 0");
    return 0;
  }

  struct tm sowing_tm = {};
  sowing_tm.tm_year = SOWING_YEAR - 1900;
  sowing_tm.tm_mon  = SOWING_MONTH - 1;
  sowing_tm.tm_mday = SOWING_DAY;
  sowing_tm.tm_hour = 0;
  sowing_tm.tm_min  = 0;
  sowing_tm.tm_sec  = 0;

  time_t now_epoch = mktime(&timeinfo);
  time_t sowing_epoch = mktime(&sowing_tm);

  double seconds_diff = difftime(now_epoch, sowing_epoch);
  int days = (int)(seconds_diff / (60 * 60 * 24));
  return days < 0 ? 0 : days;
}

// ---------- Read soil moisture and convert to 0-100 scale ----------
// NOTE: this scale is only as accurate as the SOIL_ADC_DRY / SOIL_ADC_WET
// calibration values in config.h. Recalibrate for your specific sensor unit.
float readSoilMoisturePercent() {
  int raw = analogRead(SOIL_PIN);
  // Map raw ADC reading to a 0 (dry) - 100 (wet) percentage.
  // Note: for capacitive sensors, a LOWER raw value usually means WETTER soil.
  float percent = 100.0 * ((float)(SOIL_ADC_DRY - raw) / (float)(SOIL_ADC_DRY - SOIL_ADC_WET));
  if (percent < 0) percent = 0;
  if (percent > 100) percent = 100;
  return percent;
}

// ---------- Read rain sensor (digital-style: higher analog = drier) ----------
bool readIsRaining() {
  int raw = analogRead(RAIN_PIN);
  // FC-37: lower analog reading generally means more water detected.
  // Threshold below is a starting point -- tune based on your module's behavior.
  return raw < 2000;
}

// ---------- Send JSON payload to backend ----------
bool sendSensorData(float soilMoisture, float temperature, float humidity, int daysSinceSowing) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi not connected, skipping send.");
    return false;
  }

  HTTPClient http;
  http.begin(BACKEND_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(15000);

  StaticJsonDocument<256> doc;
  doc["soil_moisture"] = soilMoisture;
  doc["temperature"] = temperature;
  doc["humidity"] = humidity;
  doc["days_since_sowing"] = daysSinceSowing;

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
  Serial.println("\n=== Crop Advisory Field Node Starting ===");

  dht.begin();

  if (connectWiFi()) {
    syncTime();
  }
}

void loop() {
  // Make sure Wi-Fi is still connected; reconnect if it dropped.
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi dropped, reconnecting...");
    connectWiFi();
  }

  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();

  if (isnan(humidity) || isnan(temperature)) {
    Serial.println("DHT22 read failed, using last-known safe defaults.");
    humidity = 60.0;
    temperature = 28.0;
  }

  float soilMoisture = readSoilMoisturePercent();
  bool raining = readIsRaining();
  int daysSinceSowing = computeDaysSinceSowing();

  Serial.println("---- Readings ----");
  Serial.printf("Soil moisture: %.1f %%\n", soilMoisture);
  Serial.printf("Temperature: %.1f C\n", temperature);
  Serial.printf("Humidity: %.1f %%\n", humidity);
  Serial.printf("Raining now: %s\n", raining ? "yes" : "no");
  Serial.printf("Days since sowing: %d\n", daysSinceSowing);

  bool sent = sendSensorData(soilMoisture, temperature, humidity, daysSinceSowing);
  Serial.println(sent ? "Data sent successfully." : "Data send failed (will retry next cycle).");

  Serial.printf("Sleeping for %lu ms...\n\n", (unsigned long)READING_INTERVAL_MS);
  delay(READING_INTERVAL_MS);
}
