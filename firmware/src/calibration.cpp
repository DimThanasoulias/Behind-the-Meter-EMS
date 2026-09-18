/**
 * @file calibration.cpp
 * @brief Implementation of Hardware Calibration and Error Compensation Engine.
 */

#include "calibration.h"

namespace ems {

HardwareCalibrator::HardwareCalibrator() {
    // Default calibration profiles for SCT-013 split-core CTs
    for (uint8_t i = 0; i < 3; ++i) {
        channels_[i].gain_multiplier = 1.000f;
        channels_[i].offset_mv = 0.0f;
        channels_[i].phase_displacement_deg = 1.85f;
        channels_[i].phase_current_slope = 4.20f;
    }
}

float HardwareCalibrator::correctAdcNonLinearity(float raw_mv) {
    if (raw_mv <= 0.0f) {
        return 0.0f;
    }

    // Stage 1: Deadband region (< 120 mV)
    // ESP32 SAR ADC under-reports low voltages due to input transistor threshold;
    // apply concave expansion (V_corr >= V_raw) so suppressed signals are restored.
    if (raw_mv < 120.0f) {
        float norm = raw_mv / 120.0f;
        return 120.0f * (1.25f * norm - 0.25f * norm * norm);
    }

    // Stage 2: Linear region (120 mV to 2600 mV)
    // eFuse factory curve is relatively linear; minor 1st order adjustment
    if (raw_mv <= 2600.0f) {
        return 0.998f * raw_mv + 0.5f;
    }

    // Stage 3: High-end saturation compression (> 2600 mV up to 3300 mV)
    // Quadratic decompression to linearize near 3.3V supply rail
    if (raw_mv < 3250.0f) {
        float excess = raw_mv - 2600.0f;
        float expansion = 1.0f + 0.00035f * excess;
        return 2600.0f + excess * expansion;
    }

    // Rail clamped
    return 3300.0f;
}

float HardwareCalibrator::estimatePhaseDisplacementDeg(float current_rms_a, float base_deg, float slope_coef) {
    if (current_rms_a <= 0.1f) {
        return base_deg + slope_coef / 0.6f; // Clamp to avoid singularity at idle
    }
    // Asymptotic decay: higher current saturates core less in relative terms, reducing phase lead
    return base_deg + slope_coef / (current_rms_a + 0.5f);
}

float HardwareCalibrator::compensatePowerFactor(float measured_cos_phi, float phase_displacement_deg, bool is_inductive) {
    // Clamp measured PF to valid physical range [-1.0, 1.0]
    if (measured_cos_phi > 1.0f) measured_cos_phi = 1.0f;
    if (measured_cos_phi < -1.0f) measured_cos_phi = -1.0f;

    // Convert to electrical radians
    float phi_meas_rad = std::acos(std::fabs(measured_cos_phi));
    float theta_rad = phase_displacement_deg * (3.14159265f / 180.0f);

    // In inductive load (current lags voltage), CT phase lead theta_e makes measured current
    // appear closer to voltage (phi_meas = phi_actual - theta_e).
    // Therefore, true phase angle is phi_true = phi_meas + theta_e.
    float phi_true_rad = is_inductive ? (phi_meas_rad + theta_rad) : (phi_meas_rad - theta_rad);

    if (phi_true_rad < 0.0f) phi_true_rad = 0.0f;
    if (phi_true_rad > 1.5707963f) phi_true_rad = 1.5707963f; // Clamp to 90 degrees

    float compensated_cos = std::cos(phi_true_rad);
    // Preserve sign of original power factor
    return (measured_cos_phi >= 0.0f) ? compensated_cos : -compensated_cos;
}

float HardwareCalibrator::calculateCalibratedActivePower(float apparent_power_kva, float compensated_pf, float gain_trim) {
    return apparent_power_kva * compensated_pf * gain_trim;
}

float HardwareCalibrator::updateMidpointEstimate(float current_midpoint_mv, float window_mean_mv, float alpha) {
    if (alpha <= 0.0f || alpha > 1.0f) {
        alpha = 0.005f;
    }
    return (1.0f - alpha) * current_midpoint_mv + alpha * window_mean_mv;
}

void HardwareCalibrator::setChannelParams(uint8_t phase_idx, const ChannelCalibrationParams& params) {
    if (phase_idx < 3) {
        channels_[phase_idx] = params;
    }
}

const ChannelCalibrationParams& HardwareCalibrator::getChannelParams(uint8_t phase_idx) const {
    if (phase_idx < 3) {
        return channels_[phase_idx];
    }
    return channels_[0];
}

} // namespace ems
