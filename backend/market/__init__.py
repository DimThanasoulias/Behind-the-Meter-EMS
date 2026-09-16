"""Greek Energy Market & Tariff Ingestion Engine package.

Exposes models, scrapers, fetchers, clients, and MarketPriceService.
"""

from backend.market.clients import (
    IMarketClient,
    LiveMarketClient,
    MockMarketClient,
)
from backend.market.fetcher_henex import (
    fetch_dam_hourly_prices,
    parse_henex_csv,
    parse_henex_json,
    validate_dam_prices,
)
from backend.market.models import (
    DamDaySummary,
    DamHourlyPrice,
    FetchDamResponse,
    GreenTariffAnnouncement,
    MarketStatus,
    RefreshGreenResponse,
)
from backend.market.scraper_rae import (
    parse_rae_html,
    parse_rae_json,
    scrape_monthly_green_tariffs,
    verify_green_tariff_formula,
)
from backend.market.service import (
    MarketPriceService,
    get_market_service,
)

__all__ = [
    "DamDaySummary",
    "DamHourlyPrice",
    "FetchDamResponse",
    "GreenTariffAnnouncement",
    "IMarketClient",
    "LiveMarketClient",
    "MarketPriceService",
    "MarketStatus",
    "MockMarketClient",
    "RefreshGreenResponse",
    "fetch_dam_hourly_prices",
    "get_market_service",
    "parse_henex_csv",
    "parse_henex_json",
    "parse_rae_html",
    "parse_rae_json",
    "scrape_monthly_green_tariffs",
    "validate_dam_prices",
    "verify_green_tariff_formula",
]
