"""
Yellow & Dynamic Electricity Tariff Engine.

Implements wholesale-indexed retail supply rates linked directly to
the Hellenic Energy Exchange (HEnEx) Day-Ahead Market (DAM) hourly clearing prices (TEA(h)).

Formula:
P_supply(h) = (TEA(h) / 1000) * (1 + loss_factor) + margin_eur_kwh + p_base
"""

from __future__ import annotations

from dataclasses import dataclass


def _normalize_to_kwh(val: float) -> float:
    """Normalizes price from €/MWh to €/kWh if val > 1.0."""
    if abs(val) > 1.0:
        return val / 1000.0
    return val


def calculate_yellow_dynamic_supply_rate(
    tea_eur_mwh: float,
    loss_factor: float = 0.135,
    margin_eur_kwh: float = 0.015,
    p_base: float = 0.050,
    floor_at_zero: bool = False,
) -> float:
    """
    Computes Yellow or Dynamic spot-indexed electricity supply rate.

    Args:
        tea_eur_mwh: Day-Ahead Market hourly clearing price TEA(h) in €/MWh (or €/kWh).
        loss_factor: Grid transmission/distribution loss factor L_loss (default: 0.135).
        margin_eur_kwh: Supplier retail margin M_supplier in €/kWh (default: 0.015 €/kWh).
        p_base: Base fixed retail tariff component in €/kWh (default: 0.050 €/kWh).
        floor_at_zero: If True, floors negative wholesale pricing at 0.0 €/kWh.

    Returns:
        Supply rate in €/kWh rounded to 5 decimal places.
    """
    tea_kwh = _normalize_to_kwh(tea_eur_mwh)
    rate = tea_kwh * (1.0 + loss_factor) + margin_eur_kwh + p_base
    if floor_at_zero:
        rate = max(0.0, rate)
    return round(rate, 5)


def calculate_yellow_tariff(
    tea_eur_mwh: float,
    loss_factor: float = 0.135,
    margin_eur_kwh: float = 0.015,
    p_base: float = 0.040,
    floor_at_zero: bool = False,
) -> float:
    """
    Standard Yellow commercial tariff with standard base component (0.040 €/kWh).
    """
    return calculate_yellow_dynamic_supply_rate(
        tea_eur_mwh=tea_eur_mwh,
        loss_factor=loss_factor,
        margin_eur_kwh=margin_eur_kwh,
        p_base=p_base,
        floor_at_zero=floor_at_zero,
    )


def calculate_dynamic_tariff(
    tea_eur_mwh: float,
    loss_factor: float = 0.135,
    margin_eur_kwh: float = 0.015,
    p_base: float = 0.020,
    floor_at_zero: bool = False,
) -> float:
    """
    Dynamic hourly spot tariff for interval-metered facilities (0.020 €/kWh base).
    """
    return calculate_yellow_dynamic_supply_rate(
        tea_eur_mwh=tea_eur_mwh,
        loss_factor=loss_factor,
        margin_eur_kwh=margin_eur_kwh,
        p_base=p_base,
        floor_at_zero=floor_at_zero,
    )


@dataclass
class YellowDynamicEngine:
    """
    Configurable engine for calculating Yellow and Dynamic spot-indexed tariffs.
    """
    loss_factor: float = 0.135
    margin_eur_kwh: float = 0.015
    yellow_base_eur_kwh: float = 0.040
    dynamic_base_eur_kwh: float = 0.020
    floor_at_zero: bool = False

    def compute_yellow(self, tea_eur_mwh: float) -> float:
        return calculate_yellow_tariff(
            tea_eur_mwh=tea_eur_mwh,
            loss_factor=self.loss_factor,
            margin_eur_kwh=self.margin_eur_kwh,
            p_base=self.yellow_base_eur_kwh,
            floor_at_zero=self.floor_at_zero,
        )

    def compute_dynamic(self, tea_eur_mwh: float) -> float:
        return calculate_dynamic_tariff(
            tea_eur_mwh=tea_eur_mwh,
            loss_factor=self.loss_factor,
            margin_eur_kwh=self.margin_eur_kwh,
            p_base=self.dynamic_base_eur_kwh,
            floor_at_zero=self.floor_at_zero,
        )
