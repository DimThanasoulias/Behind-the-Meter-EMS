"""Integration tests for Greek Energy Market REST APIs and live telemetry pricing.

Covers:
- GET /api/v1/market/dam/today
- GET /api/v1/market/dam/curve
- GET /api/v1/market/dam/hourly
- GET /api/v1/market/green-tariffs
- POST /api/v1/market/refresh-green
- POST /api/v1/market/fetch-dam
- GET /api/v1/market/status
- Dynamic market rate propagation into POST /api/v1/telemetry ingestion
- Fault-tolerant telemetry ingestion when market services are offline
"""

from __future__ import annotations

import copy
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.market.clients import MockMarketClient
from backend.market.models import DamHourlyPrice
from backend.market.service import MarketPriceService


@pytest.fixture
def isolated_market_client(tmp_path) -> Generator[TestClient, None, None]:
    """Provide a TestClient with isolated database and MockMarketClient."""
    db_path = str(tmp_path / "test_market_integration.db")
    app = create_app(db_path=db_path)

    with TestClient(app) as client:
        store = client.app.state.market_service.store
        mock_market = MockMarketClient()
        market_svc = MarketPriceService(store=store, client=mock_market)
        client.app.state.market_service = market_svc
        yield client


class TestMarketRestEndpoints:
    """Test all /api/v1/market REST endpoints."""

    def test_get_dam_today(self, isolated_market_client: TestClient):
        res = isolated_market_client.get("/api/v1/market/dam/today")
        assert res.status_code == 200
        data = res.json()
        assert "date" in data
        assert data["count_hours"] in (23, 24, 25)
        assert len(data["prices"]) == data["count_hours"]
        assert data["min_price_eur_mwh"] <= data["max_price_eur_mwh"]
        assert data["avg_price_eur_mwh"] > 0.0
        assert data["peak_avg_price_eur_mwh"] > 0.0

    def test_get_dam_curve_by_date(self, isolated_market_client: TestClient):
        target = "2026-09-14"
        res = isolated_market_client.get(f"/api/v1/market/dam/curve?date={target}")
        assert res.status_code == 200
        data = res.json()
        assert data["date"] == target
        assert data["count_hours"] == 24
        assert len(data["prices"]) == 24
        assert data["prices"][0]["hour"] == 0
        assert data["prices"][23]["hour"] == 23

    def test_get_dam_hourly_price(self, isolated_market_client: TestClient):
        ts = "2026-09-14T14:30:00Z"
        res = isolated_market_client.get(f"/api/v1/market/dam/hourly?timestamp={ts}")
        assert res.status_code == 200
        data = res.json()
        assert data["date"] == "2026-09-14"
        assert data["hour"] == 14
        assert data["price_eur_mwh"] > 0.0
        assert round(data["price_eur_mwh"] / 1000.0, 5) == data["price_eur_kwh"]

    def test_get_green_tariffs(self, isolated_market_client: TestClient):
        res = isolated_market_client.get("/api/v1/market/green-tariffs?month=2026-09")
        assert res.status_code == 200
        tariffs = res.json()
        assert len(tariffs) >= 2
        dei_tariffs = [t for t in tariffs if t["supplier_id"] == "dei"]
        assert len(dei_tariffs) >= 1
        assert dei_tariffs[0]["month"] == "2026-09"
        assert dei_tariffs[0]["p_base"] > 0.0

    def test_get_green_tariffs_with_supplier_filter(self, isolated_market_client: TestClient):
        res = isolated_market_client.get("/api/v1/market/green-tariffs?month=2026-09&supplier_id=dei")
        assert res.status_code == 200
        tariffs = res.json()
        assert len(tariffs) >= 1
        for t in tariffs:
            assert t["supplier_id"] == "dei"

    def test_post_refresh_green(self, isolated_market_client: TestClient):
        res = isolated_market_client.post("/api/v1/market/refresh-green?month=2026-09")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["count"] >= 2
        assert data["month"] == "2026-09"

    def test_post_fetch_dam(self, isolated_market_client: TestClient):
        target = "2026-09-20"
        res = isolated_market_client.post(f"/api/v1/market/fetch-dam?date={target}")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["hours_fetched"] == 24
        assert data["date"] == target

    def test_get_market_status(self, isolated_market_client: TestClient):
        res = isolated_market_client.get("/api/v1/market/status")
        assert res.status_code == 200
        status = res.json()
        assert status["online"] is True
        assert "dam_cached_dates_count" in status
        assert "green_active_month" in status
        assert status["dam_source_mode"] in ("live", "cached", "fallback_seed", "fallback_synthetic")
        assert status["green_source_mode"] in ("live", "cached", "fallback_seed", "fallback_synthetic")


