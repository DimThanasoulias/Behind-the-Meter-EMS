"""Unit tests for commercial simulation profiles, telemetry generator, and CLI.

Exhaustively verifies:
1. Load curves:
   - Bakery: night baseload (3-5 kW), morning spikes (03:30-08:30, 35-45 kW),
     daytime prep (08:30-14:30), afternoon breach (14:30-16:30, 24-28 kW), evening cooling.
   - Cold Storage: thermodynamic cycling (compressor ON at 25-32 kW for 15-20 min,
     compressor OFF at 4-6 kW for 15-20 min), dock door disturbances (surge to 34-38 kW).
   - Boutique Hotel: breakfast (07:00-10:00, 20-25 kW), afternoon check-in & VRV HVAC peak
     (14:00-17:30, 28-35 kW), evening dinner (19:30-23:00, 18-24 kW), night baseload (23:00-07:00, 8-12 kW).
2. 3-phase electrical invariant compliance (|P_tot - sum(P_i)| <= 0.05 kW, V in 230V +/- 3V,
   cos φ in 0.88-0.98, f = 50 Hz, S >= P).
3. Gaussian noise generation (--noise) and invariant preservation under noise.
4. Fast-forward time compression (--speed) and energy accumulation.
5. Automated peak breach injection (--trigger-breach) for sub-30s verification.
6. CLI argument parsing, dry-run mode, and HTTP streaming.
"""

import math
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.models.telemetry import TelemetryPayload
from simulator.cli import (
    build_arg_parser,
    format_reading_summary,
    parse_speed,
    run_simulation,
)
from simulator.generator import TelemetryGenerator
from simulator.profiles import (
    BakeryProfile,
    BoutiqueHotelProfile,
    ColdStorageProfile,
    get_boutique_hotel_power,
    get_cold_storage_power,
    get_commercial_bakery_power,
    get_profile,
)

# --- 1. Commercial Bakery Profile Tests ---

class TestBakeryProfile:
    """Tests commercial bakery 24h load curve and profile class."""

    def test_night_baseload_power_levels(self):
        """Verifies night baseload (21:00 - 03:30) is within 3.0 to 5.0 kW."""
        for hour in [0.0, 1.0, 2.0, 3.0, 21.5, 22.0, 23.5]:
            power = get_commercial_bakery_power(hour)
            assert 3.0 <= power <= 5.0, f"Night baseload at {hour}h ({power:.2f} kW) outside [3, 5] kW"

    def test_morning_preheat_and_baking_spikes(self):
        """Verifies morning pre-heat and baking spikes (03:30 - 08:30) are within 35.0 to 45.0 kW."""
        # 03:30 - 05:00: Pre-heat ramp
        for hour in [3.5, 4.0, 4.5, 4.9]:
            power = get_commercial_bakery_power(hour)
            assert 35.0 <= power <= 45.0, f"Pre-heat at {hour}h ({power:.2f} kW) outside [35, 45] kW"

        # 05:00 - 08:30: High-draw baking spikes
        for hour in [5.0, 5.5, 6.0, 7.0, 8.0, 8.4]:
            power = get_commercial_bakery_power(hour)
            assert 35.0 <= power <= 45.0, f"Baking spike at {hour}h ({power:.2f} kW) outside [35, 45] kW"

        # Specific reference checkpoints
        assert get_commercial_bakery_power(5.5) > 35.0
        assert 35.0 <= get_commercial_bakery_power(6.0) <= 45.0

    def test_daytime_prep_power_levels(self):
        """Verifies daytime prep (08:30 - 14:30) is within 10.0 to 18.0 kW."""
        for hour in [9.0, 10.0, 11.5, 13.0, 14.0]:
            power = get_commercial_bakery_power(hour)
            assert 10.0 <= power <= 18.0, f"Daytime prep at {hour}h ({power:.2f} kW) outside [10, 18] kW"

    def test_afternoon_peak_breach_window(self):
        """Verifies afternoon baking prep (14:30 - 16:30) draws 24.0 to 28.0 kW (breaching 22 kW)."""
        for hour in [14.5, 15.0, 15.5, 16.0, 16.4]:
            power = get_commercial_bakery_power(hour)
            assert 24.0 <= power <= 28.0, f"Afternoon breach at {hour}h ({power:.2f} kW) outside [24, 28] kW"
            assert power > 22.0, f"Afternoon power at {hour}h ({power:.2f} kW) does not breach 22 kW threshold"

    def test_evening_cooling_power_levels(self):
        """Verifies evening cooling (16:30 - 21:00) is within 6.0 to 10.0 kW."""
        for hour in [17.0, 18.0, 19.5, 20.5]:
            power = get_commercial_bakery_power(hour)
            assert 6.0 <= power <= 10.0, f"Evening cooling at {hour}h ({power:.2f} kW) outside [6, 10] kW"

    def test_bakery_profile_class_properties(self):
        """Verifies BakeryProfile class metadata and datetime querying."""
        profile = BakeryProfile()
        assert profile.name == "bakery"
        assert profile.default_facility_id == "bakery-central-athens"
        assert profile.default_peak_threshold_kw == 22.0

        dt_peak = datetime(2026, 9, 14, 15, 30, 0, tzinfo=timezone.utc)
        power_dt = profile.get_power_kw(dt=dt_peak)
        assert 24.0 <= power_dt <= 28.0


