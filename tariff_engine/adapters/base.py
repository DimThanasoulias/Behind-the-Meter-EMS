"""
European Market Adapter Base Protocol & Common Data Contracts (Requirement R4).

Defines the abstract interface BaseMarketAdapter and supporting data structures
decoupling the downstream mathematical optimization engine (R1: optimization_engine/)
from country-specific tariff legislation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MarketMetadata:
    """
    Descriptive metadata for an electricity market and regulatory regime.
    """
    bidding_zone: str           # e.g., 'GR', 'DE-LU', 'ES'
    country_code: str           # ISO 3166-1 alpha-2, e.g., 'GR', 'DE', 'ES'
    country_name: str           # Full name, e.g., 'Greece', 'Germany', 'Spain'
    currency: str               # ISO 4217, typically 'EUR'
    regulatory_body: str        # e.g., 'RAAEY', 'BNetzA', 'CNMC'
    default_vat_rate: float     # e.g., 0.06, 0.19, 0.21
    wholesale_market: str       # e.g., 'HEnEx', 'EPEX Spot', 'OMIE'
    supports_dynamic_dam: bool = True
    supports_periodic_billing: bool = True
    notes: str = ""


@dataclass(frozen=True)
class HourlyPriceVector:
    """
    Time-series interval price breakdown used by the constrained optimization engine
    and dashboard forecasting services.
    """
    timestamp: datetime
    interval_index: int               # 0 to horizon_hours - 1
    energy_rate_eur_kwh: float        # Wholesale spot or retail supply rate
    grid_distribution_rate: float     # Distribution network fee
    grid_transmission_rate: float     # Transmission system fee
    taxes_and_levies_rate: float      # Statutory duties, excises, and surcharges
    vat_rate: float                   # Applicable VAT rate (e.g. 0.06, 0.19, 0.21)
    total_rate_ex_vat: float          # Sum of energy + grid + taxes
    total_rate_inc_vat: float         # All-in marginal electricity rate (C_t)
    is_peak_window: bool              # Critical/peak pricing window flag
    is_critical_peak: bool = False    # Emergency demand response / peak-load warning flag
    standing_capacity_rate_eur_h: float = 0.0  # Prorated standing capacity cost (€/h)

    @property
    def marginal_cost(self) -> float:
        """Convenience alias for optimization solver objective coefficient C_t."""
        return self.total_rate_inc_vat


@dataclass(frozen=True)
class DemandCapacityLimit:
    """
    Physical and contractual capacity limits for a commercial facility.
    """
    contracted_capacity_kw: float
    peak_demand_threshold_kw: float
    capacity_penalty_rate_eur_kw: float = 0.0
    allows_power_factor_penalty: bool = False

    def is_capacity_exceeded(self, power_kw: float) -> bool:
        """Checks if power exceeds the threshold."""
        return power_kw > self.peak_demand_threshold_kw


class BaseMarketAdapter(ABC):
    """
    Abstract Protocol defining European electricity market rules, wholesale DAM pricing,
    regulated network charges, and periodic utility bill calculation.
    """

    @abstractmethod
    def get_market_metadata(self) -> MarketMetadata:
        """Returns market identifiers, bidding zone, currency, and regulatory body."""
        raise NotImplementedError

    @abstractmethod
    def get_hourly_price_vector(
        self,
        start_dt: datetime,
        horizon_hours: int = 24,
        facility_contract: Any = None,
        spot_prices: list[float] | None = None,
    ) -> list[HourlyPriceVector]:
        """
        Computes the time-series price vector over a rolling horizon (default 24 hours).
        Each element contains the itemized rates and total all-in marginal cost C_t.
        """
        raise NotImplementedError

    @abstractmethod
    def calculate_instantaneous_cost(
        self,
        power_kw: float,
        energy_kwh_delta: float,
        timestamp: datetime,
        facility_contract: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Evaluates instantaneous running cost (€/h) and incremental packet cost (€)
        for real-time streaming telemetry.
        """
        raise NotImplementedError

    @abstractmethod
    def calculate_periodic_bill(
        self,
        bill_input: Any,
    ) -> Any:
        """
        Calculates an itemized periodic utility bill for formal verification and auditing.
        """
        raise NotImplementedError

    @abstractmethod
    def get_demand_capacity_limits(
        self,
        timestamp: datetime,
        facility_contract: Any,
    ) -> DemandCapacityLimit:
        """
        Returns active power capacity thresholds before contractual penalties apply.
        """
        raise NotImplementedError

    def get_c_t_vector(
        self,
        start_dt: datetime,
        horizon_hours: int = 24,
        facility_contract: Any = None,
        spot_prices: list[float] | None = None,
    ) -> list[float]:
        """
        Convenience method directly extracting the 1D float list of all-in marginal
        electricity costs [C_0, C_1, ..., C_{T-1}] in €/kWh for SciPy HiGHS MILP solvers.
        """
        price_vectors = self.get_hourly_price_vector(
            start_dt=start_dt,
            horizon_hours=horizon_hours,
            facility_contract=facility_contract,
            spot_prices=spot_prices,
        )
        return [p.total_rate_inc_vat for p in price_vectors]

    def format_vector_summary(
        self,
        vector: list[HourlyPriceVector],
    ) -> dict[str, Any]:
        """Calculates statistical summary for telemetry dashboards."""
        if not vector:
            return {"count": 0}
        rates = [p.total_rate_inc_vat for p in vector]
        peak_count = sum(1 for p in vector if p.is_peak_window)
        return {
            "bidding_zone": self.get_market_metadata().bidding_zone,
            "horizon_hours": len(vector),
            "min_rate_eur_kwh": round(min(rates), 5),
            "max_rate_eur_kwh": round(max(rates), 5),
            "mean_rate_eur_kwh": round(sum(rates) / len(rates), 5),
            "peak_hours_count": peak_count,
            "price_spread_eur_kwh": round(max(rates) - min(rates), 5),
        }
