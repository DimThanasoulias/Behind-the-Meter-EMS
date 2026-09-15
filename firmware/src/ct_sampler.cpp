/**
 * @file ct_sampler.cpp
 * @brief Implementation of SCT-013 Split-Core Current Transformer Sampling.
 */

#include "ct_sampler.h"
#include <cmath>

namespace ems {

CTSampler::CTSampler() : initialized_(false) {
    // Default configuration for Greek 3-phase commercial service
    // Default to SCT-013-000 with 18 Ohm burden resistor (highest linear dynamic range)
    configurePhase(PhaseId::L1, CTSensorModel::SCT_013_000, 18.0f, 0.05f);
    configurePhase(PhaseId::L2, CTSensorModel::SCT_013_000, 18.0f, 0.05f);
    configurePhase(PhaseId::L3, CTSensorModel::SCT_013_000, 18.0f, 0.05f);
}

float CTSampler::calculateCalibrationFactor(CTSensorModel model, float burden_ohms) {
    if (model == CTSensorModel::SCT_013_030) {
        // SCT-013-030: Internal burden produces 1.0 V RMS (1000 mV RMS) at 30.0 A RMS
        // K_I = 30.0 A / 1000.0 mV = 0.03000 A/mV (30.0 A/V)
        return 30.0f / 1000.0f;
    } else {
        // SCT-013-000: Turns ratio 2000:1 (100 A -> 50 mA)
        // Secondary current I_sec = I_prim / 2000
        // Voltage across burden: V_b = I_sec * R_b = (I_prim / 2000) * R_b
        // I_prim = V_b * (2000 / R_b) in Volts
        // In millivolts: K_I = (2000.0 / R_b) / 1000.0 = 2.0 / R_b (A/mV)
        if (burden_ohms <= 0.001f) {
            burden_ohms = 18.0f; // Safety fallback
        }
        return (2000.0f / burden_ohms) / 1000.0f;
    }
}

void CTSampler::configurePhase(PhaseId phase, CTSensorModel model, float burden_ohms, float noise_gate) {
    uint8_t idx = static_cast<uint8_t>(phase);
    if (idx > 2) return;

    uint8_t assigned_pin = 0;
    switch (phase) {
        case PhaseId::L1: assigned_pin = PIN_CT_PHASE_L1; break;
        case PhaseId::L2: assigned_pin = PIN_CT_PHASE_L2; break;
        case PhaseId::L3: assigned_pin = PIN_CT_PHASE_L3; break;
    }

    configs_[idx].pin = assigned_pin;
    configs_[idx].model = model;
    configs_[idx].burden_resistor_ohms = (model == CTSensorModel::SCT_013_030) ? 0.0f : burden_ohms;
    configs_[idx].calibration_current_factor = calculateCalibrationFactor(model, configs_[idx].burden_resistor_ohms);
    configs_[idx].noise_gate_amperes = noise_gate;
}

void CTSampler::begin() {
    // 12-bit ADC resolution (0 - 4095)
    analogReadResolution(12);

    // Configure all assigned ADC1 pins for 11dB attenuation (up to ~3.3V input range)
    for (uint8_t i = 0; i < 3; ++i) {
        uint8_t pin = configs_[i].pin;
        // Verify hardware safety rule: must be on ADC1
        if (isAdc1Pin(pin)) {
            pinMode(pin, INPUT);
            analogSetPinAttenuation(pin, ADC_11db);
        }
    }

    initialized_ = true;
}

uint32_t CTSampler::readMilliVolts(uint8_t pin) {
    // analogReadMilliVolts uses factory eFuse calibration curves on ESP32
    return analogReadMilliVolts(pin);
}

PhaseMeasurement CTSampler::samplePhase(PhaseId phase, uint16_t num_cycles, uint16_t samples_per_cycle) {
    uint8_t idx = static_cast<uint8_t>(phase);
    PhaseMeasurement result = {0.0f, 0.0f, 1650.0f, 0};

    if (idx > 2 || !initialized_) {
        return result;
    }

    const PhaseSensorConfig& cfg = configs_[idx];
    const uint16_t total_samples = num_cycles * samples_per_cycle;
    if (total_samples == 0) return result;

    // Grid frequency 50 Hz -> 20,000 microseconds per cycle
    const uint32_t sample_interval_us = 20000UL / samples_per_cycle;

    // Buffer to hold window samples for exact DC bias removal
    // Allocate dynamically or clamp to stack buffer limit (e.g. 1000 samples)
    // 10 cycles * 50 = 500 samples (2 KB of RAM)
    const uint16_t max_buf_samples = 600;
    uint16_t n_samples = (total_samples > max_buf_samples) ? max_buf_samples : total_samples;
    float samples[max_buf_samples];

    float sum_raw = 0.0f;
    float min_val = 99999.0f;
    float max_val = -99999.0f;

    uint32_t next_sample_time = micros();

    for (uint16_t i = 0; i < n_samples; ++i) {
        // Wait until target sample instant for precise equi-spaced sampling
        while ((int32_t)(micros() - next_sample_time) < 0) {
            // tight spin for microsecond accuracy
        }
        next_sample_time += sample_interval_us;

        float mv = static_cast<float>(readMilliVolts(cfg.pin));
        samples[i] = mv;
        sum_raw += mv;

        if (mv < min_val) min_val = mv;
        if (mv > max_val) max_val = mv;
    }

    // DC midpoint bias estimation across exact integer cycles
    float dc_bias = sum_raw / static_cast<float>(n_samples);

    // Compute True RMS of AC component
    float sum_sq = 0.0f;
    for (uint16_t i = 0; i < n_samples; ++i) {
        float ac_mv = samples[i] - dc_bias;
        sum_sq += ac_mv * ac_mv;
    }

    float v_rms_mv = std::sqrt(sum_sq / static_cast<float>(n_samples));
    float i_rms = v_rms_mv * cfg.calibration_current_factor;

    // Noise gate: clamp floating/idle readings to zero
    if (i_rms < cfg.noise_gate_amperes) {
        i_rms = 0.0f;
    }

    result.current_rms_a = i_rms;
    result.peak_to_peak_mv = (max_val > min_val) ? (max_val - min_val) : 0.0f;
    result.dc_bias_mv = dc_bias;
    result.sample_count = n_samples;

    return result;
}

ThreePhaseMeasurement CTSampler::sampleAllPhases(uint16_t num_cycles, uint16_t samples_per_cycle) {
    uint32_t t_start = micros();

    ThreePhaseMeasurement result;
    result.l1 = samplePhase(PhaseId::L1, num_cycles, samples_per_cycle);
    result.l2 = samplePhase(PhaseId::L2, num_cycles, samples_per_cycle);
    result.l3 = samplePhase(PhaseId::L3, num_cycles, samples_per_cycle);
    result.sampling_duration_us = micros() - t_start;

    return result;
}

} // namespace ems
