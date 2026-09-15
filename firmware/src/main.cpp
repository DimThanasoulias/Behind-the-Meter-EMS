/**
 * @file main.cpp
 * @brief Greek Commercial Behind-the-Meter EMS - ESP32 3-Phase Firmware.
 *
 * SENSORS:
 * - 3x YHDC SCT-013-000 (100A/50mA, 2000:1) Split-Core CT Clamps
 * - 18 Ohm 1% precision burden resistors (linear range up to 114 A RMS)
 * - 1.65V DC midpoint bias virtual ground
 * - Dedicated ADC1 pins: L1 -> GPIO 34, L2 -> GPIO 35, L3 -> GPIO 32
 *
 * TELEMETRY:
 * - HTTP REST client posting JSON payloads to /api/v1/telemetry
 * - In-memory store-and-forward ring buffer resilient against network outages
 * - Non-blocking exponential backoff Wi-Fi reconnection manager
 */

#include <Arduino.h>
#include "ct_sampler.h"
#include "power_calc.h"
#include "telemetry_client.h"

// Configuration Constants
static constexpr uint32_t SERIAL_BAUD_RATE = 115200;
static constexpr uint32_t TELEMETRY_INTERVAL_MS = 5000; // 5-second cadence
static constexpr uint16_t SAMPLING_CYCLES = 10;          // 10 cycles @ 50Hz = 200ms per phase
static constexpr uint16_t SAMPLES_PER_CYCLE = 50;        // 50 samples / cycle = 2.5 kHz

// Subsystem instances
static ems::CTSampler ct_sampler;
static ems::PowerCalculator power_calc;
static ems::TelemetryClient telemetry_client;

static uint32_t last_telemetry_time = 0;

void setup() {
    Serial.begin(SERIAL_BAUD_RATE);
    delay(1000);

    Serial.println();
    Serial.println(F("================================================================="));
    Serial.println(F(" Greek Behind-the-Meter EMS - ESP32 3-Phase Telemetry Firmware   "));
    Serial.println(F(" Version: 1.0.0 (PlatformIO / Arduino C++17)                     "));
    Serial.println(F("================================================================="));

    // 1. Initialize Analog Current Transformer Sampler
    Serial.println(F("[SETUP] Initializing SCT-013 CT Sampler on ADC1..."));
    ct_sampler.configurePhase(ems::PhaseId::L1, ems::CTSensorModel::SCT_013_000, 18.0f, 0.05f);
    ct_sampler.configurePhase(ems::PhaseId::L2, ems::CTSensorModel::SCT_013_000, 18.0f, 0.05f);
    ct_sampler.configurePhase(ems::PhaseId::L3, ems::CTSensorModel::SCT_013_000, 18.0f, 0.05f);
    ct_sampler.begin();
    Serial.println(F("[SETUP] CT Sampler initialized (L1: GPIO 34, L2: GPIO 35, L3: GPIO 32)."));

    // 2. Initialize Electrical Power Calculator
    Serial.println(F("[SETUP] Initializing 3-Phase Power Calculation Engine..."));
    power_calc.setNominalVoltage(230.0f, 230.0f, 230.0f); // Nominal Greek Phase-to-Neutral
    power_calc.setPhasePowerFactors(0.95f, 0.95f, 0.95f);  // Commercial baseline
    power_calc.setGridFrequency(50.0f);
    Serial.println(F("[SETUP] Power Calculator ready (230V / 50Hz nominal)."));

    // 3. Initialize Telemetry Client
    Serial.println(F("[SETUP] Initializing Telemetry Client (Wi-Fi + REST/MQTT)..."));
    telemetry_client.configureWiFi("EMS_Commercial_WLAN", "GreekEnergy2026");
    telemetry_client.configureRest("http://192.168.1.100:8000", "/api/v1/telemetry");
    telemetry_client.configureMqtt("192.168.1.100", 1883, "ems/telemetry");
    telemetry_client.setDeviceIdentity("esp32-ems-001", "bakery-central-athens");
    telemetry_client.setMode(ems::TelemetryMode::REST_ONLY);
    telemetry_client.begin();
    Serial.println(F("[SETUP] Telemetry Client initialized. Starting sampling loop..."));
    Serial.println(F("-----------------------------------------------------------------"));
}

void loop() {
    uint32_t now = millis();

    // Run non-blocking telemetry network loop (Wi-Fi reconnect + queue flush)
    telemetry_client.loop(now);

    // Periodic 3-phase sampling and dispatch
    if (now - last_telemetry_time >= TELEMETRY_INTERVAL_MS) {
        last_telemetry_time = now;

        // 1. Sample all 3 phases synchronously over exact integer cycles
        ems::ThreePhaseMeasurement samples = ct_sampler.sampleAllPhases(SAMPLING_CYCLES, SAMPLES_PER_CYCLE);

        // 2. Compute True RMS, Active/Apparent Power, and Trapezoidal Cumulative Energy
        ems::SystemPowerSnapshot snapshot = power_calc.update(samples, now);

        // 3. Print operational metrics to Serial console
        Serial.printf("[METRICS] L1: %.2fA (%.2fkW) | L2: %.2fA (%.2fkW) | L3: %.2fA (%.2fkW)\r\n",
                      snapshot.l1.current_a, snapshot.l1.active_power_kw,
                      snapshot.l2.current_a, snapshot.l2.active_power_kw,
                      snapshot.l3.current_a, snapshot.l3.active_power_kw);
        Serial.printf("[TOTALS]  P: %.3f kW | S: %.3f kVA | PF: %.2f | E: %.4f kWh\r\n",
                      snapshot.total_active_power_kw,
                      snapshot.total_apparent_power_kva,
                      snapshot.system_power_factor,
                      snapshot.cumulative_energy_kwh);
        Serial.printf("[STATUS]  Wi-Fi: %s | Queue Backlog: %u | Overflows: %u\r\n",
                      telemetry_client.isWiFiConnected() ? "CONNECTED" : "DISCONNECTED",
                      static_cast<unsigned int>(telemetry_client.getBufferedCount()),
                      static_cast<unsigned int>(telemetry_client.getBufferOverflows()));
        Serial.println(F("-----------------------------------------------------------------"));

        // 4. Dispatch telemetry snapshot (sends via REST or queues in ring buffer)
        telemetry_client.dispatchTelemetry(snapshot);
    }
}
