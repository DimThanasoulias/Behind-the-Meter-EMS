"""
Ground-Truth Benchmark Utility Bill Dataset (Requirement R2).

Defines 9 curated commercial electricity bills representing real-world commercial operations
in Greece under statutory RAAEY regulations and Law 5068/2023.

Coverage:
1. BILL-01-DEI-G21-SUMMER: Artisanal Bakery, Single-rate Γ21 Green, neutral MD band, 12.9% prompt discount.
2. BILL-02-DEI-G21-SPIKE: Retail Workshop, Single-rate Γ21 Green, wholesale price spike MD breach (+€0.03450/kWh).
3. BILL-03-PROT-G22-SUMMER-PEAK: Commercial Bakery, Dual-rate Γ22 Green, Summer Peak window (14:00-17:00, +25%).
4. BILL-04-PROT-G22-WINTER-PEAK: Boutique Hotel, Dual-rate Γ22 Green, Winter Peak window (17:00-21:00, +25%).
5. BILL-05-ELPED-G22-LOW-PF: Cold Storage, Dual-rate Γ22 Green, severe low power factor (cos φ = 0.68, +25% DEDDIE fee).
6. BILL-06-HERON-G22-CAP-BREACH: Supermarket, Dual-rate Γ22 Green, contracted capacity breach (35 kVA vs 43.5 kVA max demand).
7. BILL-07-DEI-G21-YELLOW-DAM: Coffee Bistro, Single-rate Γ21 Yellow, wholesale DAM indexed with 13.5% losses.
8. BILL-08-DYNAMIC-SPOT-INTERVAL: Smart Bakery, Dual-rate Γ22 Dynamic, interval spot pricing.
9. BILL-09-HERON-G23-MV-INDUSTRIAL: Industrial Plastics, Tri-rate Γ23 Medium Voltage, large industrial connection (400 kVA).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .billing import UtilityBillInput
from .contracts import Season, TariffColor, TariffContract


@dataclass(frozen=True)
class BenchmarkBillDefinition:
    """Encapsulates input specifications, ground-truth itemized breakdown, and metadata."""
    bill_id: str
    facility_id: str
    facility_name: str
    contract_type: TariffContract
    tariff_color: TariffColor
    season: Season
    input_spec: UtilityBillInput
    expected_charges: dict[str, float]
    regulatory_focus: str


# -----------------------------------------------------------------------------
# 9 Statutory Benchmark Bills (Exact Ground Truth)
# -----------------------------------------------------------------------------

BENCHMARK_BILLS: dict[str, dict[str, Any]] = {
    "BILL-01-DEI-G21-SUMMER": {
        "facility_name": "Artisanal Bakery & Cafe",
        "regulatory_focus": "Single-rate uniform LV <= 25 kVA, neutral MD deadband, 12.9% prompt discount",
        "input": UtilityBillInput(
            bill_id="BILL-01-DEI-G21-SUMMER",
            facility_id="bakery_small",
            supplier_name="ΔΕΗ",
            contract_type=TariffContract.G21,
            tariff_color=TariffColor.GREEN,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            billing_period_days=31,
            contracted_capacity_kva=25.0,
            power_factor=0.96,
            energy_active_total_kwh=2450.0,
            energy_normal_kwh=2450.0,
            base_supply_rate_eur_kwh=0.155,
            prompt_discount_percent=12.9,
            fixed_monthly_fee_eur=5.00,
            wholesale_tea_m1_eur_mwh=105.0,  # Neutral band: 95 <= TEA <= 115 => MD = 0.0
        ),
        "expected": {
            "supply_energy_base": 379.75,
            "supply_fixed": 5.00,
            "supply_md": 0.00,
            "supply_discount": 48.99,
            "supply_subtotal": 335.76,
            "admie_capacity": 9.41,
            "admie_energy": 13.72,
            "admie_subtotal": 23.13,
            "deddie_capacity": 9.41,
            "deddie_energy": 34.67,
            "deddie_pf_penalty": 0.00,
            "deddie_cap_excess": 0.00,
            "deddie_subtotal": 44.08,
            "etmear": 41.65,
            "yko": 16.91,
            "efk": 5.39,
            "dete": 2.33,
            "other_regulated_subtotal": 66.28,
            "regulated_subtotal": 133.49,
            "pretax_total": 469.25,
            "vat_amount": 28.15,
            "total_payable": 497.40,
        },
    },

    "BILL-02-DEI-G21-SPIKE": {
        "facility_name": "Retail Fabrication Workshop",
        "regulatory_focus": "Wholesale spike breach (TEA=145 €/MWh > Lu=115), Law 5068/2023 MD=+0.03450 €/kWh",
        "input": UtilityBillInput(
            bill_id="BILL-02-DEI-G21-SPIKE",
            facility_id="workshop_retail",
            supplier_name="ΔΕΗ",
            contract_type=TariffContract.G21,
            tariff_color=TariffColor.GREEN,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            billing_period_days=31,
            contracted_capacity_kva=25.0,
            power_factor=0.95,
            energy_active_total_kwh=3100.0,
            energy_normal_kwh=3100.0,
            base_supply_rate_eur_kwh=0.155,
            prompt_discount_percent=5.0,
            fixed_monthly_fee_eur=5.00,
            wholesale_tea_m1_eur_mwh=145.0,  # MD = 1.15 * (0.145 - 0.115) = 0.03450 €/kWh
        ),
        "expected": {
            "supply_energy_base": 480.50,
            "supply_fixed": 5.00,
            "supply_md": 106.95,
            "supply_discount": 24.03,
            "supply_subtotal": 568.42,
            "admie_capacity": 9.41,
            "admie_energy": 17.36,
            "admie_subtotal": 26.77,
            "deddie_capacity": 9.41,
            "deddie_energy": 43.86,
            "deddie_pf_penalty": 0.00,
            "deddie_cap_excess": 0.00,
            "deddie_subtotal": 53.27,
            "etmear": 52.70,
            "yko": 21.39,
            "efk": 6.82,
            "dete": 2.94,
            "other_regulated_subtotal": 83.85,
            "regulated_subtotal": 163.89,
            "pretax_total": 732.31,
            "vat_amount": 43.94,
            "total_payable": 776.25,
        },
    },

    "BILL-03-PROT-G22-SUMMER-PEAK": {
        "facility_name": "Commercial Bakery & Confectionery",
        "regulatory_focus": "Dual-rate TOU Summer Peak window (14:00-17:00, +25%), MD=+0.00575 €/kWh",
        "input": UtilityBillInput(
            bill_id="BILL-03-PROT-G22-SUMMER-PEAK",
            facility_id="bakery_commercial",
            supplier_name="Protergia",
            contract_type=TariffContract.G22,
            tariff_color=TariffColor.GREEN,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            billing_period_days=31,
            contracted_capacity_kva=50.0,
            power_factor=0.94,
            energy_active_total_kwh=8200.0,
            energy_normal_kwh=3800.0,
            energy_peak_kwh=2200.0,
            energy_offpeak_kwh=2200.0,
            base_supply_rate_eur_kwh=0.165,
            prompt_discount_percent=5.0,
            fixed_monthly_fee_eur=5.00,
            wholesale_tea_m1_eur_mwh=120.0,  # MD = 1.15 * (0.120 - 0.115) = 0.00575 €/kWh
        ),
        "expected": {
            "supply_energy_base": 1334.85,
            "supply_fixed": 5.00,
            "supply_md": 47.15,
            "supply_discount": 66.74,
            "supply_subtotal": 1320.26,
            "admie_capacity": 18.81,
            "admie_energy": 45.92,
            "admie_subtotal": 64.73,
            "deddie_capacity": 18.83,
            "deddie_energy": 116.03,
            "deddie_pf_penalty": 0.00,
            "deddie_cap_excess": 0.00,
            "deddie_subtotal": 134.86,
            "etmear": 139.40,
            "yko": 56.58,
            "efk": 18.04,
            "dete": 7.79,
            "other_regulated_subtotal": 221.81,
            "regulated_subtotal": 421.40,
            "pretax_total": 1741.66,
            "vat_amount": 104.50,
            "total_payable": 1846.16,
        },
    },

    "BILL-04-PROT-G22-WINTER-PEAK": {
        "facility_name": "Boutique Hotel & Suites",
        "regulatory_focus": "Dual-rate TOU Winter Peak window (17:00-21:00, +25%), heat pump winter load",
        "input": UtilityBillInput(
            bill_id="BILL-04-PROT-G22-WINTER-PEAK",
            facility_id="boutique_hotel",
            supplier_name="Protergia",
            contract_type=TariffContract.G22,
            tariff_color=TariffColor.GREEN,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            billing_period_days=31,
            contracted_capacity_kva=70.0,
            power_factor=0.92,
            energy_active_total_kwh=12500.0,
            energy_normal_kwh=5500.0,
            energy_peak_kwh=3500.0,
            energy_offpeak_kwh=3500.0,
            base_supply_rate_eur_kwh=0.165,
            prompt_discount_percent=5.0,
            fixed_monthly_fee_eur=5.00,
            wholesale_tea_m1_eur_mwh=110.0,  # Neutral deadband MD = 0.0
        ),
        "expected": {
            "supply_energy_base": 2033.63,
            "supply_fixed": 5.00,
            "supply_md": 0.00,
            "supply_discount": 101.68,
            "supply_subtotal": 1936.95,
            "admie_capacity": 26.34,
            "admie_energy": 70.00,
            "admie_subtotal": 96.34,
            "deddie_capacity": 26.36,
            "deddie_energy": 176.88,
            "deddie_pf_penalty": 0.00,
            "deddie_cap_excess": 0.00,
            "deddie_subtotal": 203.24,
            "etmear": 212.50,
            "yko": 86.25,
            "efk": 27.50,
            "dete": 11.88,
            "other_regulated_subtotal": 338.13,
            "regulated_subtotal": 637.71,
            "pretax_total": 2574.66,
            "vat_amount": 154.48,
            "total_payable": 2729.14,
        },
    },

    "BILL-05-ELPED-G22-LOW-PF": {
        "facility_name": "Cold Storage Logistics Facility",
        "regulatory_focus": "Severe inductive draw (cos φ = 0.68 < 0.85 => M_PF = 1.25, +25% DEDDIE energy penalty)",
        "input": UtilityBillInput(
            bill_id="BILL-05-ELPED-G22-LOW-PF",
            facility_id="cold_storage",
            supplier_name="Elpedison",
            contract_type=TariffContract.G22,
            tariff_color=TariffColor.GREEN,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            billing_period_days=30,
            contracted_capacity_kva=50.0,
            power_factor=0.68,  # M_PF = 0.85 / 0.68 = 1.25
            energy_active_total_kwh=11000.0,
            energy_normal_kwh=5000.0,
            energy_peak_kwh=3000.0,
            energy_offpeak_kwh=3000.0,
            base_supply_rate_eur_kwh=0.165,
            prompt_discount_percent=0.0,
            fixed_monthly_fee_eur=5.00,
            wholesale_tea_m1_eur_mwh=100.0,
        ),
        "expected": {
            "supply_energy_base": 1790.25,
            "supply_fixed": 5.00,
            "supply_md": 0.00,
            "supply_discount": 0.00,
            "supply_subtotal": 1795.25,
            "admie_capacity": 18.21,
            "admie_energy": 61.60,
            "admie_subtotal": 79.81,
            "deddie_capacity": 18.22,
            "deddie_energy": 155.65,
            "deddie_pf_penalty": 38.91,  # 155.65 * (1.25 - 1.0) = 38.91
            "deddie_cap_excess": 0.00,
            "deddie_subtotal": 212.78,
            "etmear": 187.00,
            "yko": 75.90,
            "efk": 24.20,
            "dete": 10.45,
            "other_regulated_subtotal": 297.55,
            "regulated_subtotal": 590.14,
            "pretax_total": 2385.39,
            "vat_amount": 143.12,
            "total_payable": 2528.51,
        },
    },

    "BILL-06-HERON-G22-CAP-BREACH": {
        "facility_name": "Commercial Supermarket",
        "regulatory_focus": "Agreed connection breach (35 kVA contracted vs 43.5 kVA peak, k=2.5 penalty surcharge)",
        "input": UtilityBillInput(
            bill_id="BILL-06-HERON-G22-CAP-BREACH",
            facility_id="supermarket_medium",
            supplier_name="Heron",
            contract_type=TariffContract.G22,
            tariff_color=TariffColor.GREEN,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            billing_period_days=31,
            contracted_capacity_kva=35.0,
            max_demand_kva=43.5,  # Delta = 8.5 kVA
            power_factor=0.93,
            energy_active_total_kwh=9500.0,
            energy_normal_kwh=4500.0,
            energy_peak_kwh=2500.0,
            energy_offpeak_kwh=2500.0,
            base_supply_rate_eur_kwh=0.165,
            prompt_discount_percent=0.0,
            fixed_monthly_fee_eur=5.00,
            wholesale_tea_m1_eur_mwh=110.0,
            capacity_penalty_multiplier=2.5,
        ),
        "expected": {
            "supply_energy_base": 1546.87,
            "supply_fixed": 5.00,
            "supply_md": 0.00,
            "supply_discount": 0.00,
            "supply_subtotal": 1551.87,
            "admie_capacity": 13.17,
            "admie_energy": 53.20,
            "admie_subtotal": 66.37,
            "deddie_capacity": 13.18,
            "deddie_energy": 134.42,
            "deddie_pf_penalty": 0.00,
            "deddie_cap_excess": 8.00,  # 2.5 * (4.434 * 8.5 * 31)/365 = 8.00
            "deddie_subtotal": 155.60,
            "etmear": 161.50,
            "yko": 65.55,
            "efk": 20.90,
            "dete": 9.03,
            "other_regulated_subtotal": 256.98,
            "regulated_subtotal": 478.95,
            "pretax_total": 2030.82,
            "vat_amount": 121.85,
            "total_payable": 2152.67,
        },
    },

    "BILL-07-DEI-G21-YELLOW-DAM": {
        "facility_name": "Specialty Coffee Bistro & Roastery",
        "regulatory_focus": "Wholesale-indexed Yellow contract (TEA=118.50 €/MWh, 13.5% losses, 0.015 margin)",
        "input": UtilityBillInput(
            bill_id="BILL-07-DEI-G21-YELLOW-DAM",
            facility_id="cafe_bistro",
            supplier_name="ΔΕΗ",
            contract_type=TariffContract.G21,
            tariff_color=TariffColor.YELLOW,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 31),
            billing_period_days=31,
            contracted_capacity_kva=25.0,
            power_factor=0.97,
            energy_active_total_kwh=2800.0,
            energy_normal_kwh=2800.0,
            wholesale_tea_dam_eur_mwh=118.50,
            loss_factor=0.135,
            supplier_margin_eur_kwh=0.015,
            base_supply_rate_eur_kwh=0.040,  # 0.1185*1.135 + 0.015 + 0.040 = 0.18950 €/kWh
            prompt_discount_percent=0.0,
            fixed_monthly_fee_eur=5.00,
        ),
        "expected": {
            "supply_energy_base": 530.60,
            "supply_fixed": 5.00,
            "supply_md": 0.00,
            "supply_discount": 0.00,
            "supply_subtotal": 535.60,
            "admie_capacity": 9.41,
            "admie_energy": 15.68,
            "admie_subtotal": 25.09,
            "deddie_capacity": 9.41,
            "deddie_energy": 39.62,
            "deddie_pf_penalty": 0.00,
            "deddie_cap_excess": 0.00,
            "deddie_subtotal": 49.03,
            "etmear": 47.60,
            "yko": 19.32,
            "efk": 6.16,
            "dete": 2.66,
            "other_regulated_subtotal": 75.74,
            "regulated_subtotal": 149.86,
            "pretax_total": 685.46,
            "vat_amount": 41.13,
            "total_payable": 726.59,
        },
    },

    "BILL-08-DYNAMIC-SPOT-INTERVAL": {
        "facility_name": "Smart Automated Industrial Bakery",
        "regulatory_focus": "Interval dynamic spot settlement (weighted average rate = 0.15240 €/kWh)",
        "input": UtilityBillInput(
            bill_id="BILL-08-DYNAMIC-SPOT-INTERVAL",
            facility_id="bakery_smart_meter",
            supplier_name="Volton",
            contract_type=TariffContract.G22,
            tariff_color=TariffColor.DYNAMIC,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 30),
            billing_period_days=30,
            contracted_capacity_kva=50.0,
            power_factor=0.96,
            energy_active_total_kwh=9600.0,
            energy_normal_kwh=9600.0,
            weighted_dynamic_rate_eur_kwh=0.15240,
            prompt_discount_percent=0.0,
            fixed_monthly_fee_eur=5.00,
        ),
        "expected": {
            "supply_energy_base": 1463.04,
            "supply_fixed": 5.00,
            "supply_md": 0.00,
            "supply_discount": 0.00,
            "supply_subtotal": 1468.04,
            "admie_capacity": 18.21,
            "admie_energy": 53.76,
            "admie_subtotal": 71.97,
            "deddie_capacity": 18.22,
            "deddie_energy": 135.84,
            "deddie_pf_penalty": 0.00,
            "deddie_cap_excess": 0.00,
            "deddie_subtotal": 154.06,
            "etmear": 163.20,
            "yko": 66.24,
            "efk": 21.12,
            "dete": 9.12,
            "other_regulated_subtotal": 259.68,
            "regulated_subtotal": 485.71,
            "pretax_total": 1953.75,
            "vat_amount": 117.22,
            "total_payable": 2070.97,
        },
    },

    "BILL-09-HERON-G23-MV-INDUSTRIAL": {
        "facility_name": "Industrial Plastics & Packaging Plant",
        "regulatory_focus": "Medium Voltage Tri-rate Γ23 (400 kVA cap), discounted ETMEAR = 0.01200 €/kWh",
        "input": UtilityBillInput(
            bill_id="BILL-09-HERON-G23-MV-INDUSTRIAL",
            facility_id="plant_industrial",
            supplier_name="Heron",
            contract_type=TariffContract.G23,
            tariff_color=TariffColor.GREEN,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            billing_period_days=28,
            contracted_capacity_kva=400.0,
            power_factor=0.92,
            energy_active_total_kwh=85000.0,
            energy_normal_kwh=45000.0,
            energy_peak_kwh=20000.0,
            energy_offpeak_kwh=20000.0,
            base_supply_rate_eur_kwh=0.140,
            prompt_discount_percent=3.0,
            fixed_monthly_fee_eur=10.00,
            wholesale_tea_m1_eur_mwh=108.0,
            is_medium_voltage=True,
        ),
        "expected": {
            "supply_energy_base": 11760.00,
            "supply_fixed": 10.00,
            "supply_md": 0.00,
            "supply_discount": 352.80,
            "supply_subtotal": 11417.20,
            "admie_capacity": 135.93,
            "admie_energy": 476.00,
            "admie_subtotal": 611.93,
            "deddie_capacity": 136.06,
            "deddie_energy": 1202.75,
            "deddie_pf_penalty": 0.00,
            "deddie_cap_excess": 0.00,
            "deddie_subtotal": 1338.81,
            "etmear": 1020.00,  # Medium Voltage rate: 85000 * 0.01200
            "yko": 586.50,
            "efk": 187.00,
            "dete": 80.75,
            "other_regulated_subtotal": 1874.25,
            "regulated_subtotal": 3824.99,
            "pretax_total": 15242.19,
            "vat_amount": 914.53,
            "total_payable": 16156.72,
        },
    },
}

# Aliases mapping alternative IDs (e.g. from spec report) to canonical dataset keys
BENCHMARK_ALIASES: dict[str, str] = {
    "BILL-01-DEI-G21-STANDARD": "BILL-01-DEI-G21-SUMMER",
    "BILL-02-DEI-G21-GREEN-MD": "BILL-02-DEI-G21-SPIKE",
}


def get_benchmark_bill(bill_id: str) -> dict[str, Any]:
    """
    Retrieves a benchmark bill specification by ID or alias.
    Raises KeyError if not found.
    """
    canonical_id = BENCHMARK_ALIASES.get(bill_id, bill_id)
    if canonical_id not in BENCHMARK_BILLS:
        available = sorted(BENCHMARK_BILLS.keys())
        raise KeyError(f"Unknown benchmark bill ID '{bill_id}'. Available bills: {available}")
    return BENCHMARK_BILLS[canonical_id]


def list_benchmark_bill_ids() -> list[str]:
    """Returns sorted list of canonical benchmark bill IDs."""
    return sorted(BENCHMARK_BILLS.keys())


def get_all_benchmark_bills() -> dict[str, dict[str, Any]]:
    """Returns copy of all benchmark bills dictionary."""
    return dict(BENCHMARK_BILLS)
