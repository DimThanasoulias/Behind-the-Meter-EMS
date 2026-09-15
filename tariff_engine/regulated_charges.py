"""
Greek Electricity Regulated Charges (Ρυθμιζόμενες Χρεώσεις) Engine.

Governed by RAAEY (Regulatory Authority for Waste, Energy and Water).
Models:
- DEDDIE distribution charges (capacity rate €/kVA/yr, energy rate €/kWh).
- ADMIE transmission charges (capacity rate €/kVA/yr, energy rate €/kWh).
- ETMEAR (ΕΤΜΕΑΡ - Special Renewable Energy Duty).
- YKO (ΥΚΩ - Public Service Obligations).
- EFK (ΕΦΚ - Special Consumption Tax).
- DETE (ΔΕΤΕ - Special 5‰ Duty).
- Greek Electricity VAT (6%).
"""

from __future__ import annotations

from dataclasses import dataclass

# RAAEY Regulated Constants
DEDDIE_CAPACITY_RATE_EUR_KVA_YR = 4.434  # €/kVA/year
DEDDIE_ENERGY_RATE_EUR_KWH = 0.01415     # €/kWh
ADMIE_CAPACITY_RATE_EUR_KVA_YR = 4.430   # €/kVA/year
ADMIE_ENERGY_RATE_EUR_KWH = 0.00560      # €/kWh

ETMEAR_LV_RATE_EUR_KWH = 0.01700         # €/kWh for Low Voltage (Γ21, Γ22)
ETMEAR_MV_RATE_EUR_KWH = 0.01200         # €/kWh for Medium Voltage (Γ23)
YKO_RATE_EUR_KWH = 0.00690               # €/kWh
EFK_RATE_EUR_KWH = 0.00220               # €/kWh
DETE_PERCENT = 0.005                     # 0.5% (5‰)
DETE_FIXED_EQUIVALENT_EUR_KWH = 0.00095  # Standard unit volumetric equivalent
VAT_RATE = 0.06                          # 6% Greek VAT for electricity


@dataclass(frozen=True)
class RegulatedBreakdown:
    """Detailed breakdown of regulated charges per kWh."""
    deddie_energy: float
    deddie_penalized: float
    admie_energy: float
    etmear: float
    yko: float
    efk: float
    dete: float
    subtotal_energy: float
    total_regulated_per_kwh: float
    pf_multiplier: float
    vat_rate: float = VAT_RATE


def calculate_regulated_unit_rate(
    contracted_kva: float = 35.0,
    power_factor: float = 0.98,
    is_lv: bool = True,
    dete_eur_kwh: float = DETE_FIXED_EQUIVALENT_EUR_KWH,
) -> float:
    """
    Computes total regulated volumetric unit charge (€/kWh).

    Includes:
    - DEDDIE energy charge (penalized if power_factor < 0.85)
    - ADMIE energy charge
    - ETMEAR (LV or MV rate)
    - YKO public service levy
    - EFK special consumption tax
    - DETE 5‰ duty

    Args:
        contracted_kva: Agreed capacity in kVA.
        power_factor: Operating power factor cos φ (evaluates absolute value).
        is_lv: True for Low Voltage (Γ21/Γ22), False for Medium Voltage (Γ23).
        dete_eur_kwh: DETE volumetric charge (default: 0.00095 €/kWh).

    Returns:
        Total regulated rate in €/kWh rounded to 6 decimal places.
    """
    eff_pf = max(0.01, min(abs(power_factor), 1.0))
    pf_mult = (0.85 / eff_pf) if eff_pf < 0.85 else 1.0

    deddie_penalized = DEDDIE_ENERGY_RATE_EUR_KWH * pf_mult
    admie_energy = ADMIE_ENERGY_RATE_EUR_KWH
    etmear = ETMEAR_LV_RATE_EUR_KWH if is_lv else ETMEAR_MV_RATE_EUR_KWH
    yko = YKO_RATE_EUR_KWH
    efk = EFK_RATE_EUR_KWH

    subtotal_energy = deddie_penalized + admie_energy + etmear + yko + efk
    return round(subtotal_energy + dete_eur_kwh, 6)


def get_regulated_breakdown(
    contracted_kva: float = 35.0,
    power_factor: float = 0.98,
    is_lv: bool = True,
    dete_eur_kwh: float = DETE_FIXED_EQUIVALENT_EUR_KWH,
) -> RegulatedBreakdown:
    """
    Provides an itemized breakdown of all regulated unit charge components.
    """
    eff_pf = max(0.01, min(abs(power_factor), 1.0))
    pf_mult = (0.85 / eff_pf) if eff_pf < 0.85 else 1.0

    deddie_penalized = DEDDIE_ENERGY_RATE_EUR_KWH * pf_mult
    admie_energy = ADMIE_ENERGY_RATE_EUR_KWH
    etmear = ETMEAR_LV_RATE_EUR_KWH if is_lv else ETMEAR_MV_RATE_EUR_KWH
    yko = YKO_RATE_EUR_KWH
    efk = EFK_RATE_EUR_KWH
    subtotal = deddie_penalized + admie_energy + etmear + yko + efk
    total = round(subtotal + dete_eur_kwh, 6)

    return RegulatedBreakdown(
        deddie_energy=DEDDIE_ENERGY_RATE_EUR_KWH,
        deddie_penalized=round(deddie_penalized, 6),
        admie_energy=admie_energy,
        etmear=etmear,
        yko=yko,
        efk=efk,
        dete=dete_eur_kwh,
        subtotal_energy=round(subtotal, 6),
        total_regulated_per_kwh=total,
        pf_multiplier=round(pf_mult, 4),
    )


def calculate_deddie_capacity_charge(contracted_kva: float, days: int = 30) -> float:
    """
    Calculates DEDDIE capacity standing charge:
    C_dist_cap = (MPX_dist * S_agreed_kVA * Days) / 365
    """
    return round((DEDDIE_CAPACITY_RATE_EUR_KVA_YR * contracted_kva * days) / 365.0, 4)


def calculate_admie_capacity_charge(contracted_kva: float, days: int = 30) -> float:
    """
    Calculates ADMIE capacity standing charge:
    C_trans_cap = (MPX_trans * S_agreed_kVA * Days) / 365
    """
    return round((ADMIE_CAPACITY_RATE_EUR_KVA_YR * contracted_kva * days) / 365.0, 4)


def calculate_fixed_capacity_charges(contracted_kva: float, days: int = 30) -> dict[str, float]:
    """
    Calculates total standing capacity charges for DEDDIE and ADMIE over a period of days.
    """
    deddie_cap = calculate_deddie_capacity_charge(contracted_kva, days)
    admie_cap = calculate_admie_capacity_charge(contracted_kva, days)
    return {
        "deddie_capacity_eur": deddie_cap,
        "admie_capacity_eur": admie_cap,
        "total_capacity_eur": round(deddie_cap + admie_cap, 4),
    }


def calculate_hourly_capacity_rate(contracted_kva: float) -> float:
    """
    Computes capacity standing charge rate per hour in €/h:
    ((MPX_dist + MPX_trans) * S_agreed_kVA) / (365 * 24)
    """
    annual_rate = (DEDDIE_CAPACITY_RATE_EUR_KVA_YR + ADMIE_CAPACITY_RATE_EUR_KVA_YR) * contracted_kva
    return round(annual_rate / (365.0 * 24.0), 5)
