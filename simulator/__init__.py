"""Commercial Telemetry Simulator for Behind-the-Meter EMS."""

from typing import Any

from simulator.generator import TelemetryGenerator
from simulator.profiles import (
    AVAILABLE_PROFILES,
    PROFILE_REGISTRY,
    BakeryProfile,
    BoutiqueHotelProfile,
    ColdStorageProfile,
    LoadProfile,
    get_boutique_hotel_power,
    get_cold_storage_power,
    get_commercial_bakery_power,
    get_profile,
)


def __getattr__(name: str) -> Any:
    """Lazy import for CLI functions to avoid eager circular imports."""
    if name == "main":
        from simulator.cli import main
        return main
    if name == "run_simulation":
        from simulator.cli import run_simulation
        return run_simulation
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "AVAILABLE_PROFILES",
    "PROFILE_REGISTRY",
    "BakeryProfile",
    "BoutiqueHotelProfile",
    "ColdStorageProfile",
    "LoadProfile",
    "TelemetryGenerator",
    "get_boutique_hotel_power",
    "get_cold_storage_power",
    "get_commercial_bakery_power",
    "get_profile",
    "main",
    "run_simulation",
]
