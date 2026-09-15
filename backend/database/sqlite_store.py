"""SQLite time-series storage engine for Greek Commercial EMS backend.

Implements high-throughput time-series persistence with:
- PRAGMA journal_mode=WAL and PRAGMA synchronous=NORMAL
- PRAGMA foreign_keys=ON and PRAGMA busy_timeout=5000
- Tables: telemetry_readings, facility_configs, cost_aggregates
- Composite indices on (facility_id, timestamp) and (facility_id, date)
- Full CRUD and aggregation queries for telemetry, facility configurations, and daily costs
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Generator

from backend.config import settings
from backend.models.telemetry import TelemetryPayload

logger = logging.getLogger(__name__)

# Default Greek commercial facility configurations
DEFAULT_FACILITIES = [
    {
        "facility_id": "bakery-central-athens",
        "name": "Bakery Central Athens",
        "facility_type": "bakery",
        "contract_type": "Γ22",
        "tariff_color": "green",
        "contracted_kva": 35.0,
        "peak_threshold_kw": 22.0,
        "warning_threshold_ratio": 0.85,
        "low_pf_threshold": 0.85,
        "cooldown_seconds": 1800,
        "hysteresis_factor": 0.90,
        "debounce_samples": 3,
        "chat_id": 999111222,
    },
    {
        "facility_id": "cold-storage-piraeus",
        "name": "Cold Storage Piraeus",
        "facility_type": "cold_storage",
        "contract_type": "Γ22",
        "tariff_color": "green",
        "contracted_kva": 50.0,
        "peak_threshold_kw": 30.0,
        "warning_threshold_ratio": 0.85,
        "low_pf_threshold": 0.85,
        "cooldown_seconds": 1800,
        "hysteresis_factor": 0.90,
        "debounce_samples": 3,
        "chat_id": 999222333,
    },
    {
        "facility_id": "hotel-plaka-boutique",
        "name": "Hotel Plaka Boutique",
        "facility_type": "boutique_hotel",
        "contract_type": "Γ21",
        "tariff_color": "green",
        "contracted_kva": 40.0,
        "peak_threshold_kw": 25.0,
        "warning_threshold_ratio": 0.85,
        "low_pf_threshold": 0.85,
        "cooldown_seconds": 1800,
        "hysteresis_factor": 0.90,
        "debounce_samples": 3,
        "chat_id": 999333444,
    },
]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS facility_configs (
    facility_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    facility_type TEXT NOT NULL,
    contract_type TEXT NOT NULL,
    tariff_color TEXT NOT NULL,
    contracted_kva REAL NOT NULL DEFAULT 35.0,
    peak_threshold_kw REAL NOT NULL DEFAULT 22.0,
    warning_threshold_ratio REAL NOT NULL DEFAULT 0.85,
    low_pf_threshold REAL NOT NULL DEFAULT 0.85,
    cooldown_seconds INTEGER NOT NULL DEFAULT 1800,
    hysteresis_factor REAL NOT NULL DEFAULT 0.90,
    debounce_samples INTEGER NOT NULL DEFAULT 3,
    chat_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

CREATE TABLE IF NOT EXISTS telemetry_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    total_active_power_kw REAL NOT NULL,
    total_apparent_power_kva REAL NOT NULL,
    system_power_factor REAL NOT NULL,
    cumulative_energy_kwh REAL NOT NULL,
    grid_frequency_hz REAL NOT NULL DEFAULT 50.0,
    wifi_rssi_dbm REAL NOT NULL DEFAULT -60.0,
    phases_json TEXT NOT NULL,
    running_cost_eur_per_h REAL DEFAULT 0.0,
    current_rate_eur_per_kwh REAL DEFAULT 0.0,
    incremental_cost_eur REAL DEFAULT 0.0,
    is_peak_window INTEGER DEFAULT 0,
    is_excess_breach INTEGER DEFAULT 0,
    projected_penalty_eur REAL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    FOREIGN KEY (facility_id) REFERENCES facility_configs(facility_id)
);

CREATE TABLE IF NOT EXISTS cost_aggregates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id TEXT NOT NULL,
    date TEXT NOT NULL,
    total_kwh REAL NOT NULL DEFAULT 0.0,
    total_cost_eur REAL NOT NULL DEFAULT 0.0,
    peak_kwh REAL NOT NULL DEFAULT 0.0,
    offpeak_kwh REAL NOT NULL DEFAULT 0.0,
    peak_surcharges_eur REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    UNIQUE(facility_id, date),
    FOREIGN KEY (facility_id) REFERENCES facility_configs(facility_id)
);

CREATE INDEX IF NOT EXISTS idx_telemetry_facility_timestamp
ON telemetry_readings (facility_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_cost_aggregates_facility_date
ON cost_aggregates (facility_id, date);
"""


