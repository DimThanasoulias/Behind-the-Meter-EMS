"""Viber Bot client adapters (Interface, Mock, and Live implementations).

Provides dual-mode architecture:
- MockViberClient for 100% offline, deterministic, sub-millisecond unit/E2E testing.
- LiveViberClient for real outbound HTTP requests to the official Viber Bot API.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

VIBER_SEND_MESSAGE_URL = "https://chatapi.viber.com/pa/send_message"


class IViberClient(ABC):
    """Abstract interface for Viber bot communication."""

    @abstractmethod
    async def send_message(
        self,
        receiver_id: str,
        text: str,
        sender_name: str = "EMS Alert Bot",
        keyboard: dict[str, Any] | None = None,
    ) -> bool:
        """Send a message to a designated Viber user or subscriber.

        Args:
            receiver_id: Unique Viber member ID.
            text: Text message body.
            sender_name: Display name for the sender.
            keyboard: Optional custom keyboard layout for quick reply buttons.

        Returns:
            bool: True if sent successfully, False otherwise.
        """


class MockViberClient(IViberClient):
    """In-memory mock Viber client for testing.

    Captures sent messages in an in-memory queue with inspection helpers.
    """

    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []

    async def send_message(
        self,
        receiver_id: str,
        text: str,
        sender_name: str = "EMS Alert Bot",
        keyboard: dict[str, Any] | None = None,
    ) -> bool:
        """Record the message in memory and return True."""
        message_record = {
            "receiver_id": receiver_id,
            "text": text,
            "sender_name": sender_name,
            "keyboard": keyboard,
            "timestamp": datetime.now(timezone.utc),
        }
        self.sent_messages.append(message_record)
        logger.debug("MockViberClient captured message for receiver %s: %s", receiver_id, text[:60])
        return True

    def get_sent_messages(self, receiver_id: str | None = None) -> list[dict[str, Any]]:
        """Retrieve sent messages, optionally filtered by receiver_id."""
        if receiver_id is not None:
            return [m for m in self.sent_messages if m["receiver_id"] == receiver_id]
        return list(self.sent_messages)

    def get_last_message(self, receiver_id: str | None = None) -> dict[str, Any] | None:
        """Return the most recently sent message, or None if queue is empty."""
        msgs = self.get_sent_messages(receiver_id)
        return msgs[-1] if msgs else None

    def clear(self) -> None:
        """Clear all recorded messages."""
        self.sent_messages.clear()


class LiveViberClient(IViberClient):
    """Production Viber client communicating via Viber REST API."""

    def __init__(
        self,
        auth_token: str,
        timeout_seconds: float = 5.0,
        sender_avatar: str | None = None,
    ) -> None:
        self.auth_token = auth_token
        self.timeout_seconds = timeout_seconds
        self.sender_avatar = sender_avatar

    async def send_message(
        self,
        receiver_id: str,
        text: str,
        sender_name: str = "EMS Alert Bot",
        keyboard: dict[str, Any] | None = None,
    ) -> bool:
        if not self.auth_token or not receiver_id:
            logger.warning("LiveViberClient skipped: auth_token or receiver_id missing")
            return False

        headers = {
            "X-Viber-Auth-Token": self.auth_token,
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "receiver": str(receiver_id),
            "min_api_version": 1,
            "type": "text",
            "text": text,
            "sender": {
                "name": sender_name,
            },
        }
        if self.sender_avatar:
            payload["sender"]["avatar"] = self.sender_avatar
        if keyboard:
            payload["keyboard"] = keyboard

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    VIBER_SEND_MESSAGE_URL,
                    json=payload,
                    headers=headers,
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == 0:
                        logger.info("LiveViberClient sent alert to receiver %s", receiver_id)
                        return True
                    logger.warning("LiveViberClient API returned error status: %s", data)
                    return False
                logger.warning(
                    "LiveViberClient HTTP %d: %s",
                    response.status_code,
                    response.text[:120],
                )
                return False
        except httpx.RequestError as exc:
            logger.error("LiveViberClient network error: %s", exc)
            return False
