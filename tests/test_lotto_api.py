"""Unit tests for the low-level HTTP handling in lotto_api.py.

These don't need the `hass` fixture - _fetch_json only needs something
that quacks like an aiohttp ClientSession.
"""
import json
from datetime import date

import pytest

from custom_components.lotto.lotto_api import (
    LottoApiAuthError,
    LottoApiError,
    LottoOpenApiClient,
    _fetch_json,
    _parse_draw_items,
)

# A real response shape from the Open API's last-results endpoint (pasted by
# the user, using a real API key) - the envelope wraps unrelated game types
# (EkstraPensja here) that don't match the requested "Lotto"/"EuroJackpot",
# alongside the field name mismatch that originally broke parsing
# (`results: [...]` with nested `resultsJson`, not a flat top-level
# `resultsJson`).
OPEN_API_MIXED_GAMES_SAMPLE = [
    {
        "drawSystemId": 3727,
        "drawDate": "2026-07-21T20:00:00Z",
        "gameType": "EkstraPensja",
        "results": [
            {
                "drawDate": "2026-07-21T20:00:00Z",
                "gameType": "EkstraPensja",
                "resultsJson": [15, 26, 6, 28, 12],
                "specialResults": [1],
            },
            {
                "drawDate": "2026-07-21T20:00:00Z",
                "gameType": "EkstraPremia",
                "resultsJson": [17, 23, 32, 10, 1],
                "specialResults": [1],
            },
        ],
    },
    {
        "drawSystemId": 7381,
        "drawDate": "2026-07-21T22:00:00Z",
        "gameType": "Lotto",
        "results": [
            {
                "drawDate": "2026-07-21T22:00:00Z",
                "gameType": "Lotto",
                "resultsJson": [1, 2, 3, 4, 5, 6],
                "specialResults": [],
            },
            {
                "drawDate": "2026-07-21T22:00:00Z",
                "gameType": "LottoPlus",
                "resultsJson": [7, 8, 9, 10, 11, 12],
                "specialResults": [],
            },
        ],
    },
]

# A real lotto.pl envelope response for EuroJackpot, pasted by the user -
# locks in the (resultsJson=main numbers, specialResults=Euro numbers)
# shape as a regression guard.
EUROJACKPOT_SAMPLE = {
    "items": [
        {
            "drawSystemId": 687,
            "drawDate": "2026-07-17T20:00:00Z",
            "gameType": "EuroJackpot",
            "results": [
                {
                    "drawDate": "2026-07-17T20:00:00Z",
                    "gameType": "EuroJackpot",
                    "resultsJson": [47, 48, 6, 21, 31],
                    "specialResults": [2, 9],
                }
            ],
        },
        {
            "drawSystemId": 686,
            "drawDate": "2026-07-14T20:15:00Z",
            "gameType": "EuroJackpot",
            "results": [
                {
                    "drawDate": "2026-07-14T20:15:00Z",
                    "gameType": "EuroJackpot",
                    "resultsJson": [34, 6, 36, 17, 5],
                    "specialResults": [3, 11],
                }
            ],
        },
    ]
}


class FakeResponse:
    def __init__(self, status: int, text_body: str) -> None:
        self.status = status
        self._text_body = text_body

    async def text(self) -> str:
        return self._text_body

    async def json(self, content_type=None):
        return json.loads(self._text_body)  # raises JSONDecodeError on HTML

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self._response = response

    def get(self, url, headers=None, params=None):
        return self._response


async def test_html_challenge_page_raises_clean_error():
    """lotto.pl's anti-bot protection has been observed serving an HTML
    challenge page with a plain HTTP 200 - this must not leak a raw
    JSONDecodeError."""
    html = "<!DOCTYPE html><html><head><title>Lotto</title></head><body>challenge</body></html>"
    session = FakeSession(FakeResponse(200, html))

    with pytest.raises(LottoApiError):
        await _fetch_json(session, "https://www.lotto.pl/api/x", {}, {})


async def test_valid_json_still_works():
    session = FakeSession(FakeResponse(200, '{"items": []}'))
    status, payload = await _fetch_json(session, "https://www.lotto.pl/api/x", {}, {})
    assert status == 200
    assert payload == {"items": []}


async def test_non_200_status_returns_status_without_raising():
    session = FakeSession(FakeResponse(403, "Forbidden"))
    status, payload = await _fetch_json(session, "https://www.lotto.pl/api/x", {}, {})
    assert status == 403
    assert payload is None


def test_parse_draw_items_eurojackpot_real_payload():
    results = _parse_draw_items("EuroJackpot", EUROJACKPOT_SAMPLE["items"])

    assert len(results) == 2
    assert results[0].numbers == [47, 48, 6, 21, 31]
    assert results[0].euro_numbers == [2, 9]
    for r in results:
        assert len(r.numbers) == 5
        assert len(r.euro_numbers) == 2
        assert all(1 <= n <= 50 for n in r.numbers)
        assert all(1 <= n <= 12 for n in r.euro_numbers)