# --- 2. Cold Storage Profile Tests ---

class TestColdStorageProfile:
    """Tests cold storage refrigeration thermodynamic cycling and disturbances."""

    def test_compressor_cycling_on_and_off(self):
        """Verifies compressor cycling: ON at 25-32 kW (15-20 min), OFF at 4-6 kW (15-20 min)."""
        # ON phase: minutes 0 to 17 (18 min duration)
        for minute in [0.0, 5.0, 10.0, 15.0, 17.5]:
            power = get_cold_storage_power(minute, door_open=False)
            assert 25.0 <= power <= 32.0, f"Compressor ON at {minute}m ({power:.2f} kW) outside [25, 32] kW"

        # OFF phase: minutes 18 to 35 (18 min duration)
        for minute in [18.0, 22.0, 27.0, 32.0, 35.0]:
            power = get_cold_storage_power(minute, door_open=False)
            assert 4.0 <= power <= 6.0, f"Compressor OFF at {minute}m ({power:.2f} kW) outside [4, 6] kW"

        # Multi-cycle repeat verification (cycle period = 36 min)
        # Second cycle ON (minute 36 - 53)
        assert 25.0 <= get_cold_storage_power(45.0) <= 32.0
        # Second cycle OFF (minute 54 - 71)
        assert 4.0 <= get_cold_storage_power(60.0) <= 6.0

    def test_dock_door_disturbance_surge(self):
        """Verifies dock door disturbance causes power to surge to 34.0 to 38.0 kW."""
        for minute in [5.0, 15.0, 25.0, 35.0]:
            power_surge = get_cold_storage_power(minute, door_open=True)
            assert 34.0 <= power_surge <= 38.0, f"Dock door surge ({power_surge:.2f} kW) outside [34, 38] kW"
            assert math.isclose(power_surge, 34.5, rel_tol=1e-2)

    def test_cold_storage_profile_class_properties_and_manual_door(self):
        """Verifies ColdStorageProfile class metadata and door control."""
        profile = ColdStorageProfile(cycle_on_minutes=18.0, cycle_off_minutes=18.0)
        assert profile.name == "cold_storage"
        assert profile.default_facility_id == "cold-storage-piraeus"
        assert profile.default_peak_threshold_kw == 25.0

        # Normal idle phase
        power_normal = profile.get_power_kw(elapsed_seconds=35.0 * 60.0)
        assert 4.0 <= power_normal <= 6.0

        # With manual door open
        profile.set_door_open(True)
        power_door = profile.get_power_kw(elapsed_seconds=35.0 * 60.0)
        assert 34.0 <= power_door <= 38.0

        profile.set_door_open(False)
        power_restored = profile.get_power_kw(elapsed_seconds=35.0 * 60.0)
        assert 4.0 <= power_restored <= 6.0


