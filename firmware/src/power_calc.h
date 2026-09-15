/**
 * @file power_calc.h
 * @brief 3-Phase Electrical Power and Trapezoidal Energy Calculation Engine.
 *
 * MATHEMATICAL FOUNDATIONS:
 * 1. True RMS Current:
 *    I_RMS = sqrt( (1 / N) * sum_{n=1}^N (i[n])^2 )
 *
 * 2. Apparent Power (kVA):
 *    S_phase = (V_RMS * I_RMS) / 1000.0
 *    S_total = S_L1 + S_L2 + S_L3
 *
 * 3. Active Power (kW) & Power Factor:
 *    P_phase = S_phase * cos_phi
 *    P_total = P_L1 + P_L2 + P_L3
 *    PF_sys  = P_total / S_total  (clamped to [-1.0, 1.0])
 *
 * 4. Trapezoidal Cumulative Energy Integration:
 *    Delta_E [kWh] = ( (P_prev + P_curr) / 2.0 ) * ( delta_t_sec / 3600.0 )
 *    E_cumulative [kWh] += Delta_E
 *
 * BACKEND INVARIANT:
 *    | total_active_power_kw - (P_L1 + P_L2 + P_L3) | <= 0.05 kW
 *    Enforced identically by construction: total_active_power_kw is the direct sum.
 */

#pragma once

#include <cstdint>
#include "ct_sampler.h"

namespace ems {

// Per-phase power results matching backend PhaseReading schema
struct PhasePower {
    float voltage_v;           // Phase RMS voltage [V] (nominal 230.0V)
    float current_a;           // Phase RMS current [A]
    float active_power_kw;     // Real active power [kW]
    float apparent_power_kva;  // Apparent power [kVA]
    float power_factor;        // Phase power factor cos phi in [-1.0, 1.0]
};

// System 3-phase aggregated telemetry snapshot
struct SystemPowerSnapshot {
    PhasePower l1;
    PhasePower l2;
    PhasePower l3;
    float total_active_power_kw;
    float total_apparent_power_kva;
    float system_power_factor;
    double cumulative_energy_kwh;
    float grid_frequency_hz;
    uint32_t timestamp_epoch; // Unix timestamp in seconds
};

class PowerCalculator {
public:
    PowerCalculator();

    /**
     * @brief Set nominal phase-to-neutral AC voltage (nominal 230.0V in Greece).
     */
    void setNominalVoltage(float v_l1, float v_l2, float v_l3);

    /**
     * @brief Set expected/measured phase displacement power factor (cos phi).
     * @param pf_l1 Power factor for L1 (default 0.95 for commercial load)
     * @param pf_l2 Power factor for L2 (default 0.95)
     * @param pf_l3 Power factor for L3 (default 0.95)
     */
    void setPhasePowerFactors(float pf_l1, float pf_l2, float pf_l3);

    /**
     * @brief Set grid frequency (nominal 50.0 Hz).
     */
    void setGridFrequency(float freq_hz);

    /**
     * @brief Set initial cumulative energy (e.g. restored from NVS).
     */
    void setCumulativeEnergy(double initial_kwh);

    /**
     * @brief Compute instantaneous power and update cumulative energy via trapezoidal rule.
     * @param measurements 3-phase RMS current measurements from CTSampler
     * @param current_millis Current system millis() for delta_t calculation
     * @return SystemPowerSnapshot containing complete telemetry snapshot
     */
    SystemPowerSnapshot update(const ThreePhaseMeasurement& measurements, uint32_t current_millis);

    /**
     * @brief Pure calculation function for single-phase RMS current from sample array.
     * @param ac_samples Array of zero-mean AC voltage/current samples
     * @param count Number of samples
     * @param calibration_factor Multiplier to convert sample units to Amperes
     * @return True RMS current in Amperes
     */
    static float calculateTrueRms(const float* ac_samples, size_t count, float calibration_factor = 1.0f);

    /**
     * @brief Pure numerical trapezoidal integration step.
     * @param p_prev_kw Active power at previous timestep [kW]
     * @param p_curr_kw Active power at current timestep [kW]
     * @param dt_seconds Elapsed time in seconds
     * @return Incremental energy in kWh
     */
    static double trapezoidalIntegrationStep(float p_prev_kw, float p_curr_kw, double dt_seconds);

    // Get current total cumulative energy
    double getCumulativeEnergyKWh() const { return cumulative_energy_kwh_; }

private:
    float nominal_voltage_[3];
    float power_factors_[3];
    float grid_frequency_hz_;
    double cumulative_energy_kwh_;
    float last_total_power_kw_;
    uint32_t last_update_millis_;
    bool has_prior_sample_;
};

} // namespace ems
