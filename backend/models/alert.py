"""Alert schemas and configuration models for proactive Telegram notifications."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AlertSeverity(str, Enum):
    """Severity levels for proactive EMS notifications."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertType(str, Enum):
    """Categorization of energy management alert events."""

    PEAK_BREACH = "PEAK_BREACH"
    PRE_WARNING = "PRE_WARNING"
    NORMALIZED = "NORMALIZED"
    LOW_POWER_FACTOR = "LOW_POWER_FACTOR"
    CAPACITY_EXCESS = "CAPACITY_EXCESS"


class AlertThresholdConfig(BaseModel):
    """Facility-specific alerting thresholds and throttling parameters."""

    model_config = ConfigDict(extra="forbid")

    facility_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Facility identifier to which these thresholds apply",
    )
    peak_threshold_kw: float = Field(
        ...,
        gt=0.0,
        description="Active power threshold [kW] during peak tariff windows (breach triggers alert)",
    )
    warning_threshold_ratio: float = Field(
        default=0.85,
        ge=0.5,
        le=1.0,
        description="Ratio of peak threshold to trigger PRE_WARNING (e.g. 0.85 = 85%)",
    )
    low_pf_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Power factor cos φ threshold below which LOW_POWER_FACTOR alert is raised (0.85 per DEDDIE)",
    )
    contracted_capacity_kva: float = Field(
        default=35.0,
        gt=0.0,
        description="Contracted service capacity in kVA (e.g. 25, 35, 50, 70 kVA)",
    )
    cooldown_seconds: int = Field(
        default=1800,
        ge=0,
        description="Throttling quiet period in seconds (default 1800s = 30 minutes)",
    )
    hysteresis_factor: float = Field(
        default=0.90,
        gt=0.0,
        le=1.0,
        description="Normalization release ratio (default 0.90 = load must drop to 90% of threshold)",
    )
    debounce_samples: int = Field(
        default=3,
        ge=1,
        description="Number of consecutive breaching telemetry samples before triggering alert",
    )
    chat_id: int | None = Field(
        default=None,
        description="Configured Telegram chat ID for facility notifications",
    )

    @property
    def warning_threshold_kw(self) -> float:
        """Calculate effective warning threshold in kW."""
        return self.peak_threshold_kw * self.warning_threshold_ratio

    @property
    def normalization_threshold_kw(self) -> float:
        """Calculate load level below which alert clears in kW."""
        return self.peak_threshold_kw * self.hysteresis_factor


class AlertEvent(BaseModel):
    """Record of an alert event triggered by the system."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(
        default=None,
        description="Unique alert identifier",
    )
    facility_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Associated commercial facility identifier",
    )
    alert_type: AlertType = Field(
        ...,
        description="Category of alert event",
    )
    severity: AlertSeverity = Field(
        ...,
        description="Severity classification of the alert",
    )
    timestamp: datetime = Field(
        ...,
        description="Timestamp when alert condition was detected (UTC)",
    )
    message: str = Field(
        ...,
        min_length=1,
        description="Formatted message text delivered to recipient (Greek HTML)",
    )
    current_power_kw: float = Field(
        ...,
        description="Instantaneous total active power [kW] at breach time",
    )
    threshold_kw: float = Field(
        ...,
        description="Target active power threshold [kW] configured for facility",
    )
    excess_kw: float = Field(
        default=0.0,
        description="Power delta exceeding threshold [kW]",
    )
    active_zone: str | None = Field(
        default=None,
        description="Active Greek tariff zone (PEAK, NORMAL, OFF_PEAK)",
    )
    estimated_penalty_eur: float = Field(
        default=0.0,
        ge=0.0,
        description="Estimated excess energy cost / penalty in EUR",
    )
    power_factor: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
        description="Observed system power factor at alert time",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context, tips, and operational metadata",
    )
    dispatched: bool = Field(
        default=False,
        description="Flag indicating whether message was successfully dispatched via Telegram",
    )
    dispatched_at: datetime | None = Field(
        default=None,
        description="Timestamp of successful delivery via Telegram",
    )

    @field_validator("timestamp")
    @classmethod
    def validate_event_timestamp(cls, v: datetime) -> datetime:
        """Ensure alert event timestamp is valid."""
        if v.year < 2000 or v.year > 2100:
            raise ValueError(f"Invalid alert timestamp year: {v.year}")
        return v