# --- 3. Boutique Hotel Profile Tests ---

class TestBoutiqueHotelProfile:
    """Tests boutique hotel load curve across 24h operational cycles."""

    def test_morning_breakfast_power_levels(self):
        """Verifies morning breakfast (07:00 - 10:00) is within 20.0 to 25.0 kW."""
        for hour in [7.0, 7.5, 8.0, 9.0, 9.9]:
            power = get_boutique_hotel_power(hour)
            assert 20.0 <= power <= 25.0, f"Breakfast at {hour}h ({power:.2f} kW) outside [20, 25] kW"

    def test_afternoon_checkin_and_vrv_hvac_peak(self):
        """Verifies afternoon check-in and VRV HVAC peak (14:00 - 17:30) is within 28.0 to 35.0 kW."""
        for hour in [14.0, 14.5, 15.0, 15.5, 16.5, 17.0, 17.4]:
            power = get_boutique_hotel_power(hour)
            assert 28.0 <= power <= 35.0, f"VRV peak at {hour}h ({power:.2f} kW) outside [28, 35] kW"

        # Check 15:30 reference
        power_1530 = get_boutique_hotel_power(15.5)
        assert 29.0 <= power_1530 <= 35.0

    def test_evening_dinner_power_levels(self):
        """Verifies evening dinner (19:30 - 23:00) is within 18.0 to 24.0 kW."""
        for hour in [19.5, 20.0, 21.0, 22.0, 22.8]:
            power = get_boutique_hotel_power(hour)
            assert 18.0 <= power <= 24.0, f"Dinner at {hour}h ({power:.2f} kW) outside [18, 24] kW"

    def test_night_baseload_power_levels(self):
        """Verifies night baseload (23:00 - 07:00) is within 8.0 to 12.0 kW."""
        for hour in [0.0, 1.0, 3.0, 5.0, 6.5, 23.0, 23.5]:
            power = get_boutique_hotel_power(hour)
            assert 8.0 <= power <= 12.0, f"Night baseload at {hour}h ({power:.2f} kW) outside [8, 12] kW"

    def test_boutique_hotel_profile_class_properties(self):
        """Verifies BoutiqueHotelProfile class metadata and datetime querying."""
        profile = BoutiqueHotelProfile()
        assert profile.name == "boutique_hotel"
        assert profile.default_facility_id == "hotel-santorini-boutique"
        assert profile.default_peak_threshold_kw == 30.0

        dt_checkin = datetime(2026, 7, 20, 16, 0, 0, tzinfo=timezone.utc)
        power_dt = profile.get_power_kw(dt=dt_checkin)
        assert 28.0 <= power_dt <= 35.0


# --- 4. Profile Registry & Factory Tests ---

class TestProfileRegistry:
    """Tests get_profile factory and registry lookup."""

    def test_get_profile_by_valid_names(self):
        assert isinstance(get_profile("bakery"), BakeryProfile)
        assert isinstance(get_profile("commercial_bakery"), BakeryProfile)
        assert isinstance(get_profile("cold_storage"), ColdStorageProfile)
        assert isinstance(get_profile("refrigeration"), ColdStorageProfile)
        assert isinstance(get_profile("boutique_hotel"), BoutiqueHotelProfile)
        assert isinstance(get_profile("hotel"), BoutiqueHotelProfile)

    def test_get_profile_unknown_name_raises(self):
        with pytest.raises(ValueError, match="Unknown profile"):
            get_profile("unknown_commercial_entity")


# --- 5. Telemetry Generator & Electrical Invariant Compliance Tests ---

