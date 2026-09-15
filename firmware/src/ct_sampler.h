/**
 * @file ct_sampler.h
 * @brief SCT-013 Split-Core Current Transformer Sampling Engine for ESP32.
 *
 * HARDWARE CONSTRAINTS & PIN ALLOCATION:
 * - ESP32 has two SAR ADC peripherals: ADC1 (8 channels) and ADC2 (10 channels).
 * - CRITICAL: ADC2 CANNOT BE USED WHEN WI-FI IS ACTIVE!
 *   The ESP32 Wi-Fi RF physical driver continuously uses ADC2 for calibration,
 *   power management, and SAR measurements. Calling analogRead() on ADC2 pins
 *   while Wi-Fi is connected causes immediate hardware contention and returns
 *   corrupted values or crashes.
 * - THEREFORE, ALL 3-PHASE CT SENSORS ARE ASSIGNED TO ADC1 EXCLUSIVELY:
 *     * Phase 1 (L1): GPIO 34 (ADC1_CH6) - Input-only, no internal pull-ups
 *     * Phase 2 (L2): GPIO 35 (ADC1_CH7) - Input-only, no internal pull-ups
 *     * Phase 3 (L3): GPIO 32 (ADC1_CH4) - Input/Output capable, ADC1 input
 *     * (Optional V_ref): GPIO 33 (ADC1_CH5)
 *
 * BURDEN RESISTOR DERIVATION:
 * 1. SCT-013-000 (Current Output, 100A / 50mA, turns ratio 2000:1):
 *    - Rated RMS primary: 100 A -> peak primary: 100 * sqrt(2) = 141.42 A
 *    - Secondary peak current: I_sec_peak = 141.42 / 2000 = 0.07071 A (70.71 mA)
 *    - For ESP32 VDD = 3.3V, virtual midpoint = 1.65V.
 *    - Linear ADC window limit: V_peak <= 1.45V (avoids non-linear region <0.15V & >3.10V).
 *    - Theoretical max burden: R_burden = 1.45V / 0.07071A = 20.50 Ohms.
 *    - Recommended standard: 18 Ohms (1% metal film, 1/4W):
 *      * V_peak = 0.07071A * 18 Ohms = 1.273V -> V_pp = 2.546V (safe headroom up to 114 A RMS).
 *      * Calibration constant: K_I = Turns / R_burden = 2000 / 18 = 111.111 A/V = 0.11111 A/mV.
 *    - Alternative standard: 22 Ohms (1% metal film, 1/4W):
 *      * V_peak = 0.07071A * 22 Ohms = 1.556V -> V_pp = 3.111V (swings 0.095V to 3.205V).
 *      * Calibration constant: K_I = Turns / R_burden = 2000 / 22 = 90.909 A/V = 0.09091 A/mV.
 *    - Power dissipation: P = (0.050A)^2 * 22 Ohms = 0.055W (22% of 0.25W rating).
 *
 * 2. SCT-013-030 (Voltage Output, 30A / 1V RMS built-in burden):
 *    - Internal burden pre-installed; DO NOT add external burden!
 *    - Calibration constant: K_I = 30.0 A / 1.0 V = 30.0 A/V = 0.03000 A/mV.
 *
 * DC BIAS REMOVAL:
 * - Analog midpoint: 1.65V DC bias via 2x 10k 1% voltage divider + 10uF bypass cap.
 * - Digital removal: Window mean subtraction over integer 50 Hz cycles (20 ms * K),
 *   combined with IIR high-pass digital filter: y[n] = alpha * (y[n-1] + x[n] - x[n-1]).
 */

#pragma once

#include <Arduino.h>
#include <cstdint>

