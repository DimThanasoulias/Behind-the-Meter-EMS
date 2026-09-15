"""Telegram bot package for the Greek Commercial EMS."""

from bot.telegram_client import (
    ITelegramClient,
    LiveTelegramClient,
    MockTelegramClient,
)

__all__ = [
    "ITelegramClient",
    "LiveTelegramClient",
    "MockTelegramClient",
]
