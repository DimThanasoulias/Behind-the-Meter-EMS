"""
German Market Adapter implementing EPEX Spot DAM, Netzentgelte, Stromsteuer, and §14a EnWG (Requirement R4 / F7).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from tariff_engine.adapters.base import (
    BaseMarketAdapter,
    DemandCapacityLimit,
    HourlyPriceVector,
    MarketMetadata,
)
from tariff_engine.cost_calculator import CostCalculationResult

GERMAN_VAT_RATE = 0.19
STROMSTEUER_STANDARD_EUR_KWH = 0.0205
STROMSTEUER_REDUCED_EUR_KWH = 0.0005
KONZESSIONSABGABE_EUR_KWH = 0.0150
KWKG_UMLAGE_EUR_KWH = 0.00350
OFFSHORE_UMLAGE_EUR_KWH = 0.00590
STROMNEV_UMLAGE_EUR_KWH = 0.00400
DEFAULT_NETZENTGELT_AP_EUR_KWH = 0.0920
DEFAULT_NETZENTGELT_GP_EUR_KW_YR = 80.00
RETAIL_MARGIN_EUR_KWH = 0.0180


@dataclass
class GermanFacilityContract:
    contracted_kw: float = 50.0
    retail_margin_eur_kwh: float = RETAIL_MARGIN_EUR_KWH
    base_monthly_fee_eur: float = 5.00
    is_manufacturing_tax_relief: bool = False
    enwg_14a_module: int = 0          # 0: None, 1: Modul 1, 2: Modul 2, 3: Modul 3
    enwg_14a_modul1_annual_credit_eur: float = 150.00
    netzentgelt_ap_eur_kwh: float = DEFAULT_NETZENTGELT_AP_EUR_KWH
    netzentgelt_gp_eur_kw_yr: float = DEFAULT_NETZENTGELT_GP_EUR_KW_YR


class GermanMarketAdapter(BaseMarketAdapter):
    """
    Market adapter for German bidding zone (DE-LU).
    Models EPEX Spot DAM pricing, Netzentgelte, Stromsteuer, statutory surcharges,
    19% MwSt, and §14a EnWG controllable load rebate modules.
    """

    def __init__(self) -> None:
        self._metadata = MarketMetadata(
            bidding_zone="DE-LU",
            country_code="DE",
            country_name="Germany",
            currency="EUR",
            regulatory_body="BNetzA",
            default_vat_rate=GERMAN_VAT_RATE,
            wholesale_market="EPEX Spot",
            supports_dynamic_dam=True,
            supports_periodic_billing=True,
            notes="Governed by BNetzA regulations, EnWG §14a, and StromStG.",
        )

    def get_market_metadata(self) -> MarketMetadata:
        return self._metadata

    def _get_grid_fee_rate(self, dt: datetime, contract: GermanFacilityContract) -> tuple[float, bool]:
        """Evaluates volumetric Netzentgelt applying §14a EnWG modules."""
        base_ap = contract.netzentgelt_ap_eur_kwh
        is_peak = False

        if contract.enwg_14a_module == 2:
            # Modul 2: 60% volumetric reduction
            return round(base_ap * 0.40, 5), False
        elif contract.enwg_14a_module == 3:
            # Modul 3: Time-variable dynamic grid fee
            hour = dt.hour
            weekday = dt.weekday()
            if weekday < 5 and (17 <= hour < 21):
                # High tariff (HT)
                is_peak = True
                return round(base_ap * 1.60, 5), is_peak
            elif (0 <= hour < 6) or (12 <= hour < 15):
                # Low tariff (ST)
                return round(base_ap * 0.50, 5), False
            else:
                return round(base_ap, 5), False
        else:
            # Modul 0 or 1: standard grid fee
            hour = dt.hour
            if dt.weekday() < 5 and (17 <= hour < 21):
                is_peak = True
            return round(base_ap, 5), is_peak

    def get_hourly_price_vector(
        self,
        start_dt: datetime,
        horizon_hours: int = 24,
        facility_contract: Any = None,
        spot_prices: list[float] | None = None,
    ) -> list[HourlyPriceVector]:
        contract = facility_contract if isinstance(facility_contract, GermanFacilityContract) else GermanFacilityContract()

        stromsteuer = STROMSTEUER_REDUCED_EUR_KWH if contract.is_manufacturing_tax_relief else STROMSTEUER_STANDARD_EUR_KWH
        taxes_rate = round(stromsteuer + KONZESSIONSABGABE_EUR_KWH + KWKG_UMLAGE_EUR_KWH + OFFSHORE_UMLAGE_EUR_KWH + STROMNEV_UMLAGE_EUR_KWH, 5)

        standing_hourly = round((contract.netzentgelt_gp_eur_kw_yr * contract.contracted_kw) / (365.0 * 24.0), 4)

        vectors: list[HourlyPriceVector] = []
        for h in range(horizon_hours):
            interval_dt = start_dt + timedelta(hours=h)
            epex_mwh = spot_prices[h] if (spot_prices and h < len(spot_prices)) else 95.0

            energy_rate = round((epex_mwh / 1000.0) + contract.retail_margin_eur_kwh, 5)
            grid_rate, is_peak = self._get_grid_fee_rate(interval_dt, contract)

            pretax_total = round(energy_rate + grid_rate + taxes_rate, 5)
            total_inc_vat = round(pretax_total * (1.0 + GERMAN_VAT_RATE), 5)

            vectors.append(
                HourlyPriceVector(
                    timestamp=interval_dt,
                    interval_index=h,
                    energy_rate_eur_kwh=energy_rate,
                    grid_distribution_rate=grid_rate,
                    grid_transmission_rate=0.0,  # In Germany, transmission is rolled into Netzentgelte
                    taxes_and_levies_rate=taxes_rate,
                    vat_rate=GERMAN_VAT_RATE,
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
        contract = facility_contract if isinstance(facility_contract, GermanFacilityContract) else GermanFacilityContract()
        epex_mwh = kwargs.get("tea_eur_mwh", kwargs.get("epex_eur_mwh", 95.0))

        energy_rate = (epex_mwh / 1000.0) + contract.retail_margin_eur_kwh
        grid_rate, is_peak = self._get_grid_fee_rate(timestamp, contract)
        stromsteuer = STROMSTEUER_REDUCED_EUR_KWH if contract.is_manufacturing_tax_relief else STROMSTEUER_STANDARD_EUR_KWH
        taxes_rate = stromsteuer + KONZESSIONSABGABE_EUR_KWH + KWKG_UMLAGE_EUR_KWH + OFFSHORE_UMLAGE_EUR_KWH + STROMNEV_UMLAGE_EUR_KWH

        total_unit_rate = (energy_rate + grid_rate + taxes_rate) * (1.0 + GERMAN_VAT_RATE)
        hourly_cap = (contract.netzentgelt_gp_eur_kw_yr * contract.contracted_kw) / (365.0 * 24.0)

        running_cost = round((power_kw * total_unit_rate) + hourly_cap, 2)
        incremental_cost = round(energy_kwh_delta * total_unit_rate, 4)

        peak_thresh = contract.contracted_kw * 0.90
        is_excess = (power_kw > peak_thresh)
        excess_kw = max(0.0, power_kw - peak_thresh) if is_excess else 0.0

        return CostCalculationResult(
            current_rate_eur_per_kwh=round(total_unit_rate, 4),
            running_cost_eur_per_h=running_cost,
            incremental_cost_eur=incremental_cost,
            is_peak_window=is_peak,
            is_excess_breach=is_excess,
            excess_power_kw=round(excess_kw, 2),
            projected_excess_penalty_eur=0.0,
            regulated_rate_eur_per_kwh=round(grid_rate + taxes_rate, 5),
            vat_rate=GERMAN_VAT_RATE,
            supply_rate_eur_per_kwh=round(energy_rate, 5),
            hourly_capacity_rate_eur_h=round(hourly_cap, 4),
        )

    def calculate_periodic_bill(self, bill_input: Any) -> Any:
        """Itemized German electricity invoice calculation."""
        days = getattr(bill_input, "billing_period_days", 30)
        total_kwh = getattr(bill_input, "energy_active_total_kwh", 0.0)
        kw = getattr(bill_input, "contracted_capacity_kva", 50.0)
        epex_avg = getattr(bill_input, "wholesale_tea_dam_eur_mwh", 95.0)
        enwg_module = getattr(bill_input, "enwg_14a_module", 0)

        contract = GermanFacilityContract(contracted_kw=kw, enwg_14a_module=enwg_module)
        grid_ap, _ = self._get_grid_fee_rate(datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc), contract)

        energy_supply_eur = round(total_kwh * ((epex_avg / 1000.0) + contract.retail_margin_eur_kwh), 2)
        base_fee_eur = round((contract.base_monthly_fee_eur / 30.0) * days, 2)
        grid_energy_eur = round(total_kwh * grid_ap, 2)
        grid_capacity_eur = round((contract.netzentgelt_gp_eur_kw_yr * kw * days) / 365.0, 2)

        # §14a Modul 1 rebate credit
        rebate_eur = 0.0
        if contract.enwg_14a_module == 1:
            rebate_eur = round((contract.enwg_14a_modul1_annual_credit_eur / 365.0) * days, 2)

        stromsteuer_eur = round(total_kwh * STROMSTEUER_STANDARD_EUR_KWH, 2)
        concession_eur = round(total_kwh * KONZESSIONSABGABE_EUR_KWH, 2)
        surcharges_eur = round(total_kwh * (KWKG_UMLAGE_EUR_KWH + OFFSHORE_UMLAGE_EUR_KWH + STROMNEV_UMLAGE_EUR_KWH), 2)

        pretax_total = round(
            energy_supply_eur + base_fee_eur + grid_energy_eur + grid_capacity_eur - rebate_eur
            + stromsteuer_eur + concession_eur + surcharges_eur, 2
        )
        vat_eur = round(pretax_total * GERMAN_VAT_RATE, 2)
        total_payable = round(pretax_total + vat_eur, 2)

        return {
            "bill_id": getattr(bill_input, "bill_id", "DE-BILL-01"),
            "bidding_zone": "DE-LU",
            "energy_supply_eur": energy_supply_eur,
            "base_fee_eur": base_fee_eur,
            "grid_energy_eur": grid_energy_eur,
            "grid_capacity_eur": grid_capacity_eur,
            "enwg_14a_rebate_eur": rebate_eur,
            "taxes_and_surcharges_eur": round(stromsteuer_eur + concession_eur + surcharges_eur, 2),
            "pretax_total_eur": pretax_total,
            "vat_amount_eur": vat_eur,
            "total_payable_eur": total_payable,
        }

    def get_demand_capacity_limits(
        self,
        timestamp: datetime,
        facility_contract: Any,
    ) -> DemandCapacityLimit:
        kw = getattr(facility_contract, "contracted_kw", 50.0)
        return DemandCapacityLimit(
            contracted_capacity_kw=float(kw),
            peak_demand_threshold_kw=round(kw * 0.90, 2),
            capacity_penalty_rate_eur_kw=round((DEFAULT_NETZENTGELT_GP_EUR_KW_YR / 365.0) * 1.5, 4),
            allows_power_factor_penalty=False,
        )
