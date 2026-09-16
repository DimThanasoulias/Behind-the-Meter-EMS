"""Integration tests for the Real-Time Web Dashboard UI and metrics endpoints.

Verifies:
- GET /dashboard serves the responsive HTML5/Tailwind/Chart.js single-page application.
- GET /api/v1/dashboard/metrics/{facility_id} provides live 3-phase KPIs, running cost, daily spend, and timeline data.
- Load status classification correctly reflects NORMAL, WARNING, and BREACH states.
- POST /api/v1/dashboard/config/{facility_id} updates threshold kW and notification channel in the SQLite store and dispatcher.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from backend.database.sqlite_store import get_store
from backend.main import create_app


@pytest.fixture
def test_db_path(tmp_path) -> str:
    db_file = tmp_path / "test_dashboard.db"
    return str(db_file)


@pytest.fixture
def app_client(test_db_path: str) -> Generator[TestClient, None, None]:
    app = create_app(db_path=test_db_path)
    store = get_store(test_db_path)
    store.init_db()
    store.seed_default_facilities()

    # Pre-populate sample telemetry readings for bakery
    store.store_telemetry({
        "device_id": "esp32-bakery-01",
        "facility_id": "bakery-central-athens",
        "timestamp": datetime.now(timezone.utc),
        "total_active_power_kw": 18.2,
        "total_apparent_power_kva": 18.9,
        "system_power_factor": 0.96,
        "cumulative_energy_kwh": 312.4,
        "grid_frequency_hz": 50.0,
        "wifi_rssi_dbm": -58.0,
        "phases": {
            "L1": {"voltage_v": 231.2, "current_a": 26.3, "active_power_kw": 6.1},
            "L2": {"voltage_v": 229.8, "current_a": 26.0, "active_power_kw": 6.0},
            "L3": {"voltage_v": 230.5, "current_a": 26.4, "active_power_kw": 6.1},
        },
    })

    with TestClient(app) as client:
        yield client


def test_serve_dashboard_html(app_client: TestClient):
    response = app_client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html_content = response.text
    assert "<!DOCTYPE html>" in html_content
    assert "Commercial EMS" in html_content
    assert "loadTimelineChart" in html_content
    assert "facilitySelect" in html_content
    assert "settingsForm" in html_content
    assert "Chart.js" in html_content or "chart.umd.min.js" in html_content


def test_get_dashboard_metrics(app_client: TestClient):
    response = app_client.get("/api/v1/dashboard/metrics/bakery-central-athens")
    assert response.status_code == 200
    data = response.json()

    assert data["facility_id"] == "bakery-central-athens"
    assert data["total_active_power_kw"] == 18.2
    assert data["system_power_factor"] == 0.96
    assert data["peak_threshold_kw"] == 22.0
    assert "running_cost_eur_per_h" in data
    assert "cost_today_eur" in data
    assert "kwh_today" in data
    assert "active_zone_name" in data
    assert "timeline" in data
    assert len(data["timeline"]) >= 1
    assert data["phases"]["L1"]["voltage_v"] == 231.2


def test_load_status_classification(test_db_path: str):
    app = create_app(db_path=test_db_path)
    store = get_store(test_db_path)
    store.init_db()
    store.seed_default_facilities()

    with TestClient(app) as client:
        # 1. Normal state (< 85% of 22 kW = 18.7 kW)
        store.store_telemetry({
            "device_id": "esp32-01",
            "facility_id": "bakery-central-athens",
            "timestamp": datetime.now(timezone.utc),
            "total_active_power_kw": 15.0,
            "total_apparent_power_kva": 15.5,
            "system_power_factor": 0.97,
            "cumulative_energy_kwh": 350.0,
            "phases": {},
        })
        res_normal = client.get("/api/v1/dashboard/metrics/bakery-central-athens").json()
        assert res_normal["load_status"] == "NORMAL"

        # 2. Warning state (>= 18.7 kW, < 22 kW)
        store.store_telemetry({
            "device_id": "esp32-01",
            "facility_id": "bakery-central-athens",
            "timestamp": datetime.now(timezone.utc),
            "total_active_power_kw": 20.0,
            "total_apparent_power_kva": 20.5,
            "system_power_factor": 0.97,
            "cumulative_energy_kwh": 355.0,
            "phases": {},
        })
        res_warn = client.get("/api/v1/dashboard/metrics/bakery-central-athens").json()
        assert res_warn["load_status"] == "WARNING"

        # 3. Breach state (>= 22 kW)
        store.store_telemetry({
            "device_id": "esp32-01",
            "facility_id": "bakery-central-athens",
            "timestamp": datetime.now(timezone.utc),
            "total_active_power_kw": 24.5,
            "total_apparent_power_kva": 25.0,
            "system_power_factor": 0.98,
            "cumulative_energy_kwh": 360.0,
            "phases": {},
        })
        res_breach = client.get("/api/v1/dashboard/metrics/bakery-central-athens").json()
        assert res_breach["load_status"] == "BREACH"


def test_update_dashboard_config(app_client: TestClient):
    update_payload = {
        "peak_threshold_kw": 28.5,
        "notification_channel": "both",
        "chat_id": 999888777,
        "viber_receiver_id": "viber_rec_test_1",
    }
    response = app_client.post(
        "/api/v1/dashboard/config/bakery-central-athens",
        json=update_payload,
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["config"]["peak_threshold_kw"] == 28.5
    assert res_data["config"]["notification_channel"] == "both"

    # Query metrics and verify update reflected immediately
    metrics_res = app_client.get("/api/v1/dashboard/metrics/bakery-central-athens").json()
    assert metrics_res["peak_threshold_kw"] == 28.5
    assert metrics_res["notification_channel"] == "both"
    assert metrics_res["chat_id"] == 999888777
    assert metrics_res["viber_receiver_id"] == "viber_rec_test_1"


def test_update_dashboard_config_not_found(app_client: TestClient):
    response = app_client.post(
        "/api/v1/dashboard/config/unknown-facility-id",
        json={"peak_threshold_kw": 30.0},
    )
    assert response.status_code == 404
