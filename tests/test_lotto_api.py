"""Unit tests for the low-level HTTP handling in lotto_api.py.

These don't need the `hass` fixture - _fetch_json only needs something
that quacks like an aiohttp ClientSession.
"""
import json

import pytest

from custom_components.lotto.lotto_api import LottoApiError, _fetch_json, _parse_public_api_items

# A real response from lotto.pl's by-date-per-game endpoint, pasted by the
# user - locks in the (resultsJson=main numbers, specialResults=Euro
# numbers) shape for EuroJackpot as a regression guard.
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


def test_parse_public_api_items_eurojackpot_real_payload():
    results = _parse_public_api_items("EuroJackpot", EUROJACKPOT_SAMPLE["items"])

    assert len(results) == 2
    assert results[0].numbers == [47, 48, 6, 21, 31]
    assert results[0].euro_numbers == [2, 9]
    for r in results:
        assert len(r.numbers) == 5
        assert len(r.euro_numbers) == 2
        assert all(1 <= n <= 50 for n in r.numbers)
        assert all(1 <= n <= 12 for n in r.euro_numbers)


def test_parse_public_api_items_skips_unmatched_game_type():
    items = [
        {
            "drawDate": "2026-07-18T22:00:00Z",
            "results": [{"gameType": "LottoPlus", "resultsJson": [1, 2, 3, 4, 5, 6]}],
        }
    ]
    assert _parse_public_api_items("Lotto", items) == []
