"""Unit test suite for core telemetry and alert models, validating electrical invariants,

bounds checking, serialization, and edge cases.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.models.alert import (
    AlertEvent,
    AlertSeverity,
    AlertType,
)
from backend.models.telemetry import (
    TelemetryPayload,
)
from bot.telegram_client import LiveTelegramClient

# =====================================================================
# 1. Normal Serialization & Model Instantiation
# =====================================================================

def test_telemetry_payload_valid_deserialization(valid_telemetry_dict):
    """Test that a well-formed telemetry payload deserializes into TelemetryPayload."""
    payload = TelemetryPayload.model_validate(valid_telemetry_dict)

    assert payload.device_id == "esp32-ems-001"
    assert payload.facility_id == "bakery-central-athens"
    assert payload.total_active_power_kw == 17.90
    assert payload.total_apparent_power_kva == 18.27
    assert payload.system_power_factor == 0.98
    assert payload.cumulative_energy_kwh == 142.50
    assert payload.grid_frequency_hz == 50.01
    assert payload.wifi_rssi_dbm == -62.0


def test_telemetry_payload_phase_access(valid_telemetry_payload):
    """Test both dictionary key access and attribute access on phases."""
    phases = valid_telemetry_payload.phases

    # Test dictionary indexing
    assert phases["L1"].voltage_v == 230.2
    assert phases["L1"].current_a == 26.4
    assert phases["L1"].active_power_kw == 5.95
    assert phases["L1"].power_factor == 0.98

    assert phases["L2"].voltage_v == 229.8
    assert phases["L2"].current_a == 25.8
    assert phases["L2"].active_power_kw == 5.82

    assert phases["L3"].voltage_v == 231.0
    assert phases["L3"].current_a == 27.1
    assert phases["L3"].active_power_kw == 6.13

    # Test attribute dot-notation access via PhaseDict
    assert phases.L1.voltage_v == 230.2
    assert phases.L2.current_a == 25.8
    assert phases.L3.active_power_kw == 6.13


def test_telemetry_payload_model_dump_roundtrip(valid_telemetry_payload):
    """Test round-trip serialization: model -> dict -> json -> model."""
    dumped_dict = valid_telemetry_payload.model_dump()
    json_str = valid_telemetry_payload.model_dump_json()

    restored_from_dict = TelemetryPayload.model_validate(dumped_dict)
    restored_from_json = TelemetryPayload.model_validate_json(json_str)

    assert restored_from_dict.total_active_power_kw == valid_telemetry_payload.total_active_power_kw
    assert restored_from_json.device_id == valid_telemetry_payload.device_id
    assert restored_from_json.phases["L1"].voltage_v == 230.2


# =====================================================================
# 2. Electrical Invariant Validation (|P_tot - sum(P_i)| <= 0.05 kW)
# =====================================================================

def test_electrical_invariant_exact_match(valid_telemetry_dict):
    """Total active power exactly equals sum of phase active powers."""
    # L1: 5.95 + L2: 5.82 + L3: 6.13 = 17.90 kW
    valid_telemetry_dict["total_active_power_kw"] = 17.90
    payload = TelemetryPayload.model_validate(valid_telemetry_dict)
    assert payload.total_active_power_kw == 17.90


def test_electrical_invariant_positive_boundary(valid_telemetry_dict):
    """Total active power exactly +0.05 kW above sum of phases (within tolerance)."""
    # 17.90 + 0.05 = 17.95 kW
    valid_telemetry_dict["total_active_power_kw"] = 17.95
    payload = TelemetryPayload.model_validate(valid_telemetry_dict)
    assert payload.total_active_power_kw == 17.95


def test_electrical_invariant_negative_boundary(valid_telemetry_dict):
    """Total active power exactly -0.05 kW below sum of phases (within tolerance)."""
    # 17.90 - 0.05 = 17.85 kW
    valid_telemetry_dict["total_active_power_kw"] = 17.85
    payload = TelemetryPayload.model_validate(valid_telemetry_dict)
    assert payload.total_active_power_kw == 17.85


def test_electrical_invariant_exceeded_positive(valid_telemetry_dict):
    """Total active power exceeds sum by 0.051 kW (> 0.05 limit) -> must raise ValidationError."""
    # 17.90 + 0.051 = 17.951 kW
    valid_telemetry_dict["total_active_power_kw"] = 17.951
    with pytest.raises(ValidationError) as exc_info:
        TelemetryPayload.model_validate(valid_telemetry_dict)
    assert "Electrical invariant violated" in str(exc_info.value)


def test_electrical_invariant_exceeded_negative(valid_telemetry_dict):
    """Total active power is 0.051 kW below sum (> 0.05 limit) -> must raise ValidationError."""
    # 17.90 - 0.051 = 17.849 kW
    valid_telemetry_dict["total_active_power_kw"] = 17.849
    with pytest.raises(ValidationError) as exc_info:
        TelemetryPayload.model_validate(valid_telemetry_dict)
    assert "Electrical invariant violated" in str(exc_info.value)


def test_electrical_invariant_gross_mismatch(invalid_telemetry_unbalanced_active_power):
    """Gross mismatch (25.0 kW vs 17.90 kW sum) must be strictly rejected."""
    with pytest.raises(ValidationError) as exc_info:
        TelemetryPayload.model_validate(invalid_telemetry_unbalanced_active_power)
    assert "Electrical invariant violated" in str(exc_info.value)


# =====================================================================
# 3. Power Factor Boundary Validation (cos φ in [-1.0, 1.0])
# =====================================================================

@pytest.mark.parametrize("valid_pf", [1.0, 0.98, 0.85, 0.0, -0.85, -1.0])
def test_system_power_factor_valid_boundaries(valid_telemetry_dict, valid_pf):
    """Test valid power factors within [-1.0, 1.0]."""
    valid_telemetry_dict["system_power_factor"] = valid_pf
    payload = TelemetryPayload.model_validate(valid_telemetry_dict)
    assert payload.system_power_factor == valid_pf


@pytest.mark.parametrize("invalid_pf", [1.001, 1.5, 2.0, -1.001, -1.5, -10.0])
def test_system_power_factor_invalid_boundaries(valid_telemetry_dict, invalid_pf):
    """Power factor outside [-1.0, 1.0] must raise ValidationError."""
    valid_telemetry_dict["system_power_factor"] = invalid_pf
    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate(valid_telemetry_dict)


@pytest.mark.parametrize("invalid_pf", [1.05, -1.05])
def test_individual_phase_power_factor_invalid(valid_telemetry_dict, invalid_pf):
    """Individual phase power factor outside [-1.0, 1.0] must raise ValidationError."""
    valid_telemetry_dict["phases"]["L1"]["power_factor"] = invalid_pf
    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate(valid_telemetry_dict)


# =====================================================================
# 4. Grid Frequency Validation (Frequency > 0 Hz)
# =====================================================================

@pytest.mark.parametrize("valid_freq", [50.0, 50.02, 49.98, 60.0, 0.01])
def test_grid_frequency_positive(valid_telemetry_dict, valid_freq):
    """Grid frequency strictly positive must be accepted."""
    valid_telemetry_dict["grid_frequency_hz"] = valid_freq
    payload = TelemetryPayload.model_validate(valid_telemetry_dict)
    assert payload.grid_frequency_hz == valid_freq


@pytest.mark.parametrize("invalid_freq", [0.0, -0.01, -50.0])
def test_grid_frequency_non_positive_rejected(valid_telemetry_dict, invalid_freq):
    """Zero or negative grid frequency must be rejected."""
    valid_telemetry_dict["grid_frequency_hz"] = invalid_freq
    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate(valid_telemetry_dict)


# =====================================================================
# 5. Phase Completeness & Strict Schema Validation
# =====================================================================

def test_missing_phase_l3_rejected(invalid_telemetry_missing_phase):
    """Payload missing phase L3 must raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        TelemetryPayload.model_validate(invalid_telemetry_missing_phase)
    assert "missing required phase" in str(exc_info.value).lower()