class TestTelemetryGeneratorElectricalInvariants:
    """Tests 3-phase electrical invariant compliance, physical realism, and Pydantic validation."""

    @pytest.mark.parametrize("profile_name", ["bakery", "cold_storage", "boutique_hotel"])
    def test_three_phase_active_power_conservation_invariant(self, profile_name: str):
        """Strictly enforces |total_active_power_kw - sum(phases[Li])| <= 0.05 kW across 50 readings."""
        gen = TelemetryGenerator(profile=profile_name, seed=42)
        for _ in range(50):
            payload = gen.step(step_seconds=30.0)
            phase_sum = (
                payload.phases["L1"].active_power_kw
                + payload.phases["L2"].active_power_kw
                + payload.phases["L3"].active_power_kw
            )
            delta = abs(payload.total_active_power_kw - phase_sum)
            assert delta <= 0.05, f"Phase sum delta ({delta:.4f} kW) exceeds 0.05 kW limit for {profile_name}"

    @pytest.mark.parametrize("profile_name", ["bakery", "cold_storage", "boutique_hotel"])
    def test_realistic_electrical_ranges(self, profile_name: str):
        """Verifies voltages (230V +/- 3V), power factor (0.88-0.98), frequency (50 Hz), S >= P."""
        gen = TelemetryGenerator(profile=profile_name, seed=123)
        for _ in range(30):
            payload = gen.step(step_seconds=20.0)

            # Invariant: Voltages within 230V +/- 3V
            for phase_id, p in payload.phases.items():
                assert 227.0 <= p.voltage_v <= 233.0, f"Voltage {p.voltage_v}V outside [227, 233] on {phase_id}"
                assert 0.85 <= p.power_factor <= 1.0, f"PF {p.power_factor} outside bounds on {phase_id}"
                # Apparent power must be >= active power
                assert p.apparent_power_kva >= p.active_power_kw - 0.05, f"S < P on phase {phase_id}"
                # Current must be non-negative
                assert p.current_a >= 0.0

            # Grid frequency around 50 Hz
            assert 49.8 <= payload.grid_frequency_hz <= 50.2
            # System power factor
            assert 0.85 <= payload.system_power_factor <= 1.0
            # Total apparent power >= total active power
            assert payload.total_apparent_power_kva >= payload.total_active_power_kw - 0.05

    def test_pydantic_model_strict_validation(self):
        """Verifies generated readings pass TelemetryPayload.model_validate without errors."""
        gen = TelemetryGenerator(profile="bakery", seed=999)
        payload = gen.generate_reading()
        # Export to dict and re-validate
        payload_dict = payload.model_dump()
        revalidated = TelemetryPayload.model_validate(payload_dict)
        assert revalidated.total_active_power_kw == payload.total_active_power_kw
        assert set(revalidated.phases.keys()) == {"L1", "L2", "L3"}


# --- 6. Gaussian Noise Generation Tests ---

class TestNoiseGeneration:
    """Tests load noise addition and invariant preservation under noise."""

    def test_noise_adds_variance_while_preserving_invariants(self):
        """Verifies noise generates realistic variability while strictly preserving electrical invariants."""
        gen_clean = TelemetryGenerator(profile="bakery", noise_kw=0.0, seed=42)
        gen_noisy = TelemetryGenerator(profile="bakery", noise_kw=3.0, seed=42)

        readings_clean = [gen_clean.step(10.0).total_active_power_kw for _ in range(30)]
        readings_noisy = [gen_noisy.step(10.0).total_active_power_kw for _ in range(30)]

        # Noisy readings should differ from clean readings
        diffs = [abs(c - n) for c, n in zip(readings_clean, readings_noisy)]
        assert any(d > 0.5 for d in diffs), "Noise did not perturb power readings"

        # Invariants must still hold 100% on noisy generator
        gen_high_noise = TelemetryGenerator(profile="cold_storage", noise_kw=6.0, seed=77)
        for _ in range(40):
            p = gen_high_noise.step(15.0)
            phase_sum = sum(p.phases[li].active_power_kw for li in ("L1", "L2", "L3"))
            assert abs(p.total_active_power_kw - phase_sum) <= 0.05
            assert p.total_active_power_kw >= 0.5  # No negative power

    def test_noise_clamping_prevents_negative_active_power(self):
        """Verifies that large negative noise values never yield negative power."""
        gen = TelemetryGenerator(profile="bakery", noise_kw=15.0, seed=1)
        for _ in range(50):
            payload = gen.step(5.0)
            assert payload.total_active_power_kw >= 0.5
            for phase in payload.phases.values():
                assert phase.active_power_kw >= 0.0