def test_parse_draw_items_skips_unmatched_game_type():
    items = [
        {
            "drawDate": "2026-07-18T22:00:00Z",
            "results": [{"gameType": "LottoPlus", "resultsJson": [1, 2, 3, 4, 5, 6]}],
        }
    ]
    assert _parse_draw_items("Lotto", items) == []


class RoutedFakeSession:
    """Fake ClientSession returning a different canned response per URL,
    tracking every URL requested - for exercising LottoOpenApiClient's
    endpoint fallback."""

    def __init__(self, responses_by_url: dict[str, FakeResponse]) -> None:
        self._responses_by_url = responses_by_url
        self.requested_urls: list[str] = []

    def get(self, url, headers=None, params=None):
        self.requested_urls.append(url)
        return self._responses_by_url[url]


PER_GAME_URL = "https://developers.lotto.pl/api/open/v1/lotteries/draw-results/last-results-per-game"
LEGACY_URL = "https://developers.lotto.pl/api/open/v1/lotteries/draw-results/last-results"


async def test_open_api_parses_real_mixed_game_envelope():
    """The Open API's last-results-per-game endpoint wraps each draw in an
    envelope with a nested `results` list, filtered client-side by
    _parse_draw_items - this is the exact payload shape that originally
    caused 'resultsJson' KeyErrors on every draw."""
    session = RoutedFakeSession(
        {PER_GAME_URL: FakeResponse(200, json.dumps(OPEN_API_MIXED_GAMES_SAMPLE))}
    )
    client = LottoOpenApiClient(session, "test-key")

    results = await client.async_get_last_results("Lotto", size=10)

    assert len(results) == 1
    assert results[0].numbers == [1, 2, 3, 4, 5, 6]
    assert session.requested_urls == [PER_GAME_URL]


async def test_open_api_falls_back_to_legacy_endpoint_on_404():
    session = RoutedFakeSession(
        {
            PER_GAME_URL: FakeResponse(404, "Not Found"),
            LEGACY_URL: FakeResponse(200, json.dumps(OPEN_API_MIXED_GAMES_SAMPLE)),
        }
    )
    client = LottoOpenApiClient(session, "test-key")

    results = await client.async_get_last_results("Lotto", size=10)

    assert len(results) == 1
    assert results[0].numbers == [1, 2, 3, 4, 5, 6]
    # Tried the per-game endpoint first, then fell back after the 404.
    assert session.requested_urls == [PER_GAME_URL, LEGACY_URL]


async def test_open_api_rejects_bad_key():
    session = RoutedFakeSession({PER_GAME_URL: FakeResponse(401, "Unauthorized")})
    client = LottoOpenApiClient(session, "bad-key")

    with pytest.raises(LottoApiAuthError):
        await client.async_get_last_results("Lotto")


COLLECTION_URL = "https://developers.lotto.pl/api/open/v1/lotteries/draw-results/by-collection-per-game"

# The exact envelope shape the user confirmed live on the public site for
# by-collection-per-game: dates move FORWARD from the requested `drawDate`
# (a lower bound), unlike by-date-per-game which walks backward from it.
FORWARD_LOOKING_SAMPLE = [
    {
        "drawSystemId": 7373,
        "drawDate": "2026-07-02T22:00:00Z",
        "gameType": "Lotto",
        "results": [
            {"gameType": "Lotto", "resultsJson": [30, 34, 11, 23, 8, 10], "specialResults": []},
        ],
    },
    {
        "drawSystemId": 7374,
        "drawDate": "2026-07-04T22:00:00Z",
        "gameType": "Lotto",
        "results": [
            {"gameType": "Lotto", "resultsJson": [13, 30, 11, 36, 26, 49], "specialResults": []},
        ],
    },
]


async def test_open_api_get_results_from_uses_collection_endpoint():
    session = RoutedFakeSession(
        {COLLECTION_URL: FakeResponse(200, json.dumps(FORWARD_LOOKING_SAMPLE))}
    )
    client = LottoOpenApiClient(session, "test-key")

    results = await client.async_get_results_from("Lotto", date(2026, 7, 1), 10)

    assert [r.draw_date for r in results] == [date(2026, 7, 2), date(2026, 7, 4)]
    assert session.requested_urls == [COLLECTION_URL]


async def test_open_api_get_results_from_falls_back_and_filters_by_date_on_404():
    """If by-collection-per-game doesn't exist, falls back to the
    last-results chain (itself trying last-results-per-game first) and
    filters the wide-net results client-side to only those on/after
    from_date."""
    session = RoutedFakeSession(
        {
            COLLECTION_URL: FakeResponse(404, "Not Found"),
            PER_GAME_URL: FakeResponse(200, json.dumps(OPEN_API_MIXED_GAMES_SAMPLE)),
        }
    )
    client = LottoOpenApiClient(session, "test-key")

    # OPEN_API_MIXED_GAMES_SAMPLE's one Lotto draw is dated 2026-07-21.
    results = await client.async_get_results_from("Lotto", date(2026, 7, 1), 1)
    assert len(results) == 1
    assert results[0].draw_date == date(2026, 7, 21)

    results_after = await client.async_get_results_from("Lotto", date(2026, 7, 22), 1)
    assert results_after == []
