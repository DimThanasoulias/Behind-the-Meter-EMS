"""Boutique Hotel 24h load profile generator.

Simulates Greek boutique hotel energy demand:
- Morning breakfast (07:00-10:00, 20-25 kW): kitchen prep, buffet warmers, espresso machines, laundry.
- Daytime housekeeping & pool pumps (10:00-14:00, 13-17 kW).
- Afternoon check-in & VRV HVAC peak (14:00-17:30, 28-35 kW): guest arrivals, variable refrigerant volume cooling.
- Evening lounge & transition (17:30-19:30, 18-20 kW).
- Evening dinner (19:30-23:00, 18-24 kW): restaurant, kitchen, lighting, bar.
- Night baseload (23:00-07:00, 8-12 kW): standby HVAC, emergency lighting, reception, refrigeration.
"""

import math
from datetime import datetime

from simulator.profiles.base import LoadProfile


def get_boutique_hotel_power(hour_float: float) -> float:
    """Calculate boutique hotel power demand in kW for a given hour of day [0.0, 24.0).

    Args:
        hour_float: Fractional hour of the day (e.g. 15.5 for 15:30).

    Returns:
        Active power in kW.
    """
    h = hour_float % 24.0

    if 7.0 <= h < 10.0:
        # Morning breakfast & laundry: 20.0 - 25.0 kW
        return 22.5 + 2.0 * math.sin((h - 7.0) * math.pi / 3.0)
    elif 10.0 <= h < 14.0:
        # Daytime housekeeping, laundry, pool pumps: 13.0 - 17.0 kW
        return 15.0 + 2.0 * math.sin((h - 10.0) * 0.8)
    elif 14.0 <= h < 17.5:
        # Afternoon check-in & VRV HVAC peak: 28.0 - 35.0 kW
        return 31.5 + 3.0 * math.sin((h - 14.0) * math.pi / 3.5)
    elif 17.5 <= h < 19.5:
        # Evening transition / lounge: 18.0 - 20.0 kW
        return 18.0 + 2.0 * math.sin((h - 17.5) * math.pi / 2.0)
    elif 19.5 <= h < 23.0:
        # Evening dinner & restaurant: 18.0 - 24.0 kW
        return 21.0 + 2.5 * math.sin((h - 19.5) * math.pi / 3.5)
    else:
        # Night baseload: 8.0 - 12.0 kW
        return 10.0 + 1.0 * math.sin(h * 0.5)


class BoutiqueHotelProfile(LoadProfile):
    """Boutique Hotel commercial profile implementation."""

    @property
    def name(self) -> str:
        return "boutique_hotel"

    @property
    def default_facility_id(self) -> str:
        return "hotel-santorini-boutique"

    @property
    def default_peak_threshold_kw(self) -> float:
        return 30.0

    def get_power_kw(
        self,
        dt: datetime | None = None,
        elapsed_seconds: float = 0.0,
        **kwargs,
    ) -> float:
        """Calculate power for the given datetime or elapsed seconds."""
        if dt is not None:
            hour_float = dt.hour + dt.minute / 60.0 + dt.second / 3600.0 + dt.microsecond / 3600000000.0
        else:
            hour_float = (elapsed_seconds / 3600.0) % 24.0

        return get_boutique_hotel_power(hour_float)