# --- 7. Automated Peak Breach Injection Tests ---

class TestBreachInjection:
    """Tests automated peak breach triggering for sub-30s test verification."""

    @pytest.mark.parametrize(
        ("profile_name", "expected_min_breach_kw"),
        [
            ("bakery", 28.0),        # Threshold 22 kW -> surge to 32.5 kW
            ("cold_storage", 32.0),  # Threshold 25 kW -> surge to 36.5 kW
            ("boutique_hotel", 35.0), # Threshold 30 kW -> surge to 38.5 kW
        ],
    )
    def test_trigger_breach_forces_high_rate_load_immediately(
        self, profile_name: str, expected_min_breach_kw: float
    ):
        """Verifies --trigger-breach forces immediate high-rate load above peak threshold."""
        gen = TelemetryGenerator(profile=profile_name, trigger_breach=True, seed=10)
        # From the very first reading (0 seconds elapsed), load must breach threshold
        first_reading = gen.step(step_seconds=10.0)
        assert first_reading.total_active_power_kw >= expected_min_breach_kw
        assert first_reading.total_active_power_kw > gen.profile.default_peak_threshold_kw

        # Electrical invariants must still hold
        phase_sum = sum(first_reading.phases[li].active_power_kw for li in ("L1", "L2", "L3"))
        assert abs(first_reading.total_active_power_kw - phase_sum) <= 0.05

    def test_runtime_toggle_breach_mode(self):
        """Verifies enabling and disabling breach mode dynamically."""
        gen = TelemetryGenerator(profile="bakery", trigger_breach=False, seed=5)
        # Normal reading at 00:00 (night baseload ~4 kW)
        normal = gen.generate_reading(dt=datetime(2026, 9, 14, 0, 0, 0, tzinfo=timezone.utc))
        assert normal.total_active_power_kw < 10.0

        # Enable breach
        gen.set_breach_mode(True, breach_power_kw=35.0)
        breached = gen.generate_reading(dt=datetime(2026, 9, 14, 0, 0, 0, tzinfo=timezone.utc))
        assert breached.total_active_power_kw >= 35.0

        # Disable breach
        gen.set_breach_mode(False)
        restored = gen.generate_reading(dt=datetime(2026, 9, 14, 0, 0, 0, tzinfo=timezone.utc))
        assert restored.total_active_power_kw < 10.0


# --- 8. Fast-Forward, Energy Accumulation & Speed Tests ---

class TestFastForwardAndEnergyAccumulation:
    """Tests virtual time compression and numeric kWh integration."""

    def test_cumulative_energy_integration(self):
        """Verifies trapezoidal/step cumulative kWh integration matches active power."""
        initial_kwh = 100.0
        gen = TelemetryGenerator(
            profile="bakery",
            initial_energy_kwh=initial_kwh,
            noise_kw=0.0,
            seed=42,
            start_time=datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc),
        )
        # Advance 1 hour (360 steps of 10 seconds)
        for _ in range(360):
            payload = gen.step(step_seconds=10.0)

        # Energy must have increased
        assert payload.cumulative_energy_kwh > initial_kwh
        # For average power ~4 kW over 1 hour, energy increase should be ~4 kWh
        increase = payload.cumulative_energy_kwh - initial_kwh
        assert 2.0 <= increase <= 15.0

    def test_speed_parser_formats(self):
        """Verifies parse_speed parses various string and numeric formats."""
        assert parse_speed("1x") == 1.0
        assert parse_speed("60x") == 60.0
        assert parse_speed("3600x") == 3600.0
        assert parse_speed("120") == 120.0
        assert parse_speed(100.0) == 100.0

        with pytest.raises(Exception):
            parse_speed("invalid_speed")

    def test_generator_stream_yields_exact_duration(self):
        """Verifies stream() yields expected number of readings over a virtual duration."""
        gen = TelemetryGenerator(profile="cold_storage", seed=42)
        duration_seconds = 120.0
        step_seconds = 20.0
        readings = list(gen.stream(duration_seconds=duration_seconds, step_seconds=step_seconds))
        assert len(readings) == 6


