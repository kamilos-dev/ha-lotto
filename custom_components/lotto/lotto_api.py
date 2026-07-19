"""Async clients for fetching Lotto/EuroJackpot draw results.

Two providers are supported:

- `LottoOpenApiClient`: the official Lotto Open API (developers.lotto.pl).
  Requires a free API key requested from Totalizator Sportowy
  (openapi@totalizator.pl).
- `LottoPublicApiClient`: the unofficial, unauthenticated JSON endpoint that
  powers the public results page on lotto.pl. No key needed, but it's not a
  documented contract - it could change or start blocking non-browser
  traffic without notice.

`create_client()` picks between them based on whether an API key was
configured. Everything specific to either wire format lives in this one
file so drift only needs a fix here.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from aiohttp import ClientError, ClientSession

from .const import GAME_EUROJACKPOT
from .rules import GAME_RULES

_LOGGER = logging.getLogger(__name__)

OPEN_API_BASE_URL = "https://developers.lotto.pl/api/open/v1"
PUBLIC_API_BY_GAMETYPE_URL = "https://www.lotto.pl/api/lotteries/draw-results/by-gametype"
PUBLIC_API_BY_COLLECTION_URL = "https://www.lotto.pl/api/lotteries/draw-results/by-collection-per-game"
REQUEST_TIMEOUT = 15

# The public endpoint is the same one the lotto.pl website's own frontend
# calls; some requests without browser-like headers get served an HTML
# challenge page instead of JSON, so these are sent defensively.
PUBLIC_API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.lotto.pl/wyniki-losowan/lotto",
}


class LottoApiError(Exception):
    """Generic error talking to a Lotto results provider."""


class LottoApiAuthError(LottoApiError):
    """The API key was rejected (Open API only)."""


@dataclass
class DrawResult:
    """A single draw result, normalized regardless of the game type."""

    game_type: str
    draw_date: date
    numbers: list[int]
    euro_numbers: list[int]


def _parse_draw_date(raw: str) -> date:
    # Both providers have been seen returning bare dates ("2026-07-21") and
    # full ISO timestamps ("2026-07-21T22:00:00Z"); normalize to a date.
    text = str(raw).strip()
    if "T" in text:
        text = text.split("T", 1)[0]
    return date.fromisoformat(text)


async def _fetch_json(
    session: ClientSession, url: str, headers: dict[str, str], params: dict[str, Any]
) -> tuple[int, Any]:
    """GET `url` and return (status, parsed_json_or_None)."""
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    return resp.status, None
                return resp.status, await resp.json(content_type=None)
    except (ClientError, TimeoutError) as err:
        raise LottoApiError(f"Błąd komunikacji z {url}: {err}") from err


def _parse_open_api_results_field(
    game_type: str, raw_results: Any
) -> tuple[list[int], list[int]]:
    """Split the Open API's `resultsJson` field into (main, euro) numbers.

    The exact shape isn't nailed down for every game without a live API key,
    so this handles the two shapes that are known to occur: a flat list of
    numbers, or a list of number-groups (main numbers, then bonus numbers).
    """
    rules = GAME_RULES[game_type]

    if raw_results and isinstance(raw_results[0], list):
        main = [int(n) for n in raw_results[0]]
        euro = [int(n) for n in raw_results[1]] if len(raw_results) > 1 else []
        return main, euro

    flat = [int(n) for n in raw_results]
    if rules.euro_count and len(flat) == rules.numbers_count + rules.euro_count:
        return flat[: rules.numbers_count], flat[rules.numbers_count :]
    return flat, []


class LottoOpenApiClient:
    """Client for the official, key-authenticated Lotto Open API."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def async_verify_connection(self) -> None:
        """Raise LottoApiAuthError/LottoApiError if the key doesn't work."""
        await self.async_get_last_results(GAME_EUROJACKPOT, size=1)

    async def async_get_last_results(self, game_type: str, size: int = 20) -> list[DrawResult]:
        url = f"{OPEN_API_BASE_URL}/lotteries/draw-results/last-results"
        headers = {"Secret": self._api_key, "Accept": "application/json"}
        params = {
            "gameType": game_type,
            "index": 1,
            "size": size,
            "sort": "drawDate",
            "order": "DESC",
        }
        status, payload = await _fetch_json(self._session, url, headers, params)
        if status in (401, 403):
            raise LottoApiAuthError(f"Lotto Open API odrzuciło klucz API (HTTP {status})")
        if status != 200:
            raise LottoApiError(f"Lotto Open API zwróciło błąd HTTP {status}")

        items = payload
        if isinstance(payload, dict):
            for key in ("items", "results", "content", "data"):
                if key in payload and isinstance(payload[key], list):
                    items = payload[key]
                    break

        results: list[DrawResult] = []
        for item in items or []:
            try:
                main, euro = _parse_open_api_results_field(game_type, item["resultsJson"])
                results.append(
                    DrawResult(
                        game_type=item.get("gameType", game_type),
                        draw_date=_parse_draw_date(item["drawDate"]),
                        numbers=main,
                        euro_numbers=euro,
                    )
                )
            except (KeyError, ValueError, TypeError) as err:
                _LOGGER.warning("Nie udało się przetworzyć wyniku losowania %s: %s", item, err)

        return results