class TestDynamicMarketRatePropagationInTelemetry:
    """Verify that dynamic wholesale market clearing prices directly update telemetry running costs."""

    def test_telemetry_cost_reflects_wholesale_dam_spot_rates(
        self, isolated_market_client: TestClient, valid_telemetry_dict: dict[str, Any]
    ):
        # 1. Register a facility with yellow / dynamic contract
        yellow_facility = {
            "facility_id": "dynamic-supermarket",
            "name": "Dynamic Supermarket",
            "facility_type": "supermarket",
            "contract_type": "Γ22",
            "tariff_color": "yellow",
            "contracted_kva": 50.0,
            "peak_threshold_kw": 30.0,
            "warning_threshold_ratio": 0.85,
            "low_pf_threshold": 0.85,
            "cooldown_seconds": 1800,
            "hysteresis_factor": 0.90,
            "debounce_samples": 3,
            "chat_id": 999555666,
        }
        # Seed facility
        market_svc: MarketPriceService = isolated_market_client.app.state.market_service
        market_svc.store.store_facility_config(yellow_facility)

        # 2. Scenario A: Ingest during LOW spot price window (50 €/MWh)
        target_date = "2026-09-18"
        low_prices = [
            DamHourlyPrice(
                date=target_date,
                hour=h,
                price_eur_mwh=50.0,
                price_eur_kwh=0.050,
                source="henex_live",
            )
            for h in range(24)
        ]
        market_svc.store.store_dam_hourly_prices(low_prices)
        market_svc.clear_l1_cache()

        payload_low = copy.deepcopy(valid_telemetry_dict)
        payload_low["facility_id"] = "dynamic-supermarket"
        payload_low["timestamp"] = f"{target_date}T14:00:00Z"

        res_low = isolated_market_client.post("/api/v1/telemetry", json=payload_low)
        assert res_low.status_code == 200
        cost_low = res_low.json()["running_cost_eur_per_h"]
        rate_low = res_low.json()["current_rate_eur_per_kwh"]

        # 3. Scenario B: Ingest during HIGH spot price window (250 €/MWh)
        target_date_high = "2026-09-19"
        high_prices = [
            DamHourlyPrice(
                date=target_date_high,
                hour=h,
                price_eur_mwh=250.0,
                price_eur_kwh=0.250,
                source="henex_live",
            )
            for h in range(24)
        ]
        market_svc.store.store_dam_hourly_prices(high_prices)
        market_svc.clear_l1_cache()

        payload_high = copy.deepcopy(valid_telemetry_dict)
        payload_high["facility_id"] = "dynamic-supermarket"
        payload_high["timestamp"] = f"{target_date_high}T14:00:00Z"

        res_high = isolated_market_client.post("/api/v1/telemetry", json=payload_high)
        assert res_high.status_code == 200
        cost_high = res_high.json()["running_cost_eur_per_h"]
        rate_high = res_high.json()["current_rate_eur_per_kwh"]

        # High wholesale price must significantly increase retail rate and running cost
        assert rate_high > rate_low
        assert cost_high > cost_low
        assert (cost_high - cost_low) > 3.0

    def test_offline_fallback_does_not_crash_telemetry_pipeline(
        self, isolated_market_client: TestClient, valid_telemetry_dict: dict[str, Any]
    ):
        # Configure market client to fail on all network requests
        market_svc: MarketPriceService = isolated_market_client.app.state.market_service
        market_svc.client = MockMarketClient(should_fail_dam=True, should_fail_green=True)
        market_svc.clear_l1_cache()

        # Telemetry ingestion for fresh un-cached date
        payload = copy.deepcopy(valid_telemetry_dict)
        payload["timestamp"] = "2026-11-20T10:00:00Z"

        res = isolated_market_client.post("/api/v1/telemetry", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["running_cost_eur_per_h"] > 0.0
        assert data["current_rate_eur_per_kwh"] > 0.0
