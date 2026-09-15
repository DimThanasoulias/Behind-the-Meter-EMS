/**
 * @file power_calc.cpp
 * @brief Implementation of 3-Phase Electrical Power and Trapezoidal Energy Engine.
 */

#include "power_calc.h"
#include <cmath>
#include <algorithm>

namespace ems {

PowerCalculator::PowerCalculator()
    : grid_frequency_hz_(50.0f),
      cumulative_energy_kwh_(0.0),
      last_total_power_kw_(0.0f),
      last_update_millis_(0),
      has_prior_sample_(false) {
    // Standard Greek Commercial 230/400V 50Hz supply
    setNominalVoltage(230.0f, 230.0f, 230.0f);
    // Typical Greek commercial power factor (0.95 inductive baseline)
    setPhasePowerFactors(0.95f, 0.95f, 0.95f);
}

void PowerCalculator::setNominalVoltage(float v_l1, float v_l2, float v_l3) {
    nominal_voltage_[0] = (v_l1 > 0.0f) ? v_l1 : 230.0f;
    nominal_voltage_[1] = (v_l2 > 0.0f) ? v_l2 : 230.0f;
    nominal_voltage_[2] = (v_l3 > 0.0f) ? v_l3 : 230.0f;
}

void PowerCalculator::setPhasePowerFactors(float pf_l1, float pf_l2, float pf_l3) {
    power_factors_[0] = std::max(-1.0f, std::min(1.0f, pf_l1));
    power_factors_[1] = std::max(-1.0f, std::min(1.0f, pf_l2));
    power_factors_[2] = std::max(-1.0f, std::min(1.0f, pf_l3));
}

void PowerCalculator::setGridFrequency(float freq_hz) {
    if (freq_hz > 0.0f) {
        grid_frequency_hz_ = freq_hz;
    }
}

void PowerCalculator::setCumulativeEnergy(double initial_kwh) {
    if (initial_kwh >= 0.0) {
        cumulative_energy_kwh_ = initial_kwh;
    }
}

float PowerCalculator::calculateTrueRms(const float* ac_samples, size_t count, float calibration_factor) {
    if (!ac_samples || count == 0) {
        return 0.0f;
    }

    double sum_sq = 0.0;
    for (size_t i = 0; i < count; ++i) {
        sum_sq += static_cast<double>(ac_samples[i]) * static_cast<double>(ac_samples[i]);
    }

    double mean_sq = sum_sq / static_cast<double>(count);
    return static_cast<float>(std::sqrt(mean_sq)) * calibration_factor;
}

double PowerCalculator::trapezoidalIntegrationStep(float p_prev_kw, float p_curr_kw, double dt_seconds) {
    if (dt_seconds <= 0.0) {
        return 0.0;
    }
    // Trapezoidal rule: Area = ((y0 + y1) / 2) * dt
    // dt in hours: dt_seconds / 3600.0
    double avg_power_kw = (static_cast<double>(p_prev_kw) + static_cast<double>(p_curr_kw)) / 2.0;
    return avg_power_kw * (dt_seconds / 3600.0);
}

SystemPowerSnapshot PowerCalculator::update(const ThreePhaseMeasurement& measurements, uint32_t current_millis) {
    SystemPowerSnapshot snap;
    snap.grid_frequency_hz = grid_frequency_hz_;
    snap.timestamp_epoch = 0; // populated by telemetry client with NTP/RTC

    // Per-phase calculations:
    // Phase L1
    snap.l1.voltage_v = nominal_voltage_[0];
    snap.l1.current_a = measurements.l1.current_rms_a;
    snap.l1.apparent_power_kva = (snap.l1.voltage_v * snap.l1.current_a) / 1000.0f;
    snap.l1.power_factor = power_factors_[0];
    snap.l1.active_power_kw = snap.l1.apparent_power_kva * snap.l1.power_factor;

    // Phase L2
    snap.l2.voltage_v = nominal_voltage_[1];
    snap.l2.current_a = measurements.l2.current_rms_a;
    snap.l2.apparent_power_kva = (snap.l2.voltage_v * snap.l2.current_a) / 1000.0f;
    snap.l2.power_factor = power_factors_[1];
    snap.l2.active_power_kw = snap.l2.apparent_power_kva * snap.l2.power_factor;

    // Phase L3
    snap.l3.voltage_v = nominal_voltage_[2];
    snap.l3.current_a = measurements.l3.current_rms_a;
    snap.l3.apparent_power_kva = (snap.l3.voltage_v * snap.l3.current_a) / 1000.0f;
    snap.l3.power_factor = power_factors_[2];
    snap.l3.active_power_kw = snap.l3.apparent_power_kva * snap.l3.power_factor;

    // Total aggregations
    snap.total_active_power_kw = snap.l1.active_power_kw + snap.l2.active_power_kw + snap.l3.active_power_kw;
    snap.total_apparent_power_kva = snap.l1.apparent_power_kva + snap.l2.apparent_power_kva + snap.l3.apparent_power_kva;

    // System power factor calculation
    if (snap.total_apparent_power_kva > 0.001f) {
        float raw_sys_pf = snap.total_active_power_kw / snap.total_apparent_power_kva;
        snap.system_power_factor = std::max(-1.0f, std::min(1.0f, raw_sys_pf));
    } else {
        snap.system_power_factor = 1.0f;
    }

    // Cumulative energy numerical integration via Trapezoidal Rule
    if (has_prior_sample_) {
        // Compute delta_t in seconds, handling 32-bit millis() overflow smoothly
        uint32_t dt_ms = current_millis - last_update_millis_;
        double dt_sec = static_cast<double>(dt_ms) / 1000.0;

        // Discard absurdly large dt (e.g. reboot or sleep > 1 hour) for clean integration
        if (dt_sec > 0.0 && dt_sec < 3600.0) {
            double delta_kwh = trapezoidalIntegrationStep(last_total_power_kw_, snap.total_active_power_kw, dt_sec);
            cumulative_energy_kwh_ += delta_kwh;
        }
    } else {
        has_prior_sample_ = true;
    }

    last_total_power_kw_ = snap.total_active_power_kw;
    last_update_millis_ = current_millis;

    snap.cumulative_energy_kwh = cumulative_energy_kwh_;

    return snap;
}

} // namespace ems