def test_missing_all_phases_rejected(valid_telemetry_dict):
    """Payload with empty phases dict must raise ValidationError."""
    valid_telemetry_dict["phases"] = {}
    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate(valid_telemetry_dict)


def test_extra_fields_forbidden(valid_telemetry_dict):
    """Extra unexpected fields on payload or phase must raise ValidationError."""
    valid_telemetry_dict["unexpected_rogue_field"] = 123
    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate(valid_telemetry_dict)


# =====================================================================
# 6. Timestamp Validation
# =====================================================================

def test_timestamp_valid_formats(valid_telemetry_dict):
    """Test ISO 8601 strings with 'Z' and timezone offsets, and native datetime."""
    valid_telemetry_dict["timestamp"] = "2026-09-14T18:00:00+03:00"
    payload = TelemetryPayload.model_validate(valid_telemetry_dict)
    assert payload.timestamp.year == 2026

    valid_telemetry_dict["timestamp"] = datetime(2026, 9, 14, 15, 30, tzinfo=timezone.utc)
    payload2 = TelemetryPayload.model_validate(valid_telemetry_dict)
    assert payload2.timestamp.year == 2026


def test_timestamp_invalid_range(valid_telemetry_dict):
    """Timestamps outside operating range [2000, 2100] must be rejected."""
    valid_telemetry_dict["timestamp"] = "1990-01-01T00:00:00Z"
    with pytest.raises(ValidationError) as exc_info:
        TelemetryPayload.model_validate(valid_telemetry_dict)
    assert "valid operational range" in str(exc_info.value)


