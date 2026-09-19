// config.h
// Fill in your own values below before uploading.

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

// ---- Pin assignments (match hardware/circuit_diagram.svg) ----
#define DHT_PIN         4      // DHT22 data pin
#define DHT_TYPE        DHT22
#define SOIL_PIN        34     // Capacitive soil moisture analog output (ADC1_6)
#define RAIN_PIN        35     // FC-37 rain sensor analog output (ADC1_7)
#define I2C_SDA_PIN     21     // BH1750 SDA (optional sensor)
#define I2C_SCL_PIN     22     // BH1750 SCL (optional sensor)

// ---- Sowing date (used to compute days_since_sowing automatically) ----
// Format: YYYY, MM, DD  (set this to the actual date paddy was sown in your demo/field)
#define SOWING_YEAR     2026
#define SOWING_MONTH    6
#define SOWING_DAY      15

// ---- Reading interval ----
#define READING_INTERVAL_MS   (5UL * 60UL * 1000UL)   // 5 minutes; lower this for live demo testing

// ---- Soil moisture calibration ----
// Raw ADC values from YOUR sensor in fully dry air vs. fully in water.
// Run the included calibration sketch (see README in this folder) to find these
// for your specific sensor unit, then update the values below.
#define SOIL_ADC_DRY    3000   // raw analogRead() value in dry air (placeholder — recalibrate!)
#define SOIL_ADC_WET    1200   // raw analogRead() value fully submerged in water (placeholder — recalibrate!)

#endif
