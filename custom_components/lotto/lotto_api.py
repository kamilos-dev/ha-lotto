"""Async client for fetching Lotto/EuroJackpot draw results from the
official Lotto Open API (developers.lotto.pl). Requires a free API key
requested from Totalizator Sportowy (openapi@totalizator.pl).

An earlier version also supported an unofficial, unauthenticated public
endpoint as a key-free fallback, but it's Cloudflare-protected on some
networks in a way a background HTTP client can't get past (needs a
browser-obtained cf_clearance cookie plus a per-page request-token) - it
was removed rather than kept as a provider that silently never works for
some users.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from aiohttp import ClientError, ClientSession

from .const import GAME_EUROJACKPOT, RESULTS_FETCH_SIZE

_LOGGER = logging.getLogger(__name__)

OPEN_API_BASE_URL = "https://developers.lotto.pl/api/open/v1"
REQUEST_TIMEOUT = 15


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
    """GET `url` and return (status, parsed_json_or_None).

    lotto.pl's anti-bot protection has been observed serving an HTML
    challenge page with a plain HTTP 200, so a 200 status alone doesn't
    guarantee the body is JSON - that failure mode is logged with a body
    snippet (visible in Settings -> System -> Logs) and raised as
    LottoApiError instead of leaking a raw JSONDecodeError.
    """
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            async with session.get(url, headers=headers, params=params) as resp:
                status = resp.status
                if status != 200:
                    body = await resp.text()
                    _LOGGER.warning("GET %s -> HTTP %s: %s", url, status, body[:300])
                    return status, None
                try:
                    return status, await resp.json(content_type=None)
                except ValueError as err:
                    body = await resp.text()
                    _LOGGER.warning(
                        "GET %s zwróciło HTTP 200, ale treść nie jest poprawnym JSON-em "
                        "(prawdopodobnie strona z zabezpieczeniem antybotowym zamiast wyników): %s",
                        url,
                        body[:300],
                    )
                    raise LottoApiError(f"{url} zwróciło HTTP 200 z nieprawidłowym JSON-em") from err
    except (ClientError, TimeoutError) as err:
        _LOGGER.warning("Błąd komunikacji z %s: %s", url, err)
        raise LottoApiError(f"Błąd komunikacji z {url}: {err}") from err


def _parse_draw_items(game_type: str, items: list[Any]) -> list[DrawResult]:
    """Parse the Open API's response item shape (confirmed against a real
    API key: the initial assumption of a flat top-level `resultsJson` field
    was wrong and produced KeyErrors on every real draw).

    Each `item` bundles every game drawn at that date/time together (e.g.
    Lotto + LottoPlus, or EkstraPensja + EkstraPremia) under `results`, so
    the sub-result matching the requested game type is picked out of that
    list. Items with no matching sub-result (a different game entirely) are
    silently skipped rather than logged as errors - that's the normal case
    whenever a fetch happens to include another game's draws.
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


class LottoOpenApiClient:
    """Client for the official, key-authenticated Lotto Open API."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def async_verify_connection(self) -> None:
        """Raise LottoApiAuthError/LottoApiError if the key doesn't work."""
        await self.async_get_last_results(GAME_EUROJACKPOT, size=1)

    async def async_get_last_results(self, game_type: str, size: int = 20) -> list[DrawResult]:
        """Fetch the `size` most recent draws for `game_type`.

        Tries `last-results-per-game` first - the per-game-filtered variant.
        The plain `last-results` endpoint has been observed NOT filtering by
        `gameType` server-side at all: a request for "Lotto" came back full
        of unrelated games (EkstraPensja, Keno, Szybkie600, ...), several of
        which draw many times a day, so a small `size` can easily contain
        zero Lotto/EuroJackpot draws. If `last-results-per-game` doesn't
        exist (404) on this API version, this falls back to the unfiltered
        endpoint and relies on _parse_draw_items' client-side filtering
        instead - a config entry on that fallback path may need a much
        larger RESULTS_FETCH_SIZE (const.py) to reliably see its own game's
        draws.
        """
        headers = {"Secret": self._api_key, "Accept": "application/json"}
        params = {
            "gameType": game_type,
            "index": 1,
            "size": size,
            "sort": "drawDate",
            "order": "DESC",
        }

        url = f"{OPEN_API_BASE_URL}/lotteries/draw-results/last-results-per-game"
        status, payload = await _fetch_json(self._session, url, headers, params)

        if status == 404:
            _LOGGER.warning(
                "%s zwróciło HTTP 404 - używam last-results (bez filtrowania po stronie serwera)",
                url,
            )
            url = f"{OPEN_API_BASE_URL}/lotteries/draw-results/last-results"
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

        return _parse_draw_items(game_type, items or [])

    async def async_get_results_from(
        self, game_type: str, from_date: date, quantity: int
    ) -> list[DrawResult]:
        """Fetch up to `quantity` draws for `game_type` on or after `from_date`.

        Tries `by-collection-per-game` first: confirmed (against the public,
        unauthenticated lotto.pl site, whose backend the Open API very
        likely shares - unverified on developers.lotto.pl itself for lack
        of a live key at the time this was written) to treat `drawDate` as
        an inclusive lower bound and return draws moving forward from it -
        exactly what a coupon's (first_draw_date, draws_total) needs.
        (`by-date-per-game`, a differently-named endpoint, does the
        opposite - `drawDate` there is an upper bound, walking backward in
        time - so it's deliberately not used here.)

        If `by-collection-per-game` 404s, falls back to
        async_get_last_results with a wide net (RESULTS_FETCH_SIZE) and
        filters client-side by date - this can still miss draws further
        back than that window reaches if other games draw far more
        frequently, since that endpoint isn't date-anchored.
        """
        headers = {"Secret": self._api_key, "Accept": "application/json"}
        url = f"{OPEN_API_BASE_URL}/lotteries/draw-results/by-collection-per-game"
        params = {"gameType": game_type, "drawDate": from_date.isoformat(), "quantity": quantity}
        status, payload = await _fetch_json(self._session, url, headers, params)

        if status == 404:
            _LOGGER.warning(
                "%s zwróciło HTTP 404 - używam last-results z szerokim oknem "
                "(może pominąć losowania starsze niż to okno)",
                url,
            )
            results = await self.async_get_last_results(
                game_type, max(quantity, RESULTS_FETCH_SIZE)
            )
            return [r for r in results if r.draw_date >= from_date]

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

        return _parse_draw_items(game_type, items or [])