# =====================================================================
# 7. Commercial Edge Cases
# =====================================================================

def test_commercial_night_idle_baseload(valid_telemetry_dict):
    """Night idle baseload with minimal load (0.0 kW on all phases)."""
    for ph in ("L1", "L2", "L3"):
        valid_telemetry_dict["phases"][ph]["current_a"] = 0.0
        valid_telemetry_dict["phases"][ph]["active_power_kw"] = 0.0
        valid_telemetry_dict["phases"][ph]["apparent_power_kva"] = 0.0
    valid_telemetry_dict["total_active_power_kw"] = 0.0
    valid_telemetry_dict["total_apparent_power_kva"] = 0.0

    payload = TelemetryPayload.model_validate(valid_telemetry_dict)
    assert payload.total_active_power_kw == 0.0


def test_high_commercial_load(valid_telemetry_dict):
    """High industrial/commercial peak load (e.g. 45 kW bakery deck ovens)."""
    for ph in ("L1", "L2", "L3"):
        valid_telemetry_dict["phases"][ph]["voltage_v"] = 230.0
        valid_telemetry_dict["phases"][ph]["current_a"] = 65.2
        valid_telemetry_dict["phases"][ph]["active_power_kw"] = 15.0
        valid_telemetry_dict["phases"][ph]["apparent_power_kva"] = 15.0
    valid_telemetry_dict["total_active_power_kw"] = 45.0
    valid_telemetry_dict["total_apparent_power_kva"] = 45.0

    payload = TelemetryPayload.model_validate(valid_telemetry_dict)
    assert payload.total_active_power_kw == 45.0


# =====================================================================
# 8. Alert Models & Configuration Verification
# =====================================================================

def test_alert_threshold_config_properties(sample_bakery_facility_config):
    """Verify calculated properties on AlertThresholdConfig."""
    config = sample_bakery_facility_config
    assert config.facility_id == "bakery-central-athens"
    assert config.peak_threshold_kw == 22.0
    # warning threshold = 22.0 * 0.85 = 18.70 kW
    assert pytest.approx(config.warning_threshold_kw, rel=1e-4) == 18.70
    # normalization threshold = 22.0 * 0.90 = 19.80 kW
    assert pytest.approx(config.normalization_threshold_kw, rel=1e-4) == 19.80


def test_alert_event_serialization(sample_alert_event):
    """Test AlertEvent model serialization and deserialization."""
    dumped = sample_alert_event.model_dump()
    assert dumped["alert_type"] == AlertType.PEAK_BREACH.value
    assert dumped["severity"] == AlertSeverity.CRITICAL.value
    assert dumped["current_power_kw"] == 28.6
    assert dumped["threshold_kw"] == 22.0
    assert dumped["excess_kw"] == 6.6

    restored = AlertEvent.model_validate(dumped)
    assert restored.alert_type == AlertType.PEAK_BREACH
    assert restored.severity == AlertSeverity.CRITICAL
    assert restored.dispatched is True


# =====================================================================
# 9. Bot Telegram Client Tests
# =====================================================================

def test_mock_telegram_client_send_and_inspect(mock_telegram_client):
    """Verify that MockTelegramClient queues messages, updates counters, and clears."""
    import asyncio

    async def _run_test():
        assert mock_telegram_client.message_count() == 0

        success = await mock_telegram_client.send_message(
            chat_id=12345678,
            text="🚨 <b>ΠΡΟΣΟΧΗ</b>: Δοκιμαστικό μήνυμα υπέρβασης!",
            parse_mode="HTML",
        )
        assert success is True
        assert mock_telegram_client.message_count() == 1

        last_msg = mock_telegram_client.get_last_message()
        assert last_msg is not None
        assert last_msg["chat_id"] == 12345678
        assert "ΠΡΟΣΟΧΗ" in last_msg["text"]
        assert last_msg["parse_mode"] == "HTML"

        # Send second message
        await mock_telegram_client.send_message(chat_id="channel_gr", text="Normal status")
        assert mock_telegram_client.message_count() == 2

        messages = mock_telegram_client.get_sent_messages()
        assert len(messages) == 2

        # Test clear
        mock_telegram_client.clear()
        assert mock_telegram_client.message_count() == 0
        assert mock_telegram_client.get_last_message() is None

    asyncio.run(_run_test())


def test_live_telegram_client_initialization():
    """Verify LiveTelegramClient handles token validation and URL formatting."""
    with pytest.raises(ValueError):
        LiveTelegramClient(token="")

    client = LiveTelegramClient(token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
    assert client.api_url == "https://api.telegram.org/bot123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