def _parse_public_api_items(game_type: str, items: list[Any]) -> list[DrawResult]:
    """Parse the shared item shape used by both public lotto.pl endpoints.

    Each `item` bundles every game drawn together on that date (e.g. Lotto +
    LottoPlus) under `results`, so the sub-result matching the requested game
    type is picked out of that list.
    """
    results: list[DrawResult] = []
    for item in items:
        try:
            draw_date = _parse_draw_date(item["drawDate"])
            sub_result = next(
                (r for r in item.get("results", []) if r.get("gameType") == game_type),
                None,
            )
            if sub_result is None:
                continue
            results.append(
                DrawResult(
                    game_type=game_type,
                    draw_date=draw_date,
                    numbers=[int(n) for n in sub_result["resultsJson"]],
                    euro_numbers=[int(n) for n in sub_result.get("specialResults", [])],
                )
            )
        except (KeyError, ValueError, TypeError) as err:
            _LOGGER.warning("Nie udało się przetworzyć wyniku losowania %s: %s", item, err)
    return results


class LottoPublicApiClient:
    """Client for the unofficial, unauthenticated lotto.pl results endpoints.

    Used by default when no Open API key is configured.
    """

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def async_verify_connection(self) -> None:
        await self.async_get_last_results(GAME_EUROJACKPOT, size=1)

    async def async_get_last_results(self, game_type: str, size: int = 20) -> list[DrawResult]:
        """Fetch the `size` most recent draws for `game_type`."""
        params = {
            "game": game_type,
            "index": 1,
            "size": size,
            "sort": "drawDate",
            "order": "DESC",
            "initialSize": size,
        }
        status, payload = await _fetch_json(
            self._session, PUBLIC_API_BY_GAMETYPE_URL, PUBLIC_API_HEADERS, params
        )
        if status != 200:
            raise LottoApiError(f"lotto.pl zwróciło błąd HTTP {status}")
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise LottoApiError("lotto.pl zwróciło nieoczekiwaną odpowiedź (nie JSON?)")

        return _parse_public_api_items(game_type, payload["items"])

    async def async_get_results_from(
        self, game_type: str, from_date: date, quantity: int
    ) -> list[DrawResult]:
        """Fetch up to `quantity` draws for `game_type` on or after `from_date`.

        Maps directly onto a coupon's (first_draw_date, draws_total) - unlike
        async_get_last_results this can't miss old draws regardless of how
        long Home Assistant was offline, since it's anchored to a date
        instead of "the N most recent".
        """
        params = {"gameType": game_type, "drawDate": from_date.isoformat(), "quantity": quantity}
        status, payload = await _fetch_json(
            self._session, PUBLIC_API_BY_COLLECTION_URL, PUBLIC_API_HEADERS, params
        )
        if status != 200:
            raise LottoApiError(f"lotto.pl zwróciło błąd HTTP {status}")
        if not isinstance(payload, list):
            raise LottoApiError("lotto.pl zwróciło nieoczekiwaną odpowiedź (nie JSON?)")

        return _parse_public_api_items(game_type, payload)


def create_client(
    session: ClientSession, api_key: str | None
) -> LottoOpenApiClient | LottoPublicApiClient:
    """Pick the Open API client if a key was configured, else the public one."""
    if api_key:
        return LottoOpenApiClient(session, api_key)
    return LottoPublicApiClient(session)
