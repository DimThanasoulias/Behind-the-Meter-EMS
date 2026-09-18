"""
Spanish Market Adapter implementing OMIE DAM, PVPC, and Tarifa 2.0TD 3-period ToU (Requirement R4 / F7).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from tariff_engine.adapters.base import (
    BaseMarketAdapter,
    DemandCapacityLimit,
    HourlyPriceVector,
    MarketMetadata,
)
from tariff_engine.cost_calculator import CostCalculationResult

SPANISH_VAT_RATE = 0.21
IMPUESTO_ELECTRICO_RATE = 0.051127   # 5.1127%
PEAJE_PUNTA_P1_EUR_KWH = 0.1350
PEAJE_LLANO_P2_EUR_KWH = 0.0780
PEAJE_VALLE_P3_EUR_KWH = 0.0210
POTENCIA_PUNTA_EUR_KW_YR = 30.67
POTENCIA_VALLE_EUR_KW_YR = 1.42
MARKETING_MARGIN_EUR_KWH = 0.0035


@dataclass
class SpanishFacilityContract:
    potencia_punta_kw: float = 15.0
    potencia_valle_kw: float = 15.0
    meter_rent_eur_day: float = 0.027
    social_bonus_eur_day: float = 0.029
    vat_rate: float = SPANISH_VAT_RATE


class SpanishMarketAdapter(BaseMarketAdapter):
    """
    Market adapter for Spanish bidding zone (ES).
    Implements OMIE Day-Ahead Market pricing, PVPC commercial formula,
    and Tarifa 2.0TD 3-period ToU (Punta, Llano, Valle) network tolls.
    """

    def __init__(self) -> None:
        self._metadata = MarketMetadata(
            bidding_zone="ES",
            country_code="ES",
            country_name="Spain",
            currency="EUR",
            regulatory_body="CNMC",
            default_vat_rate=SPANISH_VAT_RATE,
            wholesale_market="OMIE",
            supports_dynamic_dam=True,
            supports_periodic_billing=True,
            notes="Governed by CNMC Circular 3/2020 and Royal Decree 216/2014.",
        )

    def get_market_metadata(self) -> MarketMetadata:
        return self._metadata

    @staticmethod
    def get_20td_period(dt: datetime) -> str:
        """
        Classifies timestamp into Tarifa 2.0TD ToU energy periods:
        - 'P3' (Valle): All weekend hours + Mon-Fri 00:00-08:00
        - 'P1' (Punta): Mon-Fri 10:00-14:00 and 18:00-22:00
        - 'P2' (Llano): Mon-Fri 08:00-10:00, 14:00-18:00, 22:00-24:00
        """
        # Weekends are entirely Valle (P3)
        if dt.weekday() >= 5:
            return "P3"

        hour = dt.hour
        if 0 <= hour < 8:
            return "P3"
        elif (10 <= hour < 14) or (18 <= hour < 22):
            return "P1"
        else:
            return "P2"

    def get_hourly_price_vector(
        self,
        start_dt: datetime,
        horizon_hours: int = 24,
        facility_contract: Any = None,
        spot_prices: list[float] | None = None,
    ) -> list[HourlyPriceVector]:
        contract = facility_contract if isinstance(facility_contract, SpanishFacilityContract) else SpanishFacilityContract()

        standing_hourly = round(
            ((POTENCIA_PUNTA_EUR_KW_YR * contract.potencia_punta_kw) + (POTENCIA_VALLE_EUR_KW_YR * contract.potencia_valle_kw))
            / (365.0 * 24.0), 4
        )

        vectors: list[HourlyPriceVector] = []
        for h in range(horizon_hours):
            interval_dt = start_dt + timedelta(hours=h)
            period = self.get_20td_period(interval_dt)

            omie_mwh = spot_prices[h] if (spot_prices and h < len(spot_prices)) else 85.0
            energy_rate = round((omie_mwh / 1000.0) + MARKETING_MARGIN_EUR_KWH, 5)

            if period == "P1":
                toll_rate = PEAJE_PUNTA_P1_EUR_KWH
                is_peak = True
            elif period == "P2":
                toll_rate = PEAJE_LLANO_P2_EUR_KWH
                is_peak = False
            else:  # P3
                toll_rate = PEAJE_VALLE_P3_EUR_KWH
                is_peak = False

            base_cost = energy_rate + toll_rate
            tax_rate = round(base_cost * IMPUESTO_ELECTRICO_RATE, 5)
            pretax_total = round(base_cost + tax_rate, 5)
            total_inc_vat = round(pretax_total * (1.0 + contract.vat_rate), 5)

            vectors.append(
                HourlyPriceVector(
                    timestamp=interval_dt,
                    interval_index=h,
                    energy_rate_eur_kwh=energy_rate,
                    grid_distribution_rate=toll_rate,
                    grid_transmission_rate=0.0,
                    taxes_and_levies_rate=tax_rate,
                    vat_rate=contract.vat_rate,
                    total_rate_ex_vat=pretax_total,
                    total_rate_inc_vat=total_inc_vat,
                    is_peak_window=is_peak,
                    is_critical_peak=is_peak,
                    standing_capacity_rate_eur_h=standing_hourly,
                )
            )

        return vectors

    def calculate_instantaneous_cost(
        self,
        power_kw: float,
        energy_kwh_delta: float,
        timestamp: datetime,
        facility_contract: Any,
        **kwargs: Any,
    ) -> CostCalculationResult:
        contract = facility_contract if isinstance(facility_contract, SpanishFacilityContract) else SpanishFacilityContract()
        omie_mwh = kwargs.get("tea_eur_mwh", kwargs.get("omie_eur_mwh", 85.0))

        period = self.get_20td_period(timestamp)
        toll_rate = PEAJE_PUNTA_P1_EUR_KWH if period == "P1" else (PEAJE_LLANO_P2_EUR_KWH if period == "P2" else PEAJE_VALLE_P3_EUR_KWH)
        energy_rate = (omie_mwh / 1000.0) + MARKETING_MARGIN_EUR_KWH
        base_rate = energy_rate + toll_rate
        total_unit_rate = (base_rate * (1.0 + IMPUESTO_ELECTRICO_RATE)) * (1.0 + contract.vat_rate)

        hourly_cap = ((POTENCIA_PUNTA_EUR_KW_YR * contract.potencia_punta_kw) + (POTENCIA_VALLE_EUR_KW_YR * contract.potencia_valle_kw)) / (365.0 * 24.0)

        running_cost = round((power_kw * total_unit_rate) + hourly_cap, 2)
        incremental_cost = round(energy_kwh_delta * total_unit_rate, 4)

        peak_thresh = contract.potencia_punta_kw
        is_excess = (power_kw > peak_thresh)
        excess_kw = max(0.0, power_kw - peak_thresh) if is_excess else 0.0

        return CostCalculationResult(
            current_rate_eur_per_kwh=round(total_unit_rate, 4),
            running_cost_eur_per_h=running_cost,
            incremental_cost_eur=incremental_cost,
            is_peak_window=(period == "P1"),
            is_excess_breach=is_excess,
            excess_power_kw=round(excess_kw, 2),
            projected_excess_penalty_eur=0.0,
            regulated_rate_eur_per_kwh=round(toll_rate, 5),
            vat_rate=contract.vat_rate,
            supply_rate_eur_per_kwh=round(energy_rate, 5),
            hourly_capacity_rate_eur_h=round(hourly_cap, 4),
        )

    def calculate_periodic_bill(self, bill_input: Any) -> Any:
        """Calculates 3-period ToU Spanish electricity bill."""
        days = getattr(bill_input, "billing_period_days", 30)
        p_punta_kw = getattr(bill_input, "potencia_punta_kw", 15.0)
        p_valle_kw = getattr(bill_input, "potencia_valle_kw", 15.0)
        e_p1 = getattr(bill_input, "energy_p1_kwh", getattr(bill_input, "energy_peak_kwh", 0.0))
        e_p2 = getattr(bill_input, "energy_p2_kwh", getattr(bill_input, "energy_normal_kwh", 0.0))
        e_p3 = getattr(bill_input, "energy_p3_kwh", getattr(bill_input, "energy_offpeak_kwh", 0.0))
        omie_avg = getattr(bill_input, "wholesale_tea_dam_eur_mwh", 85.0)

        contract = SpanishFacilityContract(potencia_punta_kw=p_punta_kw, potencia_valle_kw=p_valle_kw)

        # Potencia term
        potencia_punta_eur = round((POTENCIA_PUNTA_EUR_KW_YR * p_punta_kw * days) / 365.0, 2)
        potencia_valle_eur = round((POTENCIA_VALLE_EUR_KW_YR * p_valle_kw * days) / 365.0, 2)
        potencia_subtotal = round(potencia_punta_eur + potencia_valle_eur, 2)

        # Energía term
        supply_unit = (omie_avg / 1000.0) + MARKETING_MARGIN_EUR_KWH
        energia_p1_eur = round(e_p1 * (supply_unit + PEAJE_PUNTA_P1_EUR_KWH), 2)
        energia_p2_eur = round(e_p2 * (supply_unit + PEAJE_LLANO_P2_EUR_KWH), 2)
        energia_p3_eur = round(e_p3 * (supply_unit + PEAJE_VALLE_P3_EUR_KWH), 2)
        energia_subtotal = round(energia_p1_eur + energia_p2_eur + energia_p3_eur, 2)

        # Impuesto Eléctrico (IEE)
        iee_taxable = potencia_subtotal + energia_subtotal
        iee_eur = round(iee_taxable * IMPUESTO_ELECTRICO_RATE, 2)

        # Meter rent & social bonus
        meter_rent_eur = round(contract.meter_rent_eur_day * days, 2)
        social_bonus_eur = round(contract.social_bonus_eur_day * days, 2)

        pretax_total = round(iee_taxable + iee_eur + meter_rent_eur + social_bonus_eur, 2)
        vat_eur = round(pretax_total * contract.vat_rate, 2)
        total_payable = round(pretax_total + vat_eur, 2)

        return {
            "bill_id": getattr(bill_input, "bill_id", "ES-BILL-01"),
            "bidding_zone": "ES",
            "potencia_subtotal_eur": potencia_subtotal,
            "energia_subtotal_eur": energia_subtotal,
            "impuesto_electrico_eur": iee_eur,
            "meter_rent_eur": meter_rent_eur,
            "social_bonus_eur": social_bonus_eur,
            "pretax_total_eur": pretax_total,
            "vat_amount_eur": vat_eur,
            "total_payable_eur": total_payable,
        }

    def get_demand_capacity_limits(
        self,
        timestamp: datetime,
        facility_contract: Any,
    ) -> DemandCapacityLimit:
        p_punta = getattr(facility_contract, "potencia_punta_kw", 15.0)
        return DemandCapacityLimit(
            contracted_capacity_kw=float(p_punta),
            peak_demand_threshold_kw=float(p_punta),
            capacity_penalty_rate_eur_kw=round(POTENCIA_PUNTA_EUR_KW_YR / 365.0, 4),
            allows_power_factor_penalty=False,
        )
