"""REST API routes for Greek Energy Market & Tariff Ingestion Engine.

Exposes:
- GET  /api/v1/market/dam/today: Today's 24h DAM price curve and summary statistics
- GET  /api/v1/market/dam/curve: 24h DAM price curve for target date
- GET  /api/v1/market/dam/hourly: Single hour DAM clearing rate
- GET  /api/v1/market/green-tariffs: Active Green Tariff announcements
- POST /api/v1/market/refresh-green: On-demand RAE Green Tariff ingestion trigger
- POST /api/v1/market/fetch-dam: On-demand HEnEx DAM price ingestion trigger
- GET  /api/v1/market/status: Operational health, caching metrics, and source modes
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from backend.database.sqlite_store import get_store
from backend.market.models import (
    DamDaySummary,
    DamHourlyPrice,
    FetchDamResponse,
    GreenTariffAnnouncement,
    MarketStatus,
    RefreshGreenResponse,
)
from backend.market.service import MarketPriceService, get_market_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["market"])


def get_market_service_dep(request: Request) -> MarketPriceService:
    """FastAPI dependency to retrieve MarketPriceService from application state or singleton."""
    if hasattr(request.app.state, "market_service") and request.app.state.market_service is not None:
        return request.app.state.market_service

    db_path = getattr(request.app.state, "db_path", None)
    store = get_store(db_path) if db_path else None
    service = get_market_service(store=store)
    request.app.state.market_service = service
    return service


@router.get(
    "/dam/today",
    response_model=DamDaySummary,
    summary="Get today's 24-hour DAM clearing prices and summary stats",
)
async def get_dam_today(
    service: Annotated[MarketPriceService, Depends(get_market_service_dep)],
) -> DamDaySummary:
    """Retrieve today's complete Day-Ahead Market clearing price curve and daily statistics."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return await service.get_dam_curve(today_str)


@router.get(
    "/dam/curve",
    response_model=DamDaySummary,
    summary="Get 24-hour DAM price curve for a specific date",
)
async def get_dam_curve(
    service: Annotated[MarketPriceService, Depends(get_market_service_dep)],
    date: Annotated[str | None, Query(description="Target date in YYYY-MM-DD format")] = None,
) -> DamDaySummary:
    """Retrieve Day-Ahead Market clearing curve for a specific date with 4-tier fallback."""
    target_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        return await service.get_dam_curve(target_date)
    except (httpx.HTTPError, OSError, RuntimeError, ValueError) as e:
        logger.error("Failed to retrieve DAM curve for %s: %s", target_date, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not retrieve DAM curve for {target_date}: {e}",
        )


@router.get(
    "/dam/hourly",
    response_model=DamHourlyPrice,
    summary="Get single-hour DAM clearing price",
)
async def get_dam_hourly(
    service: Annotated[MarketPriceService, Depends(get_market_service_dep)],
    timestamp: Annotated[str | None, Query(description="ISO8601 timestamp (defaults to current UTC)")] = None,
) -> DamHourlyPrice:
    """Retrieve the single-hour Day-Ahead Market clearing price for an exact timestamp."""
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    try:
        return await service.get_dam_hourly_price(ts)
    except (httpx.HTTPError, OSError, RuntimeError, ValueError) as e:
        logger.error("Failed to retrieve hourly DAM price for %s: %s", ts, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not retrieve hourly DAM price for {ts}: {e}",
        )


@router.get(
    "/green-tariffs",
    response_model=list[GreenTariffAnnouncement],
    summary="Get active RAE Green Tariff announcements",
)
async def get_green_tariffs(
    service: Annotated[MarketPriceService, Depends(get_market_service_dep)],
    month: Annotated[str | None, Query(description="Month in YYYY-MM format (defaults to current)")] = None,
    supplier_id: Annotated[str | None, Query(description="Optional supplier filter (e.g. dei, protergia)")] = None,
) -> list[GreenTariffAnnouncement]:
    """Retrieve official Greek Special Green Tariff parameters with formula parameters."""
    target_month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        return await service.get_green_tariffs(target_month, supplier_id)
    except (httpx.HTTPError, OSError, RuntimeError, ValueError) as e:
        logger.error("Failed to retrieve green tariffs for %s: %s", target_month, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not retrieve green tariffs for {target_month}: {e}",
        )


@router.post(
    "/refresh-green",
    response_model=RefreshGreenResponse,
    summary="Trigger on-demand scraping of RAE Green Tariffs",
)
async def refresh_green_tariffs(
    service: Annotated[MarketPriceService, Depends(get_market_service_dep)],
    month: Annotated[str | None, Query(description="Month in YYYY-MM format")] = None,
) -> RefreshGreenResponse:
    """Manually trigger ingestion of Green Tariff parameters from RAE / energycost.gr."""
    target_month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        tariffs = await service.refresh_green_tariffs(target_month)
        return RefreshGreenResponse(
            status="success",
            count=len(tariffs),
            month=target_month,
        )
    except (httpx.HTTPError, OSError, RuntimeError, ValueError) as e:
        logger.error("Error during manual green tariff refresh: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh green tariffs: {e}",
        )


@router.post(
    "/fetch-dam",
    response_model=FetchDamResponse,
    summary="Trigger on-demand fetching of HEnEx DAM prices",
)
async def fetch_dam(
    service: Annotated[MarketPriceService, Depends(get_market_service_dep)],
    date: Annotated[str | None, Query(description="Target date in YYYY-MM-DD format")] = None,
) -> FetchDamResponse:
    """Manually trigger ingestion of 24h DAM clearing prices from HEnEx / ENEX feeds."""
    target_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        prices = await service.fetch_dam_curve(target_date)
        return FetchDamResponse(
            status="success",
            hours_fetched=len(prices),
            date=target_date,
        )
    except (httpx.HTTPError, OSError, RuntimeError, ValueError) as e:
        logger.error("Error during manual DAM fetch: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch DAM prices for {target_date}: {e}",
        )


@router.get(
    "/status",
    response_model=MarketStatus,
    summary="Get market ingestion status and metrics",
)
async def get_market_status(
    service: Annotated[MarketPriceService, Depends(get_market_service_dep)],
) -> MarketStatus:
    """Retrieve health, timestamps, cached records count, and active source modes."""
    return service.get_market_status()
