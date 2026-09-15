"""Base classes and interfaces for commercial load profiles."""

from abc import ABC, abstractmethod
from datetime import datetime


class LoadProfile(ABC):
    """Abstract base class representing a commercial electrical load profile."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the profile (e.g., 'bakery', 'cold_storage', 'boutique_hotel')."""
        ...

    @property
    @abstractmethod
    def default_facility_id(self) -> str:
        """Default facility identifier for telemetry."""
        ...

    @property
    @abstractmethod
    def default_peak_threshold_kw(self) -> float:
        """Default peak threshold in kW for Greek commercial peak windows."""
        ...

    @abstractmethod
    def get_power_kw(
        self,
        dt: datetime | None = None,
        elapsed_seconds: float = 0.0,
        **kwargs,
    ) -> float:
        """Calculate the active power demand in kW.

        Args:
            dt: Optional datetime representing the point in time.
            elapsed_seconds: Elapsed seconds since the simulation started.
            **kwargs: Profile-specific options (e.g., door_open).

        Returns:
            Active load power in kW.
        """
        ...
