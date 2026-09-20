// config.example.h
//
// Copy this file to "config.h" and fill in your own values.
// config.h is gitignored -- it will contain your real Wi-Fi password and
// device key, so it must NEVER be committed to GitHub. Only this .example
// file (with placeholder values) is safe to commit.

#ifndef CONFIG_H
#define CONFIG_H

// ---- Wi-Fi credentials ----
#define WIFI_SSID       "YOUR_WIFI_SSID"
#define WIFI_PASSWORD   "YOUR_WIFI_PASSWORD"

// ---- Backend endpoint ----
// Use your local backend while testing (e.g. http://192.168.1.x:8000/sensor-data),
// then switch to your deployed Render URL once that's live, e.g.:
// "https://crop-advisory-backend-xxxx.onrender.com/sensor-data"
#define BACKEND_URL     "https://YOUR-RENDER-APP.onrender.com/sensor-data"

// ---- Device identity ----
// Must match a device your backend expects. Also sent as a header so the
// backend can reject requests that don't know this shared secret (set
// EXPECTED_DEVICE_KEY to the same value in your backend's .env).
#define DEVICE_ID       "FIELD-001"
#define DEVICE_KEY      "demo-key-123"

// ---- Pin assignments (match hardware/circuit_diagram.svg) ----
// Note: BH1750 light sensor has been removed -- three well-integrated
// sensors (moisture, temp/humidity, rain) beat four half-integrated ones.
#define DHT_PIN         4      // DHT22 data pin
#define DHT_TYPE        DHT22
#define SOIL_PIN        34     // Capacitive soil moisture analog output (ADC1_6)
#define RAIN_PIN        35     // FC-37 rain sensor analog output (ADC1_7)

// ---- Reading interval ----
#define READING_INTERVAL_MS   (5UL * 60UL * 1000UL)   // 5 minutes; lower this for live demo testing

// ---- Soil moisture calibration ----
// Raw ADC values from YOUR sensor in fully dry air vs. fully in water.
// Run soil_calibration.ino FIRST to find these for your specific sensor
// unit, then update the values below. This is a relative INDEX, not a
// laboratory volumetric-water-content measurement -- call it that in your
// pitch, not "soil moisture percentage".
#define SOIL_ADC_DRY    3000   // raw analogRead() value in dry air (placeholder -- recalibrate!)
#define SOIL_ADC_WET    1200   // raw analogRead() value fully submerged in water (placeholder -- recalibrate!)

#endif
