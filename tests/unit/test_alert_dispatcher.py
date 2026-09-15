"""Unit tests for bot.dispatcher: FacilityStateMachine and AlertDispatcher.

Verifies:
- 5-State machine transitions (IDLE -> PENDING_BREACH -> TRIGGERED -> COOLDOWN -> CLEARED).
- 3-sample debounce filtering against single-sample noise spikes.
- 30-minute cooldown window suppressing duplicate breach notifications.
- >=25% sudden escalation power surge breaking cooldown immediately.
- 10% hysteresis release requiring load to drop <= 0.90 * threshold to clear.
- Intermediate load rejection (0.95 * threshold remains in cooldown).
- Peak window and seasonal tariff schedule enforcement.
- Proactive pre-warning alert generation (check_pre_warning).
- Low power factor alert generation (check_low_power_factor for cos phi < 0.85).
- Multi-facility registration, tenant isolation, and state reset.
- Async dispatching via ITelegramClient (MockTelegramClient).
- High-level telemetry processing pipeline.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from backend.models.alert import (
    AlertSeverity,
    AlertType,
)
from backend.models.telemetry import TelemetryPayload
from bot.dispatcher import (
    AlertDispatcher,
    AlertState,
    DispatcherAlertEvent,
    FacilityStateMachine,
)
from bot.telegram_client import MockTelegramClient
from tariff_engine.cost_calculator import CostCalculationResult


@pytest.fixture
def bakery_config() -> dict[str, Any]:
    """Standard commercial bakery threshold configuration."""
    return {
        "facility_id": "bakery-central-athens",
        "name": "Bakery Central Athens",
        "facility_type": "bakery",
        "peak_threshold_kw": 22.0,
        "warning_threshold_ratio": 0.85,
        "low_pf_threshold": 0.85,
        "cooldown_seconds": 1800,
        "hysteresis_factor": 0.90,
        "debounce_samples": 3,
        "chat_id": 999111222,
    }


@pytest.fixture
def cold_storage_config() -> dict[str, Any]:
    """Cold storage logistics threshold configuration."""
    return {
        "facility_id": "cold-storage-piraeus",
        "name": "Piraeus Cold Logistics",
        "facility_type": "cold_storage",
        "peak_threshold_kw": 25.0,
        "warning_threshold_ratio": 0.85,
        "low_pf_threshold": 0.85,
        "cooldown_seconds": 1800,
        "hysteresis_factor": 0.90,
        "debounce_samples": 3,
        "chat_id": 999333444,
    }


@pytest.fixture
def base_timestamp() -> datetime:
    """Summer peak Wednesday 15:00 UTC."""
    return datetime(2026, 7, 15, 15, 0, 0, tzinfo=timezone.utc)


class TestFacilityStateMachineDebounce:
    """Test 3-sample debounce filtering logic."""

    def test_initial_state_is_idle(self, bakery_config: dict[str, Any]):
        fsm = FacilityStateMachine(bakery_config)
        assert fsm.state == AlertState.IDLE
        assert fsm.debounce_counter == 0
        assert fsm.last_alert_time is None
        assert fsm.last_alert_kw == 0.0

    def test_three_consecutive_breaches_trigger_alert(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)
        load_kw = 28.0  # Above 22.0 kW threshold

        # Sample 1: PENDING_BREACH, count 1
        e1 = fsm.process_reading(load_kw, base_timestamp, is_peak_window=True)
        assert e1 is None
        assert fsm.state == AlertState.PENDING_BREACH
        assert fsm.debounce_counter == 1

        # Sample 2: PENDING_BREACH, count 2
        t2 = base_timestamp + timedelta(seconds=10)
        e2 = fsm.process_reading(load_kw, t2, is_peak_window=True)
        assert e2 is None
        assert fsm.state == AlertState.PENDING_BREACH
        assert fsm.debounce_counter == 2

        # Sample 3: TRIGGERED -> COOLDOWN, count 3, alert emitted
        t3 = base_timestamp + timedelta(seconds=20)
        e3 = fsm.process_reading(load_kw, t3, is_peak_window=True)
        assert e3 is not None
        assert isinstance(e3, DispatcherAlertEvent)
        assert e3.alert_type == AlertType.PEAK_BREACH
        assert e3.severity == AlertSeverity.WARNING
        assert fsm.state == AlertState.COOLDOWN
        assert fsm.last_alert_kw == load_kw
        assert fsm.last_alert_time == t3
        assert "ΠΡΟΣΟΧΗ: ΥΠΕΡΒΑΣΗ ΟΡΙΟΥ" in e3.message
        assert "28.0 kW" in e3.message
        assert "Bakery Central Athens" in e3.message

    def test_single_noise_spike_does_not_trigger_alert(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)

        # 1 spike above threshold
        e1 = fsm.process_reading(30.0, base_timestamp, is_peak_window=True)
        assert e1 is None
        assert fsm.state == AlertState.PENDING_BREACH
        assert fsm.debounce_counter == 1

        # Followed by normal reading
        t2 = base_timestamp + timedelta(seconds=10)
        e2 = fsm.process_reading(15.0, t2, is_peak_window=True)
        assert e2 is None
        assert fsm.state == AlertState.IDLE
        assert fsm.debounce_counter == 0

    def test_two_spikes_then_drop_resets_debounce(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)

        # Sample 1 & 2 above threshold
        fsm.process_reading(26.0, base_timestamp, is_peak_window=True)
        fsm.process_reading(26.0, base_timestamp + timedelta(seconds=10), is_peak_window=True)
        assert fsm.debounce_counter == 2

        # Drop to normal
        fsm.process_reading(14.0, base_timestamp + timedelta(seconds=20), is_peak_window=True)
        assert fsm.debounce_counter == 1

        # Second drop to normal
        fsm.process_reading(14.0, base_timestamp + timedelta(seconds=30), is_peak_window=True)
        assert fsm.debounce_counter == 0
        assert fsm.state == AlertState.IDLE

    def test_offpeak_high_load_does_not_trigger_breach(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)
        # High power (40 kW) during off-peak window (is_peak_window=False)
        for i in range(5):
            t = base_timestamp + timedelta(seconds=i * 10)
            e = fsm.process_reading(40.0, t, is_peak_window=False)
            assert e is None

        assert fsm.state == AlertState.IDLE
        assert fsm.debounce_counter == 0


class TestFacilityStateMachineCooldownAndEscalation:
    """Test 30-minute cooldown suppression and >=25% escalation bypass."""

    def test_cooldown_suppresses_duplicate_breaches(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)
        # Trigger initial alert (3 samples at 28 kW)
        for i in range(3):
            t = base_timestamp + timedelta(seconds=i * 10)
            alert = fsm.process_reading(28.0, t, is_peak_window=True)

        assert alert is not None
        assert fsm.state == AlertState.COOLDOWN

        # Sample 4, 5, 6 during cooldown (at 28 kW and 29 kW)
        for i in range(3, 10):
            t = base_timestamp + timedelta(seconds=i * 10)
            dup = fsm.process_reading(28.5, t, is_peak_window=True)
            assert dup is None  # Suppressed by cooldown

        assert fsm.state == AlertState.COOLDOWN
        assert fsm.last_alert_time == base_timestamp + timedelta(seconds=20)

    def test_cooldown_expires_after_30_minutes(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)
        # Trigger initial alert
        for i in range(3):
            t = base_timestamp + timedelta(seconds=i * 10)
            fsm.process_reading(28.0, t, is_peak_window=True)

        # 31 minutes later (1860 seconds > 1800s cooldown), power still 28 kW
        t_expired = base_timestamp + timedelta(seconds=20 + 1860)
        alert_after_cd = fsm.process_reading(28.0, t_expired, is_peak_window=True)
        assert alert_after_cd is not None
        assert alert_after_cd.alert_type == AlertType.PEAK_BREACH
        assert fsm.last_alert_time == t_expired

    def test_escalation_triggers_immediate_alert_during_cooldown(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)
        # Trigger initial alert at 24.0 kW
        for i in range(3):
            t = base_timestamp + timedelta(seconds=i * 10)
            fsm.process_reading(24.0, t, is_peak_window=True)

        assert fsm.state == AlertState.COOLDOWN

        # Sudden surge to 31.0 kW (jump >= 24.0 * 1.25 = 30.0 kW, ~29% increase)
        t_surge = base_timestamp + timedelta(seconds=60)
        esc_event = fsm.process_reading(31.0, t_surge, is_peak_window=True)
        assert esc_event is not None
        assert esc_event.alert_type == AlertType.PEAK_BREACH
        assert esc_event.severity == AlertSeverity.CRITICAL
        assert "ΚΛΙΜΑΚΩΣΗ ΥΠΕΡΒΑΣΗΣ" in esc_event.message
        assert esc_event.metadata.get("is_escalation") is True
        assert fsm.last_alert_kw == 31.0

    def test_minor_jump_does_not_trigger_escalation(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)
        # Trigger initial alert at 24.0 kW
        for i in range(3):
            t = base_timestamp + timedelta(seconds=i * 10)
            fsm.process_reading(24.0, t, is_peak_window=True)

        # Power rises to 26.0 kW (+8.3% < 25%)
        t_minor = base_timestamp + timedelta(seconds=60)
        e = fsm.process_reading(26.0, t_minor, is_peak_window=True)
        assert e is None  # Suppressed by cooldown, not an escalation


class TestFacilityStateMachineHysteresis:
    """Test 10% release hysteresis recovery logic."""

    def test_load_dropping_below_90_percent_triggers_recovery(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)
        # Trigger breach alert (threshold is 22.0 kW)
        for i in range(3):
            t = base_timestamp + timedelta(seconds=i * 10)
            fsm.process_reading(28.0, t, is_peak_window=True)

        # Load drops to 18.0 kW (<= 22.0 * 0.90 = 19.8 kW)
        t_safe = base_timestamp + timedelta(seconds=60)
        rec_event = fsm.process_reading(18.0, t_safe, is_peak_window=True)
        assert rec_event is not None
        assert rec_event.alert_type == AlertType.NORMALIZED
        assert rec_event.severity == AlertSeverity.INFO
        assert "ΟΜΑΛΟΠΟΙΗΣΗ ΚΑΤΑΝΑΛΩΣΗΣ" in rec_event.message
        assert "18.0 kW" in rec_event.message
        assert fsm.state == AlertState.IDLE
        assert fsm.debounce_counter == 0

    def test_load_at_95_percent_remains_in_cooldown(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)
        # Trigger breach alert (threshold 22.0 kW)
        for i in range(3):
            t = base_timestamp + timedelta(seconds=i * 10)
            fsm.process_reading(28.0, t, is_peak_window=True)

        # Load drops to 20.9 kW (95% of 22 kW: below threshold, but ABOVE 19.8 kW hysteresis)
        t_mid = base_timestamp + timedelta(seconds=60)
        res = fsm.process_reading(20.9, t_mid, is_peak_window=True)
        assert res is None  # Still in COOLDOWN, cannot clear yet
        assert fsm.state == AlertState.COOLDOWN

    def test_peak_window_expiration_triggers_recovery(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)
        # Trigger breach alert during peak window
        for i in range(3):
            t = base_timestamp + timedelta(seconds=i * 10)
            fsm.process_reading(28.0, t, is_peak_window=True)

        # Peak window ends (is_peak_window=False) even if load is still 28 kW
        t_end = base_timestamp + timedelta(hours=2)
        rec_event = fsm.process_reading(28.0, t_end, is_peak_window=False)
        assert rec_event is not None
        assert rec_event.alert_type == AlertType.NORMALIZED
        assert fsm.state == AlertState.IDLE


class TestFacilityStateMachinePreWarningAndPowerFactor:
    """Test proactive pre-warning and low power factor checks."""

    def test_check_pre_warning_approaching_threshold(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)
        # Warning threshold is 22.0 * 0.85 = 18.7 kW; power is 19.5 kW
        event = fsm.check_pre_warning(power_kw=19.5, timestamp=base_timestamp)
        assert event is not None
        assert event.alert_type == AlertType.PRE_WARNING
        assert "ΠΡΟΕΙΔΟΠΟΙΗΣΗ" in event.message
        assert "19.5 kW" in event.message

        # Cooldown prevents duplicate pre-warning within 1800s
        t_soon = base_timestamp + timedelta(minutes=5)
        dup = fsm.check_pre_warning(power_kw=19.8, timestamp=t_soon)
        assert dup is None

    def test_check_pre_warning_ignored_when_load_is_low(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)
        # Power is 12.0 kW (< 18.7 kW), no minutes_until_peak
        event = fsm.check_pre_warning(power_kw=12.0, timestamp=base_timestamp)
        assert event is None

    def test_check_low_power_factor_triggers_alert(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)
        # cos phi = 0.74 < 0.85
        event = fsm.check_low_power_factor(
            power_factor=0.74, power_kw=20.0, timestamp=base_timestamp
        )
        assert event is not None
        assert event.alert_type == AlertType.LOW_POWER_FACTOR
        assert event.severity == AlertSeverity.WARNING
        assert "ΧΑΜΗΛΟΣ ΣΥΝΤΕΛΕΣΤΗΣ ΙΣΧΥΟΣ" in event.message
        assert "0.74" in event.message

        # Cooldown suppresses duplicate low PF alert
        dup = fsm.check_low_power_factor(
            power_factor=0.72, power_kw=20.0, timestamp=base_timestamp + timedelta(seconds=60)
        )
        assert dup is None

    def test_check_low_power_factor_normal_pf_ignored(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        fsm = FacilityStateMachine(bakery_config)
        # Good cos phi >= 0.85
        assert fsm.check_low_power_factor(0.96, 20.0, base_timestamp) is None
        # Zero or negative guarded
        assert fsm.check_low_power_factor(0.0, 20.0, base_timestamp) is None
        assert fsm.check_low_power_factor(-0.5, 20.0, base_timestamp) is None


class TestAlertDispatcherMultiFacilityAndAsync:
    """Test AlertDispatcher multi-facility isolation and Telegram dispatch."""

    def test_multi_facility_registration_and_isolation(
        self, bakery_config: dict[str, Any], cold_storage_config: dict[str, Any], base_timestamp: datetime
    ):
        dispatcher = AlertDispatcher()
        dispatcher.register_facility(bakery_config)
        dispatcher.register_facility(cold_storage_config)

        assert dispatcher.get_facility_state("bakery-central-athens") == "IDLE"
        assert dispatcher.get_facility_state("cold-storage-piraeus") == "IDLE"

        # Send 3 breaches to bakery (28.0 kW > 22.0 kW)
        for i in range(3):
            t = base_timestamp + timedelta(seconds=i * 10)
            dispatcher.process_reading(28.0, t, is_peak_window=True, facility_id="bakery-central-athens")

        # Bakery should be in COOLDOWN, Cold Storage should still be IDLE
        assert dispatcher.get_facility_state("bakery-central-athens") == "COOLDOWN"
        assert dispatcher.get_facility_state("cold-storage-piraeus") == "IDLE"

        # Reset bakery
        dispatcher.reset_facility_state("bakery-central-athens")
        assert dispatcher.get_facility_state("bakery-central-athens") == "IDLE"

    def test_process_reading_and_dispatch_with_mock_client(
        self, bakery_config: dict[str, Any], base_timestamp: datetime
    ):
        import asyncio

        async def _run():
            mock_client = MockTelegramClient()
            dispatcher = AlertDispatcher(facility_config=bakery_config, telegram_client=mock_client)

            # 3 readings to breach
            for i in range(3):
                t = base_timestamp + timedelta(seconds=i * 10)
                await dispatcher.process_reading_and_dispatch(
                    power_kw=28.0,
                    timestamp=t,
                    is_peak_window=True,
                    facility_id="bakery-central-athens",
                    chat_id=999111222,
                )

            assert mock_client.message_count() == 1
            msg = mock_client.get_last_message()
            assert msg is not None
            assert msg["chat_id"] == 999111222
            assert "ΠΡΟΣΟΧΗ: ΥΠΕΡΒΑΣΗ ΟΡΙΟΥ" in msg["text"]
            assert len(dispatcher.dispatched_alerts) == 1

        asyncio.run(_run())

    def test_process_telemetry_full_pipeline(
        self, bakery_config: dict[str, Any], valid_telemetry_payload: TelemetryPayload, base_timestamp: datetime
    ):
        import asyncio

        async def _run():
            mock_client = MockTelegramClient()
            dispatcher = AlertDispatcher(facility_config=bakery_config, telegram_client=mock_client)

            # Modify payload to represent breach in peak window
            valid_telemetry_payload.timestamp = base_timestamp
            valid_telemetry_payload.total_active_power_kw = 32.0

            cost_res = CostCalculationResult(
                current_rate_eur_per_kwh=0.25,
                running_cost_eur_per_h=8.0,
                incremental_cost_eur=0.10,
                is_peak_window=True,
                is_excess_breach=True,
                excess_power_kw=10.0,
                projected_excess_penalty_eur=15.50,
            )

            # Ingest 3 times
            res = None
            for i in range(3):
                valid_telemetry_payload.timestamp = base_timestamp + timedelta(seconds=i * 10)
                res = await dispatcher.process_telemetry(
                    payload=valid_telemetry_payload,
                    cost_res_or_profile=cost_res,
                    facility_config=bakery_config,
                )

            assert res is not None
            assert res.alert_type == AlertType.PEAK_BREACH
            assert mock_client.message_count() == 1
            assert "€15.50" in mock_client.get_last_message()["text"]

        asyncio.run(_run())

