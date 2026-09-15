"""Cold Storage Facility refrigeration load profile generator.

Simulates commercial cold storage thermodynamic cycling:
- Compressor ON (15-20 min, 25-32 kW): refrigerant compression and evaporator pull-down.
- Compressor OFF (15-20 min, 4-6 kW): evaporator fans and controls only.
- Dock door disturbances (surge to 34-38 kW): warm ambient air infiltration during loading.
"""

import math
from datetime import datetime

from simulator.profiles.base import LoadProfile


def get_cold_storage_power(
    minute_float: float,
    door_open: bool = False,
    on_minutes: float = 18.0,
    off_minutes: float = 18.0,
) -> float:
    """Calculate cold storage power demand in kW.

    Args:
        minute_float: Elapsed or clock minute.
        door_open: Whether dock doors are open (causing thermal disturbance surge).
        on_minutes: Duration of compressor pull-down phase (15-20 min).
        off_minutes: Duration of compressor idle phase (15-20 min).

    Returns:
        Active power in kW.
    """
    if door_open:
        # Dock door disturbance surge (34-38 kW, nominal 34.5 kW)
        return 34.5

    cycle_period = on_minutes + off_minutes
    minute_in_cycle = minute_float % cycle_period

    if minute_in_cycle < on_minutes:
        # Compressor ON phase: 25.0 - 32.0 kW pull-down
        phase_on = minute_in_cycle / on_minutes
        return 28.0 + 3.5 * math.sin(phase_on * math.pi)
    else:
        # Compressor OFF phase: 4.0 - 6.0 kW baseload fans/controls
        phase_off = (minute_in_cycle - on_minutes) / off_minutes
        return 5.0 + 0.8 * math.cos(phase_off * 2.0 * math.pi)


class ColdStorageProfile(LoadProfile):
    """Commercial Cold Storage refrigeration profile implementation."""

    def __init__(
        self,
        cycle_on_minutes: float = 18.0,
        cycle_off_minutes: float = 18.0,
        simulate_door_openings: bool = False,
    ):
        self.cycle_on_minutes = cycle_on_minutes
        self.cycle_off_minutes = cycle_off_minutes
        self.simulate_door_openings = simulate_door_openings
        self._manual_door_open: bool = False

    @property
    def name(self) -> str:
        return "cold_storage"

    @property
    def default_facility_id(self) -> str:
        return "cold-storage-piraeus"

    @property
    def default_peak_threshold_kw(self) -> float:
        return 25.0

    def set_door_open(self, is_open: bool) -> None:
        """Manually trigger or clear a dock door disturbance."""
        self._manual_door_open = is_open

    def get_power_kw(
        self,
        dt: datetime | None = None,
        elapsed_seconds: float = 0.0,
        door_open: bool | None = None,
        **kwargs,
    ) -> float:
        """Calculate power for the given datetime or elapsed seconds."""
        if door_open is None:
            door_open = self._manual_door_open

        # If simulate_door_openings is True, trigger during daytime dock activity (10:00 - 14:00, 10-15 min)
        if (
            not door_open
            and self.simulate_door_openings
            and dt is not None
            and 10 <= dt.hour < 14
            and 10 <= dt.minute < 15
        ):
            door_open = True

        minute_val = (elapsed_seconds / 60.0) if dt is None else (dt.hour * 60.0 + dt.minute + dt.second / 60.0)

        return get_cold_storage_power(
            minute_float=minute_val,
            door_open=door_open,
            on_minutes=self.cycle_on_minutes,
            off_minutes=self.cycle_off_minutes,
        )
