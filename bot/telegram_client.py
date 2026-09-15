"""Telegram Bot client adapters (Interface, Mock, and Live implementations).

Provides dual-mode architecture:
- MockTelegramClient for 100% offline, deterministic, sub-millisecond unit/E2E testing.
- LiveTelegramClient for real outbound HTTP requests to Telegram Bot API.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ITelegramClient(ABC):
    """Abstract interface for Telegram bot communication."""

    @abstractmethod
    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str = "HTML",
    ) -> bool:
        """Send a message to a designated Telegram chat.

        Args:
            chat_id: Recipient unique chat ID or channel username.
            text: Message text (supports HTML formatting).
            parse_mode: Parsing mode ('HTML' recommended for Greek text).

        Returns:
            bool: True if sent successfully, False otherwise.
        """


class MockTelegramClient(ITelegramClient):
    """In-memory mock Telegram client for testing.

    Captures sent messages in an in-memory queue with inspection helpers.
    """

    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str = "HTML",
    ) -> bool:
        """Record the message in memory and return True."""
        message_record = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "timestamp": datetime.now(timezone.utc),
        }
        self.sent_messages.append(message_record)
        logger.debug("MockTelegramClient captured message for chat %s: %s", chat_id, text[:60])
        return True

    def get_sent_messages(self) -> list[dict[str, Any]]:
        """Return a copy of all captured messages."""
        return list(self.sent_messages)

    def get_last_message(self) -> dict[str, Any] | None:
        """Return the most recently sent message, or None if queue is empty."""
        return self.sent_messages[-1] if self.sent_messages else None

    def message_count(self) -> int:
        """Return the count of messages currently in the queue."""
        return len(self.sent_messages)

    def clear(self) -> None:
        """Clear all messages from the in-memory queue."""
        self.sent_messages.clear()


class LiveTelegramClient(ITelegramClient):
    """Production Telegram client using httpx to call Telegram Bot API."""

    def __init__(
        self,
        token: str,
        timeout: float = 10.0,
        base_url: str = "https://api.telegram.org",
    ) -> None:
        if not token:
            raise ValueError("LiveTelegramClient requires a non-empty bot token")
        self.token = token
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")

    @property
    def api_url(self) -> str:
        return f"{self.base_url}/bot{self.token}"

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str = "HTML",
    ) -> bool:
        """Send an asynchronous HTTP POST to Telegram's sendMessage endpoint."""
        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        return True
                    logger.warning("Telegram API error response: %s", data)
                    return False

                logger.error(
                    "Telegram API HTTP %d error: %s",
                    response.status_code,
                    response.text,
                )
                return False

        except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
            logger.error("Error sending Telegram message: %s", exc)
            return False
