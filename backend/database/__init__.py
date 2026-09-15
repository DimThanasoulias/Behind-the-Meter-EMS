"""Database package for Greek Commercial EMS backend."""

from backend.database.sqlite_store import (
    DEFAULT_FACILITIES,
    SQLiteStore,
    get_daily_summary,
    get_facility_config,
    get_latest_telemetry,
    get_store,
    get_telemetry_history,
    init_db,
    list_facility_configs,
    seed_default_facilities,
    store_facility_config,
    store_telemetry,
)

__all__ = [
    "DEFAULT_FACILITIES",
    "SQLiteStore",
    "get_daily_summary",
    "get_facility_config",
    "get_latest_telemetry",
    "get_store",
    "get_telemetry_history",
    "init_db",
    "list_facility_configs",
    "seed_default_facilities",
    "store_facility_config",
    "store_telemetry",
]
