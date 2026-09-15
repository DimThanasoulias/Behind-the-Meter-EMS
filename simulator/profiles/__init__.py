"""Commercial load profiles for Greek Behind-the-Meter EMS simulation."""

from simulator.profiles.bakery import BakeryProfile, get_commercial_bakery_power
from simulator.profiles.base import LoadProfile
from simulator.profiles.boutique_hotel import (
    BoutiqueHotelProfile,
    get_boutique_hotel_power,
)
from simulator.profiles.cold_storage import ColdStorageProfile, get_cold_storage_power

PROFILE_REGISTRY: dict[str, type[LoadProfile]] = {
    "bakery": BakeryProfile,
    "commercial_bakery": BakeryProfile,
    "cold_storage": ColdStorageProfile,
    "refrigeration": ColdStorageProfile,
    "boutique_hotel": BoutiqueHotelProfile,
    "hotel": BoutiqueHotelProfile,
}

AVAILABLE_PROFILES = sorted(set(PROFILE_REGISTRY.keys()))


def get_profile(name: str, **kwargs) -> LoadProfile:
    """Instantiate a load profile by name.

    Args:
        name: Profile name ('bakery', 'cold_storage', 'boutique_hotel', etc.).
        **kwargs: Optional configuration parameters passed to profile constructor.

    Returns:
        Instance of LoadProfile.

    Raises:
        ValueError: If profile name is not recognized.
    """
    key = name.strip().lower().replace("-", "_")
    if key not in PROFILE_REGISTRY:
        available = sorted(set(PROFILE_REGISTRY.keys()))
        raise ValueError(f"Unknown profile '{name}'. Available profiles: {available}")

    profile_cls = PROFILE_REGISTRY[key]
    return profile_cls(**kwargs)


__all__ = [
    "AVAILABLE_PROFILES",
    "PROFILE_REGISTRY",
    "BakeryProfile",
    "BoutiqueHotelProfile",
    "ColdStorageProfile",
    "LoadProfile",
    "get_boutique_hotel_power",
    "get_cold_storage_power",
    "get_commercial_bakery_power",
    "get_profile",
]
