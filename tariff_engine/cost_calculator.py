"""
Greek Commercial Real-Time Cost & Penalty Projection Engine.

Computes:
1. Instantaneous running cost (€/h = active power kW * effective rate €/kWh + hourly capacity rate).
2. Incremental telemetry packet cost (€ = delta_kWh * effective rate).
3. Daily accumulated spend tracking across calendar dates.
4. Projected excess cost penalties during peak tariff hours:
   (excess_power_kw * rate_diff * remaining_peak_hours).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from .contracts import (
    TariffColor,
    TariffContract,
    is_greek_offpeak_window,
    is_greek_peak_window,
)
from .green_tariff import calculate_green_tariff_supply_rate
from .regulated_charges import (
    VAT_RATE,
    calculate_hourly_capacity_rate,
    calculate_regulated_unit_rate,
)
from .yellow_dynamic import calculate_yellow_dynamic_supply_rate


@dataclass(frozen=True)
class CostCalculationResult:
    """
    Contractual output of real-time electricity cost calculation.
    """
    current_rate_eur_per_kwh: float
    running_cost_eur_per_h: float
    incremental_cost_eur: float
    is_peak_window: bool
    is_excess_breach: bool
    excess_power_kw: float
    projected_excess_penalty_eur: float
    regulated_rate_eur_per_kwh: float = 0.0
    vat_rate: float = VAT_RATE
    supply_rate_eur_per_kwh: float = 0.0
    hourly_capacity_rate_eur_h: float = 0.0


def calculate_projected_peak_penalty(
    excess_power_kw: float,
    rate_difference_eur_kwh: float,
    remaining_peak_hours: float,
    vat_rate: float = VAT_RATE,
) -> float:
    """
    Computes projected financial penalty for exceeding optimal load threshold
    during remaining active peak hours:
    Penalty = excess_power_kw * (peak_rate - base_rate) * remaining_peak_hours * (1 + VAT)
    """
    if excess_power_kw <= 0.0 or remaining_peak_hours <= 0.0 or rate_difference_eur_kwh <= 0.0:
        return 0.0
    surcharge = excess_power_kw * remaining_peak_hours * rate_difference_eur_kwh * (1.0 + vat_rate)
    return round(surcharge, 2)


def calculate_realtime_cost(
    power_kw: float,
    energy_kwh_delta: float,
    timestamp: datetime,
    tariff_profile: Any,
    tea_eur_mwh: float = 120.0,
    power_factor: float = 0.98,
    contracted_kva: float | None = None,
    include_hourly_capacity_rate: bool = False,
) -> CostCalculationResult:
    """
    Pure deterministic cost calculation oracle.
    Computes instantaneous running cost (€/h), incremental spend, zone status,
    and projected excess demand penalties.

    Compatible with both tariff_engine.ContractProfile and harness.FacilityProfileConfig.
    """
    # Normalize contract code
    raw_code = getattr(tariff_profile, "contract_code", None) or getattr(tariff_profile, "contract_type", "G21")
    if isinstance(raw_code, TariffContract):
        contract_code = raw_code.value
    else:
        contract_code = str(raw_code).strip().upper().replace("Γ", "G")

    # Normalize tariff color
    raw_color = getattr(tariff_profile, "tariff_color", None) or getattr(tariff_profile, "color", "green")
    if isinstance(raw_color, TariffColor):
        tariff_color = raw_color.value
    else:
        tariff_color = str(raw_color).strip().lower()

    # Agreed capacity and threshold
    eff_contracted_kva = contracted_kva if contracted_kva is not None else getattr(tariff_profile, "contracted_kva", 35.0)
    eff_peak_threshold_kw = getattr(tariff_profile, "peak_threshold_kw", None)
    if eff_peak_threshold_kw is None:
        eff_peak_threshold_kw = round(eff_contracted_kva * 0.85, 2)

    is_peak = is_greek_peak_window(timestamp)
    is_offpeak = is_greek_offpeak_window(timestamp)

    # Determine base supply rate
    if tariff_color == "green":
        p_base = 0.155 if contract_code == "G21" else 0.165
        supply_rate = calculate_green_tariff_supply_rate(
            p_base=p_base,
            tea_eur_mwh=tea_eur_mwh,
        )
    elif tariff_color == "yellow":
        supply_rate = calculate_yellow_dynamic_supply_rate(tea_eur_mwh=tea_eur_mwh, p_base=0.040)
    else:  # dynamic
        supply_rate = calculate_yellow_dynamic_supply_rate(tea_eur_mwh=tea_eur_mwh, p_base=0.020)

    # If G22 / G23 dual-rate contract, apply peak / off-peak rate modifiers
    if contract_code in ("G22", "G23"):
        if is_peak:
            supply_rate *= 1.25  # +25% peak surcharge
        elif is_offpeak:
            supply_rate *= 0.70  # -30% night discount

    # Calculate regulated unit rate
    is_lv = (contract_code != "G23")
    regulated_rate = calculate_regulated_unit_rate(
        contracted_kva=eff_contracted_kva,
        power_factor=power_factor,
        is_lv=is_lv,
    )

    total_unit_rate = (supply_rate + regulated_rate) * (1.0 + VAT_RATE)

    # Hourly capacity standing charge
    hourly_cap_rate = calculate_hourly_capacity_rate(eff_contracted_kva) if include_hourly_capacity_rate else 0.0

    running_cost_eur_per_h = round((power_kw * total_unit_rate) + hourly_cap_rate, 2)
    incremental_cost_eur = round(energy_kwh_delta * total_unit_rate, 4)

    is_excess = (is_peak and power_kw > eff_peak_threshold_kw)
    excess_power_kw = max(0.0, power_kw - eff_peak_threshold_kw) if is_peak else 0.0

    # Project excess penalty for remaining peak window
    projected_penalty = 0.0
    if is_excess:
        end_hour = 17 if (5 <= timestamp.month <= 10) else 21
        remaining_hours = max(0.1, end_hour - (timestamp.hour + timestamp.minute / 60.0))
        # Rate differential vs offpeak
        rate_diff = (supply_rate * 0.40) * (1.0 + VAT_RATE)
        projected_penalty = round(excess_power_kw * remaining_hours * rate_diff, 2)

    return CostCalculationResult(
        current_rate_eur_per_kwh=round(total_unit_rate, 4),
        running_cost_eur_per_h=running_cost_eur_per_h,
        incremental_cost_eur=incremental_cost_eur,
        is_peak_window=is_peak,
        is_excess_breach=is_excess,
        excess_power_kw=round(excess_power_kw, 2),
        projected_excess_penalty_eur=projected_penalty,
        regulated_rate_eur_per_kwh=round(regulated_rate, 5),
        vat_rate=VAT_RATE,
        supply_rate_eur_per_kwh=round(supply_rate, 5),
        hourly_capacity_rate_eur_h=hourly_cap_rate,
    )


class DailySpendTracker:
    """
    Thread-safe tracker for accumulating daily electricity costs and consumption.
    Handles multi-day rollovers and per-facility spend aggregation.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._spend_by_date: dict[date, float] = {}
        self._kwh_by_date: dict[date, float] = {}

    def record_reading(self, timestamp: datetime, delta_kwh: float, cost_eur: float) -> None:
        """Records an incremental energy delta and corresponding cost."""
        with self._lock:
            d = timestamp.date()
            self._spend_by_date[d] = round(self._spend_by_date.get(d, 0.0) + cost_eur, 4)
            self._kwh_by_date[d] = round(self._kwh_by_date.get(d, 0.0) + delta_kwh, 4)

    def get_daily_spend(self, target_date: date | None = None) -> float:
        """Retrieves total accumulated spend in € for a specific date (defaults to today)."""
        d = target_date or datetime.now(timezone.utc).date()
        with self._lock:
            return round(self._spend_by_date.get(d, 0.0), 2)

    def get_daily_kwh(self, target_date: date | None = None) -> float:
        """Retrieves total accumulated energy in kWh for a specific date (defaults to today)."""
        d = target_date or datetime.now(timezone.utc).date()
        with self._lock:
            return round(self._kwh_by_date.get(d, 0.0), 3)

    def reset(self, target_date: date | None = None) -> None:
        """Resets counters for a target date, or clears all history if target_date is None."""
        with self._lock:
            if target_date is None:
                self._spend_by_date.clear()
                self._kwh_by_date.clear()
            else:
                self._spend_by_date.pop(target_date, None)
                self._kwh_by_date.pop(target_date, None)

    def get_summary(self) -> dict[str, Any]:
        """Provides a statistical summary of tracked days."""
        with self._lock:
            total_spend = sum(self._spend_by_date.values())
            total_kwh = sum(self._kwh_by_date.values())
            return {
                "total_spend_eur": round(total_spend, 2),
                "total_kwh": round(total_kwh, 3),
                "days_tracked": len(self._spend_by_date),
            }
