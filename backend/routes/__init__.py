"""Routes package for Greek Commercial EMS backend."""

from backend.routes.facilities import router as facilities_router
from backend.routes.telemetry import (
    AlertDispatcher,
    get_alert_dispatcher,
    get_database_store,
    router as telemetry_router,
)

__all__ = [
    "AlertDispatcher",
    "facilities_router",
    "get_alert_dispatcher",
    "get_database_store",
    "telemetry_router",
]
