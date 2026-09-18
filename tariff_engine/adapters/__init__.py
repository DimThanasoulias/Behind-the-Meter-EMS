"""
European Market Adapters Package (Requirement R4 / Features F5-F7).

Provides pluggable market adapters for:
- Greece (GR / HEnEx / RAAEY / Law 5068/2023)
- Germany (DE-LU / EPEX Spot / BNetzA / §14a EnWG)
- Spain (ES / OMIE / CNMC / PVPC Tarifa 2.0TD)
"""

from __future__ import annotations

from .base import (
    BaseMarketAdapter,
    DemandCapacityLimit,
    HourlyPriceVector,
    MarketMetadata,
)
from .german import (
    GermanFacilityContract,
    GermanMarketAdapter,
)
from .greek import (
    GreekMarketAdapter,
)
from .registry import (
    MarketAdapterRegistry,
    get_market_adapter,
    register_default_adapters,
)
from .spanish import (
    SpanishFacilityContract,
    SpanishMarketAdapter,
)

__all__ = [
    "BaseMarketAdapter",
    "DemandCapacityLimit",
    "GermanFacilityContract",
    "GermanMarketAdapter",
    "GreekMarketAdapter",
    "HourlyPriceVector",
    "MarketAdapterRegistry",
    "MarketMetadata",
    "SpanishFacilityContract",
    "SpanishMarketAdapter",
    "get_market_adapter",
    "register_default_adapters",
]
