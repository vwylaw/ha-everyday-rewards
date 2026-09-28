"""Tests for the Everyday Rewards API client."""

from datetime import datetime, timedelta, timezone

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.everyday_rewards.api import (
    CLIENT_ID,
    AccessDeniedError,
    Account,
    ApiError,
    BoostResult,
    CannotConnectError,
    EverydayRewardsClient,
    InvalidCardError,
    Offer,
)

from .helpers import BOOST_URL, CARD, FIRST_NAME_URL, HASH, OFFERS_URL, load_json

AEST = timezone(timedelta(hours=10))


@pytest.fixture
async def client(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> EverydayRewardsClient:
    """Return a client using Home Assistant's mocked session."""
    return EverydayRewardsClient(async_get_clientsession(hass))


async def test_resolve_account(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A known card resolves to its first name and hashed CRN."""
    aioclient_mock.get(FIRST_NAME_URL, json=load_json("first_name.json"))

    account = await client.resolve_account(CARD)

    assert account == Account(first_name="Alex", hashed_crn=HASH)
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["loyalty_card_number"] == CARD
    assert headers["client_id"] == CLIENT_ID
    assert headers["channel"] == "OAP"


@pytest.mark.parametrize("status", [204, 404])
async def test_resolve_account_unknown_card(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    """A non-200 lookup means the card is not recognised."""
    aioclient_mock.get(FIRST_NAME_URL, status=status)

    with pytest.raises(InvalidCardError):
        await client.resolve_account(CARD)


async def test_resolve_account_server_error(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 5xx lookup is an API error, not a bad card."""
    aioclient_mock.get(FIRST_NAME_URL, status=500)

    with pytest.raises(ApiError):
        await client.resolve_account(CARD)


async def test_get_offers(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Offers are parsed and requested with the account's hashed CRN."""
    aioclient_mock.get(OFFERS_URL, json=load_json("offers_mixed.json"))

    offers = await client.get_offers(HASH)

    assert [offer.id for offer in offers] == ["1001", "1002", "1003", "1004"]
    assert offers[0] == Offer(
        id="1001",
        status="NotActivated",
        heading="Collect 3000 points",
        name="when you spend $60 or more at BIG W.",
        points=3000,
        ends=datetime(2026, 10, 4, 23, 59, 59, tzinfo=AEST),
        partners=("1060",),
        offer_type="OTHER",
    )
    assert [offer.boostable for offer in offers] == [True, True, False, False]
    assert [offer.boosted for offer in offers] == [False, False, True, False]
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["hashcrn"] == HASH
    assert headers["client_id"] == CLIENT_ID


async def test_requests_look_like_the_boost_widget(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Akamai stalls non-browser requests to the offers endpoint until timeout."""
    aioclient_mock.get(OFFERS_URL, json=load_json("offers_mixed.json"))

    await client.get_offers(HASH)

    headers = aioclient_mock.mock_calls[0][3]
    assert headers["user-agent"].startswith("Mozilla/5.0")
    assert headers["origin"] == "https://activate.woolworthsrewards.com.au"
    assert headers["referer"] == "https://activate.woolworthsrewards.com.au/"


@pytest.mark.parametrize(
    ("list_short", "expected"),
    [
        ("Woolworths Beanettes 400g*", "Woolworths Beanettes 400g"),
        (
            "when you spend $60 or more at Ampol Foodary.* Tap for T&Cs.",
            "when you spend $60 or more at Ampol Foodary.",
        ),
        (
            "on hundreds of participating products. Tap for T&Cs.",
            "on hundreds of participating products.",
        ),
        ("  ", "Collect 80 points"),
        (None, "Collect 80 points"),
    ],
)
def test_offer_name(list_short: str | None, expected: str) -> None:
    """The offer name comes from the short description, falling back to the heading."""
    offer = Offer.from_json(
        {
            "id": "1",
            "heading": "Collect 80 points",
            "description": {"listShort": list_short},
        }
    )

    assert offer.name == expected


def test_offer_name_without_description() -> None:
    """Offers with no description block use the heading as the name."""
    assert Offer.from_json({"id": "1", "heading": "Collect 80 points"}).name == (
        "Collect 80 points"
    )


@pytest.mark.parametrize("status", [401, 403])
async def test_get_offers_access_denied(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    """401/403 means the API has refused us."""
    aioclient_mock.get(OFFERS_URL, status=status)

    with pytest.raises(AccessDeniedError):
        await client.get_offers(HASH)


async def test_get_offers_not_json(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A non-JSON body is an API error."""
    aioclient_mock.get(OFFERS_URL, text="<html>maintenance</html>")

    with pytest.raises(ApiError):
        await client.get_offers(HASH)


async def test_get_offers_unexpected_shape(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """JSON without an offers list is an API error."""
    aioclient_mock.get(OFFERS_URL, json={"unexpected": True})

    with pytest.raises(ApiError):
        await client.get_offers(HASH)


@pytest.mark.parametrize("exc", [aiohttp.ClientError(), TimeoutError()])
async def test_get_offers_cannot_connect(
    client: EverydayRewardsClient,
    aioclient_mock: AiohttpClientMocker,
    exc: Exception,
) -> None:
    """Network failures and timeouts become CannotConnectError."""
    aioclient_mock.get(OFFERS_URL, exc=exc)

    with pytest.raises(CannotConnectError):
        await client.get_offers(HASH)


async def test_boost(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Boost posts all IDs in one request and reports per-offer results."""
    aioclient_mock.post(BOOST_URL, json=load_json("boost_mixed.json"))

    results = await client.boost(HASH, ["1001", "1002"])

    assert results == [
        BoostResult(offer_id="1001", success=True),
        BoostResult(offer_id="1002", success=False),
    ]
    _, _, body, headers = aioclient_mock.mock_calls[0]
    assert body == {"offerIds": ["1001", "1002"]}
    assert headers["hashcrn"] == HASH


async def test_boost_already_boosted_counts_as_success(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """An offer that was already boosted is treated as a success."""
    aioclient_mock.post(
        BOOST_URL,
        json=[
            {
                "success": False,
                "offer": {"id": "1001"},
                "code": 409,
                "isAlreadyBoosted": True,
            }
        ],
    )

    assert await client.boost(HASH, ["1001"]) == [
        BoostResult(offer_id="1001", success=True)
    ]


async def test_boost_nothing_is_a_noop(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Boosting no offers makes no request."""
    assert await client.boost(HASH, []) == []
    assert aioclient_mock.call_count == 0


async def test_boost_server_error(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A failed boost request is an API error."""
    aioclient_mock.post(BOOST_URL, status=500)

    with pytest.raises(ApiError):
        await client.boost(HASH, ["1001"])
