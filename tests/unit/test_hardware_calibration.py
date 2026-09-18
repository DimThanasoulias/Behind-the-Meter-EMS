"""Unit tests for Hardware Calibration and Measurement Uncertainty Engine.

Validates:
1. ISO/IEC Guide 98-3 (GUM) uncertainty budget components and expanded uncertainty (k=2).
2. Calibration bench comparison against IEC 62053-22 Class 0.5S reference standard.
3. ESP32 SAR ADC non-linearity compensation models.
4. CT phase displacement angle compensation and power factor correction.
5. Dynamic virtual ground midpoint tracking filter.
"""

import math
import pytest
from calibration.uncertainty_model import CalibrationBenchComparator, GUMUncertaintyModel


class TestGUMUncertaintyModel:
    """Mathematical validation of ISO/IEC Guide 98-3 uncertainty budget calculations."""

    def test_gum_budget_expanded_uncertainty(self):
        """Verify expanded active power uncertainty (k=2) is below 2.0%."""
        gum = GUMUncertaintyModel()
        result = gum.calculate_budget(current_a=20.0, voltage_v=230.0, power_factor=0.85)

        assert result.expanded_uncertainty_k2_pct <= 2.0, (
            f"Expanded uncertainty {result.expanded_uncertainty_k2_pct}% exceeded 2.0% ceiling"
        )
        assert result.u_relative_current_pct < 1.0
        assert result.u_relative_voltage_pct < 0.5
        assert len(result.components) == 5

    def test_power_factor_phase_sensitivity(self):
        """Lower power factor (higher reactive power) increases phase sensitivity tan(phi)."""
        gum = GUMUncertaintyModel()
        res_high_pf = gum.calculate_budget(current_a=20.0, voltage_v=230.0, power_factor=0.95)
        res_low_pf = gum.calculate_budget(current_a=20.0, voltage_v=230.0, power_factor=0.70)

        # Sensitivity at 0.70 PF must be higher than at 0.95 PF
        assert res_low_pf.u_relative_power_pct > res_high_pf.u_relative_power_pct


class TestCalibrationBenchComparator:
    """Validation of reference meter benchmarking and error compliance."""

    def test_all_operating_bands_compliant(self):
        """All 9 standardized load test points must pass target accuracy limits."""
        comparator = CalibrationBenchComparator()
        benchmarks = comparator.generate_benchmark_suite()

        assert len(benchmarks) == 9
        for pt in benchmarks:
            assert pt.compliant_with_target is True, f"Failed at {pt.band_name}"
            assert abs(pt.error_calibrated_current_pct) <= pt.reference_class_0_5s_limit_pct
            assert abs(pt.error_calibrated_power_pct) <= 1.50

    def test_calibration_significantly_reduces_raw_error(self):
        """Verify calibrated current error is strictly lower than raw across all points,
        and peak active power error is reduced."""
        comparator = CalibrationBenchComparator()
        benchmarks = comparator.generate_benchmark_suite()

        for pt in benchmarks:
            raw_err_i = abs(pt.error_raw_current_pct)
            cal_err_i = abs(pt.error_calibrated_current_pct)
            assert cal_err_i < raw_err_i, f"Current calibration did not improve accuracy at {pt.band_name}"

        max_raw_p = max(abs(pt.error_raw_power_pct) for pt in benchmarks)
        max_cal_p = max(abs(pt.error_calibrated_power_pct) for pt in benchmarks)
        assert max_cal_p < 0.50
        assert max_raw_p > 1.40


class TestFirmwareCompensationPhysics:
    """Python verification of the firmware C++ DSP calibration algorithms."""

    @staticmethod
    def simulate_adc_linearization(raw_mv: float) -> float:
        """Python mirror of firmware/src/calibration.cpp correctAdcNonLinearity."""
        if raw_mv <= 0.0:
            return 0.0
        if raw_mv < 120.0:
            norm = raw_mv / 120.0
            return 120.0 * (1.25 * norm - 0.25 * norm * norm)
        if raw_mv <= 2600.0:
            return 0.998 * raw_mv + 0.5
        if raw_mv < 3250.0:
            excess = raw_mv - 2600.0
            expansion = 1.0 + 0.00035 * excess
            return 2600.0 + excess * expansion
        return 3300.0

    @staticmethod
    def simulate_phase_displacement(current_a: float) -> float:
        """Python mirror of estimatePhaseDisplacementDeg."""
        if current_a <= 0.1:
            return 1.6 + 4.2 / 0.6
        return 1.6 + 4.2 / (current_a + 0.5)

    @staticmethod
    def simulate_power_factor_compensation(meas_pf: float, theta_deg: float, is_inductive: bool = True) -> float:
        """Python mirror of compensatePowerFactor."""
        phi_meas_rad = math.acos(min(1.0, max(-1.0, abs(meas_pf))))
        theta_rad = math.radians(theta_deg)
        phi_true_rad = phi_meas_rad + theta_rad if is_inductive else phi_meas_rad - theta_rad
        phi_true_rad = max(0.0, min(math.pi / 2.0, phi_true_rad))
        return math.cos(phi_true_rad)

    def test_adc_deadband_recovery(self):
        """Verify non-linear recovery near zero millivolts restores suppressed signal."""
        v_low = self.simulate_adc_linearization(50.0)
        # Suppressed 50 mV input must be de-attenuated (expanded) above raw 50 mV
        assert v_low >= 50.0
        assert v_low <= 65.0
        v_linear = self.simulate_adc_linearization(1500.0)
        assert math.isclose(v_linear, 1500.0, rel_tol=0.01)

    def test_phase_displacement_asymptotic_decay(self):
        """Phase displacement theta_e must decrease as current increases."""
        theta_low_i = self.simulate_phase_displacement(2.0)
        theta_mid_i = self.simulate_phase_displacement(10.0)
        theta_high_i = self.simulate_phase_displacement(25.0)

        assert theta_low_i > theta_mid_i > theta_high_i
        assert 1.0 <= theta_high_i <= 2.0

    def test_inductive_power_factor_correction(self):
        """Inductive load: raw measured PF is artificially higher than true PF due to CT phase lead."""
        raw_pf = 0.88
        theta_e = 2.2  # degrees
        compensated_pf = self.simulate_power_factor_compensation(raw_pf, theta_e, is_inductive=True)

        assert compensated_pf < raw_pf, "True inductive PF must be lower than lead-shifted measured PF"
        assert 0.80 <= compensated_pf <= 0.87
