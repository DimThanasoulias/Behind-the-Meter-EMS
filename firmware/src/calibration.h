/**
 * @file calibration.h
 * @brief Hardware Calibration and Error Compensation Engine for ESP32 & Split-Core CTs.
 *
 * Provides embedded DSP algorithms for:
 * 1. ESP32 SAR ADC Non-Linearity Correction (piecewise correction for 0-100mV deadband and 2600-3300mV compression).
 * 2. SCT-013 Split-Core CT Phase-Angle Displacement Compensation (theta_e correction for cos phi and active power).
 * 3. Dynamic DC Virtual Ground Midpoint Tracking (exponential moving average for 1.65V bias drift).
 * 4. Per-phase gain and offset calibration trimming.
 */

#pragma once

#include <cstdint>
#include <cmath>

namespace ems {

// Calibration coefficients for a single CT measurement channel
struct ChannelCalibrationParams {
    float gain_multiplier;         // Fine gain trim (nominal 1.000)
    float offset_mv;               // Zero-point offset correction in mV
    float phase_displacement_deg;  // Base CT phase lead angle in degrees (nominal 1.8 - 2.5 deg)
    float phase_current_slope;     // Current-dependent phase angle coefficient
};

class HardwareCalibrator {
public:
    HardwareCalibrator();

    /**
     * @brief Correct ESP32 SAR ADC non-linearity.
     * Maps raw hardware millivolt readings to linearized voltage using a 3-stage piecewise model:
     * - Stage 1 (< 120 mV): Dead-band non-linear polynomial expansion.
     * - Stage 2 (120 - 2600 mV): Linear calibrated range.
     * - Stage 3 (> 2600 mV): High-end compression decompression.
     *
     * @param raw_mv Raw reading from ESP32 ADC in millivolts
     * @return Linearized voltage in millivolts
     */
    static float correctAdcNonLinearity(float raw_mv);

    /**
     * @brief Compute load-dependent phase displacement angle theta_e for split-core CT.
     * Split-core CTs exhibit magnetizing core phase lead that decreases asymptotically
     * with higher primary current: theta_e(I) = theta_base + k_slope / (I + I_offset).
     *
     * @param current_rms_a Measured RMS current in Amperes
     * @param base_deg Base phase angle in degrees
     * @param slope_coef Slope coefficient
     * @return Estimated phase displacement in degrees
     */
    static float estimatePhaseDisplacementDeg(float current_rms_a, float base_deg = 1.6f, float slope_coef = 4.2f);

    /**
     * @brief Compensate power factor cos phi for CT phase displacement.
     * Corrects cos(phi_measured) to true cos(phi_actual) by removing theta_e:
     * phi_true = phi_measured - theta_e
     *
     * @param measured_cos_phi Raw measured power factor [-1.0, 1.0]
     * @param phase_displacement_deg Phase error theta_e in degrees
     * @param is_inductive True if load is inductive (lagging PF, typical for motors/compressors)
     * @return Compensated true power factor
     */
    static float compensatePowerFactor(float measured_cos_phi, float phase_displacement_deg, bool is_inductive = true);

    /**
     * @brief Compensate active power (kW) for CT phase displacement and ADC gain trim.
     * True Active Power: P_true = S * cos(phi_true) * gain_trim
     *
     * @param apparent_power_kva Measured apparent power in kVA
     * @param compensated_pf Phase-compensated power factor
     * @param gain_trim Per-channel gain calibration multiplier
     * @return Calibrated active power in kW
     */
    static float calculateCalibratedActivePower(float apparent_power_kva, float compensated_pf, float gain_trim = 1.0f);

    /**
     * @brief Update dynamic DC virtual midpoint bias using exponential moving average.
     * Adapts to temperature drift and supply rail variation.
     *
     * @param current_midpoint_mv Previous midpoint estimate
     * @param window_mean_mv Mean voltage measured across current integer cycles
     * @param alpha Filter smoothing factor (default 0.005)
     * @return Updated midpoint bias in millivolts
     */
    static float updateMidpointEstimate(float current_midpoint_mv, float window_mean_mv, float alpha = 0.005f);

    // Channel calibration parameter accessors
    void setChannelParams(uint8_t phase_idx, const ChannelCalibrationParams& params);
    const ChannelCalibrationParams& getChannelParams(uint8_t phase_idx) const;

private:
    ChannelCalibrationParams channels_[3];
};

} // namespace ems
