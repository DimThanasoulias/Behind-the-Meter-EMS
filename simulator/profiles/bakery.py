"""Commercial Bakery 24h load profile generator.

Simulates typical Greek commercial bakery operation:
- Night baseload (3-5 kW): refrigeration, display cases, standby power.
- Morning pre-heat & baking spikes (03:30-08:30, 35-45 kW): rotary deck ovens, proofers.
- Daytime prep (08:30-14:30, 12-16 kW): mixers, refrigeration, store open.
- Afternoon breach (14:30-16:30, 24-28 kW): afternoon batch baking prep in Greek peak window (14:00-17:00).
- Evening cooling (16:30-21:00, 6-10 kW): cooling down, cleaning, store closing.
"""

import math
from datetime import datetime

from simulator.profiles.base import LoadProfile


def get_commercial_bakery_power(hour_float: float) -> float:
    """Calculate commercial bakery power demand in kW for a given hour of day [0.0, 24.0).

    Args:
        hour_float: Fractional hour of the day (e.g. 6.5 for 06:30).

    Returns:
        Active power in kW.
    """
    h = hour_float % 24.0

    if 3.5 <= h < 5.0:
        # 03:30 - 05:00: Morning pre-heat (36.0 - 40.0 kW)
        return 37.0 + 3.0 * math.sin((h - 3.5) * math.pi / 1.5)
    elif 5.0 <= h < 8.5:
        # 05:00 - 08:30: Baking spikes (39.5 - 44.5 kW)
        return 42.0 + 2.5 * math.cos((h - 5.0) * 1.5)
    elif 8.5 <= h < 14.5:
        # 08:30 - 14:30: Daytime prep (12.0 - 16.0 kW)
        return 14.0 + 2.0 * math.sin((h - 8.5) * 0.8)
    elif 14.5 <= h < 16.5:
        # 14:30 - 16:30: Afternoon baking prep breach (24.0 - 28.0 kW, breaches 22 kW threshold)
        return 25.5 + 2.0 * math.sin((h - 14.5) * math.pi / 2.0)
    elif 16.5 <= h < 21.0:
        # 16:30 - 21:00: Evening cooling (6.5 - 9.5 kW)
        return 8.0 + 1.5 * math.cos((h - 16.5) * 0.7)
    else:
        # 21:00 - 03:30: Night baseload (3.5 - 4.5 kW)
        return 4.0 + 0.5 * math.sin(h * 0.8)


class BakeryProfile(LoadProfile):
    """Commercial Bakery profile implementation."""

    @property
    def name(self) -> str:
        return "bakery"

    @property
    def default_facility_id(self) -> str:
        return "bakery-central-athens"

    @property
    def default_peak_threshold_kw(self) -> float:
        return 22.0

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

        return get_commercial_bakery_power(hour_float)
