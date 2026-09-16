"""Market rate provider protocol and adapter for Greek Electricity Tariff Engine.

Bridges the live market ingestion layer (HEnEx DAM clearing prices and RAE Green Tariffs)
with the core tariff engine calculation formulas.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class BaseMarketFeed(Protocol):
    """Protocol for dynamic market rate resolution engines."""

    def get_effective_tea(
        self,
        timestamp: datetime,
        tariff_color: str = "green",
        contract_type: str = "G22",
        supplier_id: str = "dei",
    ) -> float:
        """Resolve wholesale market rate (TEA or hourly MCP) in €/MWh."""
        ...


def resolve_effective_tea(
    timestamp: datetime,
    tariff_color: str = "green",
    contract_type: str = "G22",
    supplier_id: str = "dei",
    market_service: Any | None = None,
) -> float:
    """Resolve active wholesale market rate (€/MWh).

    If a market_service instance is provided and healthy, delegates to it.
    Otherwise returns default benchmark TEA = 120.0 €/MWh for 100% backward compatibility.
    """
    if market_service is not None and hasattr(market_service, "get_effective_tea"):
        try:
            return float(
                market_service.get_effective_tea(
                    timestamp=timestamp,
                    tariff_color=tariff_color,
                    contract_type=contract_type,
                    supplier_id=supplier_id,
                )
            )
        except (AttributeError, ValueError, TypeError, RuntimeError) as e:
            logger.debug("Market service TEA resolution fallback to 120.0: %s", e)
    return 120.0