class SQLiteStore:
    """Thread-safe SQLite storage engine with WAL mode and time-series query capabilities."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = str(db_path or settings.SQLITE_DB_PATH)
        self._is_memory = (self.db_path == ":memory:" or "mode=memory" in self.db_path)
        self._lock = threading.Lock()
        self._memory_conn: sqlite3.Connection | None = None

        if self._is_memory:
            self._memory_conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=15.0)
            self._memory_conn.row_factory = sqlite3.Row
            self._apply_pragmas(self._memory_conn)
            self._create_schema(self._memory_conn)
        else:
            # Ensure target directory exists for file-based database
            if not self.db_path.startswith("file:"):
                dir_name = os.path.dirname(os.path.abspath(self.db_path))
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
            with self.connection() as conn:
                self._create_schema(conn)

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        """Apply required WAL and concurrency pragmas."""
        if not self._is_memory:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=5000;")

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        """Initialize database schema tables and indices."""
        conn.executescript(SCHEMA_SQL)
        conn.commit()

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a contextual SQLite connection."""
        if self._is_memory and self._memory_conn:
            with self._lock:
                try:
                    yield self._memory_conn
                    self._memory_conn.commit()
                except Exception:
                    self._memory_conn.rollback()
                    raise
        else:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=15.0)
            conn.row_factory = sqlite3.Row
            self._apply_pragmas(conn)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def init_db(self) -> None:
        """Re-verify schema initialization."""
        with self.connection() as conn:
            self._create_schema(conn)

    def store_facility_config(self, config: dict[str, Any] | Any) -> None:
        """Store or update facility configuration."""
        if hasattr(config, "model_dump"):
            data = config.model_dump()
        elif isinstance(config, dict):
            data = dict(config)
        else:
            data = {k: getattr(config, k) for k in dir(config) if not k.startswith("_")}

        facility_id = str(data["facility_id"])
        name = str(data.get("name", data.get("facility_name", facility_id)))
        facility_type = str(data.get("facility_type", "bakery"))
        contract_type = str(data.get("contract_type", data.get("contract_code", "Γ22")))
        tariff_color = str(data.get("tariff_color", data.get("color", "green")))
        contracted_kva = float(data.get("contracted_kva", data.get("contracted_capacity_kva", 35.0)))
        peak_threshold_kw = float(data.get("peak_threshold_kw", 22.0))
        warning_threshold_ratio = float(data.get("warning_threshold_ratio", 0.85))
        low_pf_threshold = float(data.get("low_pf_threshold", 0.85))
        cooldown_seconds = int(data.get("cooldown_seconds", 1800))
        hysteresis_factor = float(data.get("hysteresis_factor", 0.90))
        debounce_samples = int(data.get("debounce_samples", 3))
        chat_id = data.get("chat_id", data.get("telegram_chat_id"))

        query = """
        INSERT INTO facility_configs (
            facility_id, name, facility_type, contract_type, tariff_color,
            contracted_kva, peak_threshold_kw, warning_threshold_ratio,
            low_pf_threshold, cooldown_seconds, hysteresis_factor,
            debounce_samples, chat_id, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'utc'))
        ON CONFLICT(facility_id) DO UPDATE SET
            name = excluded.name,
            facility_type = excluded.facility_type,
            contract_type = excluded.contract_type,
            tariff_color = excluded.tariff_color,
            contracted_kva = excluded.contracted_kva,
            peak_threshold_kw = excluded.peak_threshold_kw,
            warning_threshold_ratio = excluded.warning_threshold_ratio,
            low_pf_threshold = excluded.low_pf_threshold,
            cooldown_seconds = excluded.cooldown_seconds,
            hysteresis_factor = excluded.hysteresis_factor,
            debounce_samples = excluded.debounce_samples,
            chat_id = excluded.chat_id,
            updated_at = datetime('now', 'utc');
        """
        with self.connection() as conn:
            conn.execute(
                query,
                (
                    facility_id,
                    name,
                    facility_type,
                    contract_type,
                    tariff_color,
                    contracted_kva,
                    peak_threshold_kw,
                    warning_threshold_ratio,
                    low_pf_threshold,
                    cooldown_seconds,
                    hysteresis_factor,
                    debounce_samples,
                    chat_id,
                ),
            )

    def get_facility_config(self, facility_id: str) -> dict[str, Any] | None:
        """Fetch facility configuration by ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM facility_configs WHERE facility_id = ?;",
                (facility_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def list_facility_configs(self) -> list[dict[str, Any]]:
        """List all configured commercial facilities."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM facility_configs ORDER BY facility_id ASC;"
            ).fetchall()
            return [dict(r) for r in rows]

    def seed_default_facilities(self) -> None:
        """Ensure standard commercial facilities (Bakery, Cold Storage, Hotel) are seeded."""
        for fac in DEFAULT_FACILITIES:
            self.store_facility_config(fac)

    def store_telemetry(
        self,
        payload: TelemetryPayload | dict[str, Any],
        cost_result: Any | None = None,
    ) -> int:
        """Store a telemetry reading and update daily cost aggregates.

        Returns:
            The inserted telemetry reading ID.
        """
        if isinstance(payload, TelemetryPayload):
            device_id = payload.device_id
            facility_id = payload.facility_id
            ts = payload.timestamp
            p_tot = float(payload.total_active_power_kw)
            s_tot = float(payload.total_apparent_power_kva)
            pf = float(payload.system_power_factor)
            kwh = float(payload.cumulative_energy_kwh)
            freq = float(payload.grid_frequency_hz)
            rssi = float(payload.wifi_rssi_dbm)
            # Serialize phases
            phases_dict = {
                k: v.model_dump() if hasattr(v, "model_dump") else v
                for k, v in payload.phases.items()
            }
        else:
            device_id = str(payload["device_id"])
            facility_id = str(payload["facility_id"])
            ts = payload["timestamp"]
            p_tot = float(payload["total_active_power_kw"])
            s_tot = float(payload["total_apparent_power_kva"])
            pf = float(payload["system_power_factor"])
            kwh = float(payload["cumulative_energy_kwh"])
            freq = float(payload.get("grid_frequency_hz", 50.0))
            rssi = float(payload.get("wifi_rssi_dbm", -60.0))
            phases_dict = payload.get("phases", {})

        # Ensure timestamp is formatted consistently as ISO 8601 string
        if isinstance(ts, datetime):
            ts_str = ts.astimezone(timezone.utc).isoformat()
            reading_date = ts.date()
        else:
            ts_str = str(ts)
            try:
                reading_date = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).date()
            except Exception:
                reading_date = datetime.now(timezone.utc).date()

        phases_json = json.dumps(phases_dict)

        # Cost metrics extraction
        cost_h = getattr(cost_result, "running_cost_eur_per_h", 0.0) if cost_result else 0.0
        unit_rate = getattr(cost_result, "current_rate_eur_per_kwh", 0.0) if cost_result else 0.0
        incremental_cost = getattr(cost_result, "incremental_cost_eur", 0.0) if cost_result else 0.0
        is_peak = 1 if getattr(cost_result, "is_peak_window", False) else 0
        is_excess = 1 if getattr(cost_result, "is_excess_breach", False) else 0
        projected_penalty = getattr(cost_result, "projected_excess_penalty_eur", 0.0) if cost_result else 0.0

        with self.connection() as conn:
            # Auto-provision facility if not yet recorded to prevent foreign key violation
            fac_exists = conn.execute(
                "SELECT 1 FROM facility_configs WHERE facility_id = ?;", (facility_id,)
            ).fetchone()
            if not fac_exists:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO facility_configs (
                        facility_id, name, facility_type, contract_type, tariff_color,
                        contracted_kva, peak_threshold_kw
                    ) VALUES (?, ?, 'commercial', 'Γ22', 'green', 35.0, 22.0);
                    """,
                    (facility_id, facility_id),
                )

            # Insert reading
            cursor = conn.execute(
                """
                INSERT INTO telemetry_readings (
                    device_id, facility_id, timestamp, total_active_power_kw,
                    total_apparent_power_kva, system_power_factor, cumulative_energy_kwh,
                    grid_frequency_hz, wifi_rssi_dbm, phases_json, running_cost_eur_per_h,
                    current_rate_eur_per_kwh, incremental_cost_eur, is_peak_window,
                    is_excess_breach, projected_penalty_eur
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    device_id,
                    facility_id,
                    ts_str,
                    p_tot,
                    s_tot,
                    pf,
                    kwh,
                    freq,
                    rssi,
                    phases_json,
                    cost_h,
                    unit_rate,
                    incremental_cost,
                    is_peak,
                    is_excess,
                    projected_penalty,
                ),
            )
            reading_id = cursor.lastrowid

            # Calculate energy delta for daily aggregate
            # Query the previous reading for this facility
            prev_reading = conn.execute(
                """
                SELECT cumulative_energy_kwh FROM telemetry_readings
                WHERE facility_id = ? AND id < ?
                ORDER BY id DESC LIMIT 1;
                """,
                (facility_id, reading_id),
            ).fetchone()

            if prev_reading and prev_reading["cumulative_energy_kwh"] is not None:
                delta_kwh = max(0.0, kwh - prev_reading["cumulative_energy_kwh"])
            else:
                delta_kwh = 0.0

            peak_kwh = delta_kwh if is_peak else 0.0
            offpeak_kwh = delta_kwh if not is_peak else 0.0
            penalty_contrib = projected_penalty if is_excess else 0.0
            date_str = reading_date.isoformat()

            conn.execute(
                """
                INSERT INTO cost_aggregates (
                    facility_id, date, total_kwh, total_cost_eur, peak_kwh,
                    offpeak_kwh, peak_surcharges_eur, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'utc'))
                ON CONFLICT(facility_id, date) DO UPDATE SET
                    total_kwh = total_kwh + excluded.total_kwh,
                    total_cost_eur = total_cost_eur + excluded.total_cost_eur,
                    peak_kwh = peak_kwh + excluded.peak_kwh,
                    offpeak_kwh = offpeak_kwh + excluded.offpeak_kwh,
                    peak_surcharges_eur = peak_surcharges_eur + excluded.peak_surcharges_eur,
                    updated_at = datetime('now', 'utc');
                """,
                (
                    facility_id,
                    date_str,
                    delta_kwh,
                    incremental_cost,
                    peak_kwh,
                    offpeak_kwh,
                    penalty_contrib,
                ),
            )

            return reading_id

    def get_latest_telemetry(self, facility_id: str) -> dict[str, Any] | None:
        """Fetch the most recent telemetry record for a facility."""
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM telemetry_readings
                WHERE facility_id = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT 1;
                """,
                (facility_id,),
            ).fetchone()
            if row is None:
                return None

            result = dict(row)
            try:
                result["phases"] = json.loads(result.pop("phases_json", "{}"))
            except Exception:
                result["phases"] = {}
            return result

    def get_telemetry_history(
        self,
        facility_id: str,
        start_time: datetime | str | None = None,
        end_time: datetime | str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Retrieve historical telemetry records within an optional time range."""
        start_str = start_time.isoformat() if isinstance(start_time, datetime) else start_time
        end_str = end_time.isoformat() if isinstance(end_time, datetime) else end_time

        query = """
        SELECT * FROM telemetry_readings
        WHERE facility_id = ?
          AND (? IS NULL OR timestamp >= ?)
          AND (? IS NULL OR timestamp <= ?)
        ORDER BY timestamp DESC, id DESC
        LIMIT ?;
        """
        with self.connection() as conn:
            rows = conn.execute(
                query, (facility_id, start_str, start_str, end_str, end_str, limit)
            ).fetchall()

            history = []
            for row in rows:
                item = dict(row)
                try:
                    item["phases"] = json.loads(item.pop("phases_json", "{}"))
                except Exception:
                    item["phases"] = {}
                history.append(item)
            return history

    def get_daily_summary(
        self,
        facility_id: str,
        target_date: date | str | None = None,
    ) -> dict[str, Any]:
        """Get accumulated daily consumption, spend, and peak surcharge breakdown."""
        if target_date is None:
            date_str = datetime.now(timezone.utc).date().isoformat()
        elif isinstance(target_date, date):
            date_str = target_date.isoformat()
        else:
            date_str = str(target_date)

        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM cost_aggregates
                WHERE facility_id = ? AND date = ?;
                """,
                (facility_id, date_str),
            ).fetchone()

            if row:
                tot_kwh = float(row["total_kwh"])
                tot_cost = float(row["total_cost_eur"])
                avg_rate = round(tot_cost / tot_kwh, 4) if tot_kwh > 0 else 0.0
                return {
                    "facility_id": facility_id,
                    "date": date_str,
                    "total_kwh": round(tot_kwh, 3),
                    "total_spend_eur": round(tot_cost, 2),
                    "peak_kwh": round(float(row["peak_kwh"]), 3),
                    "offpeak_kwh": round(float(row["offpeak_kwh"]), 3),
                    "peak_surcharges_eur": round(float(row["peak_surcharges_eur"]), 2),
                    "average_rate_eur_per_kwh": avg_rate,
                }

            # Fallback computation from raw telemetry readings if no cost aggregate row exists
            fallback = conn.execute(
                """
                SELECT
                    COUNT(*) as count,
                    COALESCE(SUM(incremental_cost_eur), 0.0) as sum_cost,
                    COALESCE(SUM(CASE WHEN is_peak_window = 1 THEN incremental_cost_eur ELSE 0.0 END), 0.0) as peak_cost,
                    COALESCE(SUM(CASE WHEN is_excess_breach = 1 THEN projected_penalty_eur ELSE 0.0 END), 0.0) as surcharges,
                    COALESCE(MIN(cumulative_energy_kwh), 0.0) as min_kwh,
                    COALESCE(MAX(cumulative_energy_kwh), 0.0) as max_kwh
                FROM telemetry_readings
                WHERE facility_id = ? AND date(timestamp) = ?;
                """,
                (facility_id, date_str),
            ).fetchone()

            if fallback and fallback["count"] > 0:
                kwh_delta = max(0.0, fallback["max_kwh"] - fallback["min_kwh"])
                sum_cost = float(fallback["sum_cost"])
                avg_rate = round(sum_cost / kwh_delta, 4) if kwh_delta > 0 else 0.0
                return {
                    "facility_id": facility_id,
                    "date": date_str,
                    "total_kwh": round(kwh_delta, 3),
                    "total_spend_eur": round(sum_cost, 2),
                    "peak_kwh": round(kwh_delta, 3),
                    "offpeak_kwh": 0.0,
                    "peak_surcharges_eur": round(float(fallback["surcharges"]), 2),
                    "average_rate_eur_per_kwh": avg_rate,
                }

            # If no data at all for this date
            return {
                "facility_id": facility_id,
                "date": date_str,
                "total_kwh": 0.0,
                "total_spend_eur": 0.0,
                "peak_kwh": 0.0,
                "offpeak_kwh": 0.0,
                "peak_surcharges_eur": 0.0,
                "average_rate_eur_per_kwh": 0.0,
            }


# Global store instance registry
_stores: dict[str, SQLiteStore] = {}
_stores_lock = threading.Lock()


def get_store(db_path: str | Path | None = None) -> SQLiteStore:
    """Retrieve or create a SQLiteStore instance for the given database path."""
    key = str(db_path or settings.SQLITE_DB_PATH)
    with _stores_lock:
        if key not in _stores:
            _stores[key] = SQLiteStore(key)
        return _stores[key]


# Top-level functional wrappers matching requirement interface
def init_db(db_path: str | Path | None = None) -> None:
    """Initialize database schema and pragmas."""
    store = get_store(db_path)
    store.init_db()


def store_telemetry(
    payload: TelemetryPayload | dict[str, Any],
    cost_result: Any | None = None,
    db_path: str | Path | None = None,
) -> int:
    """Store telemetry reading and update daily aggregates."""
    return get_store(db_path).store_telemetry(payload, cost_result)


def get_latest_telemetry(
    facility_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Fetch latest telemetry reading for facility."""
    return get_store(db_path).get_latest_telemetry(facility_id)


def get_telemetry_history(
    facility_id: str,
    start_time: datetime | str | None = None,
    end_time: datetime | str | None = None,
    limit: int = 100,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Fetch telemetry history for facility."""
    return get_store(db_path).get_telemetry_history(facility_id, start_time, end_time, limit)


def get_daily_summary(
    facility_id: str,
    target_date: date | str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Fetch daily consumption and spend summary."""
    return get_store(db_path).get_daily_summary(facility_id, target_date)


def store_facility_config(
    config: dict[str, Any] | Any,
    db_path: str | Path | None = None,
) -> None:
    """Store or update facility configuration."""
    get_store(db_path).store_facility_config(config)


def get_facility_config(
    facility_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Fetch facility configuration."""
    return get_store(db_path).get_facility_config(facility_id)


def list_facility_configs(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """List all facility configurations."""
    return get_store(db_path).list_facility_configs()


def seed_default_facilities(db_path: str | Path | None = None) -> None:
    """Seed default facilities into database."""
    get_store(db_path).seed_default_facilities()
