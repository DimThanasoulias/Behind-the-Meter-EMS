"""Market client interfaces and implementations for Greek Energy Market Ingestion.

Provides:
- IMarketClient: Abstract interface
- LiveMarketClient: Production client connecting to RAE and HEnEx endpoints
- MockMarketClient: Deterministic offline client with network failure injection and recording
"""

from __future__ import annotations

import abc

import httpx

from backend.market.fetcher_henex import (
    fetch_dam_hourly_prices,
    is_dst_transition_day,
)
from backend.market.models import DamHourlyPrice, GreenTariffAnnouncement
from backend.market.scraper_rae import scrape_monthly_green_tariffs


class IMarketClient(abc.ABC):
    """Abstract interface for external Greek energy market data sources."""

    @abc.abstractmethod
    async def fetch_dam_prices(self, target_date: str) -> list[DamHourlyPrice]:
        """Fetch 24-hour DAM hourly clearing prices for the given date (YYYY-MM-DD)."""
        ...

    @abc.abstractmethod
    async def fetch_green_tariffs(self, month: str) -> list[GreenTariffAnnouncement]:
        """Fetch monthly Green Tariff announcements for the given month (YYYY-MM)."""
        ...


class LiveMarketClient(IMarketClient):
    """Live HTTP client querying official Greek market and regulatory endpoints."""

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    async def fetch_dam_prices(self, target_date: str) -> list[DamHourlyPrice]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await fetch_dam_hourly_prices(target_date, http_client=client)

    async def fetch_green_tariffs(self, month: str) -> list[GreenTariffAnnouncement]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await scrape_monthly_green_tariffs(month, http_client=client)


class MockMarketClient(IMarketClient):
    """Deterministic offline market client for testing, simulation, and hermetic environments."""

    def __init__(
        self,
        should_fail_dam: bool = False,
        should_fail_green: bool = False,
        dam_curves: dict[str, list[DamHourlyPrice]] | None = None,
        green_tariffs: dict[str, list[GreenTariffAnnouncement]] | None = None,
    ) -> None:
        self.should_fail_dam = should_fail_dam
        self.should_fail_green = should_fail_green
        self.dam_curves: dict[str, list[DamHourlyPrice]] = dam_curves or {}
        self.green_tariffs: dict[str, list[GreenTariffAnnouncement]] = green_tariffs or {}

        # Call tracking
        self.dam_calls: list[str] = []
        self.green_calls: list[str] = []

    def set_dam_curve(self, target_date: str, prices: list[DamHourlyPrice]) -> None:
        """Register custom DAM curve for a date."""
        self.dam_curves[target_date] = prices

    def set_green_tariffs(self, month: str, tariffs: list[GreenTariffAnnouncement]) -> None:
        """Register custom green tariffs for a month."""
        self.green_tariffs[month] = tariffs

    async def fetch_dam_prices(self, target_date: str) -> list[DamHourlyPrice]:
        self.dam_calls.append(target_date)
        if self.should_fail_dam:
            raise httpx.ConnectError(f"Simulated network failure connecting to HEnEx for {target_date}")

        if target_date in self.dam_curves:
            return self.dam_curves[target_date]

        # Generate realistic synthetic Greek curve
        _is_dst, expected_hours = is_dst_transition_day(target_date)
        records: list[DamHourlyPrice] = []
        # Benchmark diurnal profile centered around 120 €/MWh
        base_profile = [
            92.0, 85.0, 80.0, 78.0, 82.0, 90.0,
            105.0, 125.0, 148.0, 145.0, 122.0, 110.0,
            102.0, 98.0, 104.0, 115.0, 128.0, 142.0,
            175.0, 190.0, 178.0, 161.0, 124.0, 101.0
        ]
        if expected_hours == 23:
            # Skip hour 3 in spring transition
            curve = base_profile[:3] + base_profile[4:]
        elif expected_hours == 25:
            # Repeat hour 2 in autumn transition
            curve = base_profile[:3] + [base_profile[2]] + base_profile[3:]
        else:
            curve = base_profile

        for h, price in enumerate(curve):
            records.append(
                DamHourlyPrice(
                    date=target_date,
                    hour=h,
                    price_eur_mwh=round(price, 2),
                    price_eur_kwh=round(price / 1000.0, 5),
                    source="henex_live",
                )
            )
        return records

    async def fetch_green_tariffs(self, month: str) -> list[GreenTariffAnnouncement]:
        self.green_calls.append(month)
        if self.should_fail_green:
            raise httpx.ConnectError(f"Simulated network failure connecting to RAE for {month}")

        if month in self.green_tariffs:
            return self.green_tariffs[month]

        # Return standard benchmark suppliers
        return [
            GreenTariffAnnouncement(
                month=month,
                supplier_id="dei",
                supplier_name="ΔΕΗ (Public Power Corporation)",
                contract_type="G21",
                p_base=0.155,
                e_disc=0.020,
                prompt_discount_percent=12.9,
                alpha=1.15,
                lu_eur_mwh=115.0,
                ll_eur_mwh=95.0,
                beta=0.0,
                fixed_monthly_fee_eur=5.0,
                published_final_rate_eur_per_kwh=0.14075,
                tea_m1_eur_mwh=120.0,
                source="rae_feed",
            ),
            GreenTariffAnnouncement(
                month=month,
                supplier_id="dei",
                supplier_name="ΔΕΗ (Public Power Corporation)",
                contract_type="G22",
                p_base=0.165,
                e_disc=0.020,
                prompt_discount_percent=12.1,
                alpha=1.15,
                lu_eur_mwh=115.0,
                ll_eur_mwh=95.0,
                beta=0.0,
                fixed_monthly_fee_eur=5.0,
                published_final_rate_eur_per_kwh=0.15075,
                tea_m1_eur_mwh=120.0,
                source="rae_feed",
            ),
        ]
