"""
Greek Electricity Tariff Penalties & Surcharge Mathematics.

Implements:
1. Power Factor (cos φ) Penalty Surcharges per DEDDIE Grid Distribution Code:
   - When cos φ < 0.85, distribution energy multiplier M_PF = 0.85 / cos φ.
2. Contracted Capacity Excess Penalties (Υπέρβαση Συμφωνηθείσας Ισχύος):
   - Proportional surcharge when apparent power S > contracted kVA.
   - Breaker thermal trip risk indicators.
"""

from __future__ import annotations

from dataclasses import dataclass

from .regulated_charges import (
    DEDDIE_CAPACITY_RATE_EUR_KVA_YR,
)

POWER_FACTOR_THRESHOLD = 0.85
DEFAULT_CAPACITY_PENALTY_MULTIPLIER = 2.5  # DEDDIE capacity excess surcharge multiplier (2.0 - 3.0)


@dataclass(frozen=True)
class CapacityExcessResult:
    """Result of contracted capacity evaluation."""
    apparent_power_kva: float
    contracted_kva: float
    excess_kva: float
    is_breached: bool
    overload_percentage: float
    hourly_penalty_eur: float
    breaker_trip_risk: bool


def calculate_power_factor_multiplier(power_factor: float) -> float:
    """
    Computes DEDDIE distribution charge multiplier M_PF for reactive power:
    - If cos φ >= 0.85: M_PF = 1.0 (no penalty)
    - If cos φ < 0.85: M_PF = 0.85 / |cos φ|

    Clamps effective power factor to [0.01, 1.0] to prevent division by zero.
    Handles capacitive/leading reactive power (evaluates absolute displacement).
    """
    eff_pf = max(0.01, min(abs(power_factor), 1.0))
    if eff_pf < POWER_FACTOR_THRESHOLD:
        return round(POWER_FACTOR_THRESHOLD / eff_pf, 4)
    return 1.0


def is_power_factor_penalized(power_factor: float) -> bool:
    """Returns True if power factor falls below the 0.85 regulatory threshold."""
    eff_pf = max(0.01, min(abs(power_factor), 1.0))
    return eff_pf < POWER_FACTOR_THRESHOLD


def calculate_power_factor_surcharge(
    base_deddie_charge_eur: float,
    power_factor: float,
) -> float:
    """
    Computes additional euro surcharge incurred on DEDDIE distribution energy charge
    due to uncompensated reactive power draw (cos φ < 0.85).
    """
    mult = calculate_power_factor_multiplier(power_factor)
    return round(base_deddie_charge_eur * (mult - 1.0), 4)


def calculate_capacity_excess(
    apparent_power_kva: float,
    contracted_kva: float,
    k_penalty: float = DEFAULT_CAPACITY_PENALTY_MULTIPLIER,
) -> CapacityExcessResult:
    """
    Evaluates apparent power demand against agreed connection capacity (kVA).

    Args:
        apparent_power_kva: Measured instantaneous or 15-minute apparent power in kVA.
        contracted_kva: Contracted capacity S_agreed in kVA.
        k_penalty: DEDDIE capacity penalty multiplier (default: 2.5).

    Returns:
        CapacityExcessResult with excess kVA, overload percentage, hourly penalty,
        and breaker trip risk indication.
    """
    if contracted_kva <= 0.0:
        raise ValueError(f"Contracted capacity must be > 0, got {contracted_kva}")

    apparent = max(0.0, apparent_power_kva)
    excess = max(0.0, apparent - contracted_kva)
    is_breached = excess > 0.0
    overload_pct = round((excess / contracted_kva) * 100.0, 2)

    # Hourly capacity surcharge = k_penalty * (MPX_dist / (365 * 24)) * S_excess
    hourly_rate_per_kva = DEDDIE_CAPACITY_RATE_EUR_KVA_YR / (365.0 * 24.0)
    hourly_penalty = round(k_penalty * hourly_rate_per_kva * excess, 4)

    # Breaker trip risk: instantaneous overload > 15% above contracted kVA
    breaker_trip_risk = apparent > (contracted_kva * 1.15)

    return CapacityExcessResult(
        apparent_power_kva=round(apparent, 3),
        contracted_kva=round(contracted_kva, 3),
        excess_kva=round(excess, 3),
        is_breached=is_breached,
        overload_percentage=overload_pct,
        hourly_penalty_eur=hourly_penalty,
        breaker_trip_risk=breaker_trip_risk,
    )


def is_capacity_exceeded(apparent_power_kva: float, contracted_kva: float) -> bool:
    """Simple boolean check whether demand breaches agreed connection capacity."""
    return apparent_power_kva > contracted_kva