namespace ems {

// Explicit ADC1 Pin assignments
constexpr uint8_t PIN_CT_PHASE_L1 = 34; // ADC1_CH6 (GPIO 34)
constexpr uint8_t PIN_CT_PHASE_L2 = 35; // ADC1_CH7 (GPIO 35)
constexpr uint8_t PIN_CT_PHASE_L3 = 32; // ADC1_CH4 (GPIO 32)

// Phase identifier enumeration
enum class PhaseId : uint8_t {
    L1 = 0,
    L2 = 1,
    L3 = 2
};

// CT Sensor Type enumeration
enum class CTSensorModel : uint8_t {
    SCT_013_000 = 0, // 100A / 50mA current output (requires external burden)
    SCT_013_030 = 1  // 30A / 1V RMS voltage output (internal burden)
};

// Configuration per phase
struct PhaseSensorConfig {
    uint8_t pin;                  // Must be an ADC1 GPIO (32, 33, 34, 35, 36, 39)
    CTSensorModel model;          // SCT-013-000 or SCT-013-030
    float burden_resistor_ohms;   // e.g. 18.0 or 22.0 for SCT-013-000, 0.0 for SCT-013-030
    float calibration_current_factor; // Calculated K_I in A/mV
    float noise_gate_amperes;     // Cutoff for idle/floating clamp (default 0.05 A)
};

// Measurement result for a single phase
struct PhaseMeasurement {
    float current_rms_a;          // True RMS Current in Amperes
    float peak_to_peak_mv;        // AC signal peak-to-peak swing in millivolts
    float dc_bias_mv;             // Measured DC bias midpoint in millivolts (~1650 mV)
    uint16_t sample_count;        // Number of samples processed in window
};

// Measurement result across all three phases
struct ThreePhaseMeasurement {
    PhaseMeasurement l1;
    PhaseMeasurement l2;
    PhaseMeasurement l3;
    uint32_t sampling_duration_us;
};

class CTSampler {
public:
    CTSampler();

    /**
     * @brief Initialize ADC hardware parameters and configure ADC1 pins.
     * Sets 12-bit resolution and 11dB attenuation for full 0-3.3V range.
     */
    void begin();

    /**
     * @brief Configure sensor properties for a specific phase.
     * @param phase PhaseId::L1, L2, or L3
     * @param model SCT_013_000 or SCT_013_030
     * @param burden_ohms Burden resistor value in Ohms (e.g. 18.0 or 22.0)
     * @param noise_gate Minimum current cutoff in Amperes (default 0.05 A)
     */
    void configurePhase(PhaseId phase, CTSensorModel model, float burden_ohms = 18.0f, float noise_gate = 0.05f);

    /**
     * @brief Sample a single phase over an integer number of grid cycles (50 Hz).
     * @param phase Phase to sample
     * @param num_cycles Number of 20ms cycles to sample (default 10 = 200 ms)
     * @param samples_per_cycle Samples per 20ms cycle (default 50 -> 2.5 kHz sampling)
     * @return PhaseMeasurement containing RMS current, DC bias, and peak-to-peak swing
     */
    PhaseMeasurement samplePhase(PhaseId phase, uint16_t num_cycles = 10, uint16_t samples_per_cycle = 50);

    /**
     * @brief Sequentially sample all three phases (L1, L2, L3) over integer cycles.
     * @param num_cycles Number of 20ms cycles per phase (default 5 = 100 ms per phase)
     * @param samples_per_cycle Samples per cycle (default 50)
     * @return ThreePhaseMeasurement
     */
    ThreePhaseMeasurement sampleAllPhases(uint16_t num_cycles = 5, uint16_t samples_per_cycle = 50);

    /**
     * @brief Calculate theoretical current calibration factor K_I (A/mV).
     * @param model SCT-013 model
     * @param burden_ohms Burden resistor in Ohms (for SCT-013-000)
     * @return Calibration factor K_I in A/mV
     */
    static float calculateCalibrationFactor(CTSensorModel model, float burden_ohms);

    /**
     * @brief Verify if a GPIO pin is on ADC1 (safe for Wi-Fi coexistence).
     * @param pin GPIO pin number
     * @return true if pin belongs to ADC1, false if ADC2 or invalid
     */
    static constexpr bool isAdc1Pin(uint8_t pin) {
        // ESP32 ADC1 pins: GPIO 32, 33, 34, 35, 36, 39
        return (pin == 32 || pin == 33 || pin == 34 || pin == 35 || pin == 36 || pin == 39);
    }

private:
    PhaseSensorConfig configs_[3];
    bool initialized_;

    /**
     * @brief Read raw analog voltage in millivolts using calibrated ADC reading.
     */
    uint32_t readMilliVolts(uint8_t pin);
};

} // namespace ems