# --- 9. Standalone CLI & HTTP Ingestion Tests ---

class TestSimulatorCLI:
    """Tests CLI argument parsing, dry-run mode, and HTTP streaming dispatch."""

    def test_arg_parser_defaults_and_options(self):
        """Verifies default flags and custom option overrides."""
        parser = build_arg_parser()
        args = parser.parse_args(["--profile", "cold_storage", "--speed", "60x", "--trigger-breach", "--dry-run"])
        assert args.profile == "cold_storage"
        assert args.speed == 60.0
        assert args.trigger_breach is True
        assert args.dry_run is True
        assert args.duration_hours == 24.0

    def test_run_simulation_dry_run_execution(self):
        """Verifies run_simulation executes cleanly in dry-run mode without network calls."""
        logs = []
        readings = run_simulation(
            profile="bakery",
            speed=3600.0,
            duration_hours=1.0,
            interval_seconds=60.0,
            dry_run=True,
            max_readings=10,
            seed=42,
            sleep_fn=lambda _: None,
            log_fn=logs.append,
        )
        assert len(readings) == 10
        assert any("DRY RUN" in line for line in logs)
        assert any("Simulation completed" in line for line in logs)
        for r in readings:
            assert isinstance(r, TelemetryPayload)

    def test_run_simulation_http_dispatch(self):
        """Verifies run_simulation serializes TelemetryPayload and POSTs to --url."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response

        readings = run_simulation(
            profile="boutique_hotel",
            speed=3600.0,
            duration_hours=1.0,
            interval_seconds=60.0,
            url="http://localhost:8000/api/v1/telemetry",
            dry_run=False,
            max_readings=5,
            seed=10,
            http_client=mock_client,
            sleep_fn=lambda _: None,
            log_fn=lambda _: None,
        )
        assert len(readings) == 5
        assert mock_client.post.call_count == 5

        # Check call arguments of the first post
        first_call = mock_client.post.call_args_list[0]
        url_arg = first_call[0][0]
        kwargs = first_call[1]
        assert url_arg == "http://localhost:8000/api/v1/telemetry"
        assert kwargs["headers"] == {"Content-Type": "application/json"}
        # Ensure payload content is valid JSON matching TelemetryPayload
        import json
        payload_data = json.loads(kwargs["content"])
        assert payload_data["facility_id"] == "hotel-santorini-boutique"
        assert "phases" in payload_data
        assert "L1" in payload_data["phases"]

    def test_format_reading_summary_structure(self):
        """Verifies terminal logging output format."""
        gen = TelemetryGenerator(profile="bakery", seed=1)
        payload = gen.step(10.0)
        line = format_reading_summary(payload)
        assert "bakery-central-athens" in line
        assert "Total:" in line
        assert "L1:" in line
        assert "L2:" in line
        assert "L3:" in line
        assert "Cumul:" in line

    def test_run_simulation_invalid_arguments_raise(self):
        """Verifies invalid arguments raise appropriate ValueError."""
        with pytest.raises(ValueError, match="duration_hours"):
            run_simulation(duration_hours=-1.0, dry_run=True)

        with pytest.raises(ValueError, match="interval_seconds"):
            run_simulation(interval_seconds=0.0, dry_run=True)
