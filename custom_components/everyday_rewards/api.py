"""Client for the unofficial Everyday Rewards boost API.

This module has no Home Assistant imports so it can be tested and reused on its own.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp

API_BASE = "https://prod.api-wr.com"
CLIENT_ID = "i0U7OrzMGFD16vPaIaCRvGZDZ0YIeGGQ"
FIRST_NAME_PATH = "/v1/oam/getFirstName"
OFFERS_PATH = "/wx/v1/csl/customers/offers"
BOOST_PATH = "/wx/v1/csl/customers/offers/boost"

# Akamai in front of the offers endpoint stalls non-browser requests until they
# time out, so present the same browser headers as the boost widget.
WIDGET_ORIGIN = "https://activate.woolworthsrewards.com.au"
BROWSER_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
    ),
    "origin": WIDGET_ORIGIN,
    "referer": f"{WIDGET_ORIGIN}/",
}

STATUS_NOT_ACTIVATED = "NotActivated"
STATUS_ACTIVATED = "Activated"


class EverydayRewardsError(Exception):
    """Base error for the Everyday Rewards client."""


class CannotConnectError(EverydayRewardsError):
    """Network failure or timeout."""


class InvalidCardError(EverydayRewardsError):
    """The card number was not recognised."""


class AccessDeniedError(EverydayRewardsError):
    """The API refused the request (HTTP 401/403)."""


class ApiError(EverydayRewardsError):
    """Unexpected status code or response body."""


def _offer_name(data: dict[str, Any], heading: str) -> str:
    """Return the offer's product or partner text, e.g. "Woolworths Beanettes 400g"."""
    text = str((data.get("description") or {}).get("listShort") or "")
    text = text.replace("Tap for T&Cs.", "").strip().rstrip("*").strip()
    return text or heading


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _utc_offset_minutes() -> int:
    offset = datetime.now().astimezone().utcoffset()
    return int(offset.total_seconds() // 60) if offset else 0


@dataclass(frozen=True)
class Account:
    """An Everyday Rewards account resolved from a card number."""

    first_name: str
    hashed_crn: str


@dataclass(frozen=True)
class Offer:
    """A single booster offer."""

    id: str
    status: str
    heading: str
    name: str
    points: int | None
    ends: datetime | None
    partners: tuple[str, ...]
    offer_type: str

    @property
    def boostable(self) -> bool:
        """Return True if the offer can still be boosted."""
        return self.status == STATUS_NOT_ACTIVATED

    @property
    def boosted(self) -> bool:
        """Return True if the offer has been boosted and is still running."""
        return self.status == STATUS_ACTIVATED

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Offer:
        """Build an offer from an API offer object."""
        reward = data.get("rewardValue") or {}
        activation = data.get("activation") or {}
        heading = str(data.get("heading", ""))
        return cls(
            id=str(data["id"]),
            status=str(data.get("status", "")),
            heading=heading,
            name=_offer_name(data, heading),
            points=reward.get("points"),
            ends=_parse_datetime(activation.get("endDate")),
            partners=tuple(str(p) for p in data.get("divisionPartnerIds") or ()),
            offer_type=str(data.get("offerType", "")),
        )


@dataclass(frozen=True)
class BoostResult:
    """The outcome of boosting one offer."""

    offer_id: str
    success: bool

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> BoostResult:
        """Build a result from one element of the boost response."""
        return cls(
            offer_id=str((data.get("offer") or {}).get("id", "")),
            success=bool(data.get("success") or data.get("isAlreadyBoosted")),
        )


class EverydayRewardsClient:
    """Async client for the Everyday Rewards boost API."""

    def __init__(self, session: aiohttp.ClientSession, timeout: float = 30) -> None:
        """Initialise the client with a shared aiohttp session."""
        self._session = session
        self._timeout = timeout

    async def resolve_account(self, card_number: str) -> Account:
        """Look up the account for a card number."""
        status, data = await self._request(
            "GET",
            FIRST_NAME_PATH,
            {"loyalty_card_number": card_number, "channel": "OAP"},
        )
        if status >= 500:
            raise ApiError(f"Unexpected status {status} resolving card")
        if status != 200 or not isinstance(data, dict) or not data.get("hashed_crn"):
            raise InvalidCardError("Card number not recognised")
        return Account(
            first_name=str(data.get("first_name") or ""),
            hashed_crn=str(data["hashed_crn"]),
        )

    async def get_offers(self, hashed_crn: str) -> list[Offer]:
        """Return every offer on the account."""
        status, data = await self._request(
            "GET", OFFERS_PATH, self._account_headers(hashed_crn)
        )
        if (
            status != 200
            or not isinstance(data, dict)
            or not isinstance(data.get("offers"), list)
        ):
            raise ApiError(f"Unexpected offers response (HTTP {status})")
        return [Offer.from_json(item) for item in data["offers"]]

    async def boost(
        self, hashed_crn: str, offer_ids: Iterable[str]
    ) -> list[BoostResult]:
        """Boost the given offers in a single request."""
        ids = list(offer_ids)
        if not ids:
            return []
        status, data = await self._request(
            "POST",
            BOOST_PATH,
            self._account_headers(hashed_crn),
            {"offerIds": ids},
        )
        if status != 200 or not isinstance(data, list):
            raise ApiError(f"Unexpected boost response (HTTP {status})")
        return [BoostResult.from_json(item) for item in data]

    @staticmethod
    def _account_headers(hashed_crn: str) -> dict[str, str]:
        return {
            "hashcrn": hashed_crn,
            "content-type": "application/json",
            "userlocaltime": str(_utc_offset_minutes()),
        }

    async def _request(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        json_body: Any = None,
    ) -> tuple[int, Any]:
        """Return (status, parsed JSON body or None for non-200 responses)."""
        try:
            async with (
                asyncio.timeout(self._timeout),
                self._session.request(
                    method,
                    f"{API_BASE}{path}",
                    headers={
                        **BROWSER_HEADERS,
                        "client_id": CLIENT_ID,
                        "accept": "application/json",
                        **headers,
                    },
                    json=json_body,
                ) as resp,
            ):
                if resp.status in (401, 403):
                    raise AccessDeniedError(f"Access denied (HTTP {resp.status})")
                if resp.status != 200:
                    return resp.status, None
                try:
                    return resp.status, await resp.json(content_type=None)
                except ValueError as err:
                    raise ApiError("Response was not valid JSON") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnectError(
                f"Error talking to Everyday Rewards: {err!r}"
            ) from err
