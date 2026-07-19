"""Thin async client for the Lotto Open API (developers.lotto.pl).

Access requires a free API key requested from Totalizator Sportowy
(openapi@totalizator.pl). Everything specific to the wire format lives in
this one file so a schema drift only needs a fix here.
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

BASE_URL = "https://developers.lotto.pl/api/open/v1"
REQUEST_TIMEOUT = 15


class LottoApiError(Exception):
    """Generic error talking to the Lotto Open API."""


class LottoApiAuthError(LottoApiError):
    """The API key was rejected."""


@dataclass
class DrawResult:
    """A single draw result, normalized regardless of the game type."""

    game_type: str
    draw_date: date
    numbers: list[int]
    euro_numbers: list[int]


def _parse_draw_date(raw: str) -> date:
    # The API has been seen returning both bare dates ("2026-07-21") and
    # full ISO timestamps ("2026-07-21T20:15:00Z"); normalize to a date.
    text = str(raw).strip()
    if "T" in text:
        text = text.split("T", 1)[0]
    return date.fromisoformat(text)


def _parse_results_field(game_type: str, raw_results: Any) -> tuple[list[int], list[int]]:
    """Split the API's `resultsJson` field into (main_numbers, euro_numbers).

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


class LottoApiClient:
    """Client for fetching draw results from the Lotto Open API."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{BASE_URL}/{path}"
        headers = {"Secret": self._api_key, "Accept": "application/json"}
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.get(url, headers=headers, params=params) as resp:
                    if resp.status in (401, 403):
                        raise LottoApiAuthError(
                            f"Lotto Open API odrzuciło klucz API (HTTP {resp.status})"
                        )
                    if resp.status != 200:
                        body = await resp.text()
                        raise LottoApiError(
                            f"Lotto Open API zwróciło błąd HTTP {resp.status}: {body[:200]}"
                        )
                    return await resp.json(content_type=None)
        except LottoApiError:
            raise
        except (ClientError, TimeoutError) as err:
            raise LottoApiError(f"Błąd komunikacji z Lotto Open API: {err}") from err

    async def async_verify_api_key(self) -> None:
        """Raise LottoApiAuthError/LottoApiError if the key doesn't work."""
        await self.async_get_last_results(GAME_EUROJACKPOT, size=1)

    async def async_get_last_results(self, game_type: str, size: int = 20) -> list[DrawResult]:
        payload = await self._get(
            "lotteries/draw-results/last-results",
            {"gameType": game_type, "index": 1, "size": size, "sort": "drawDate", "order": "DESC"},
        )

        items = payload
        if isinstance(payload, dict):
            for key in ("items", "results", "content", "data"):
                if key in payload and isinstance(payload[key], list):
                    items = payload[key]
                    break

        results: list[DrawResult] = []
        for item in items or []:
            try:
                main, euro = _parse_results_field(game_type, item["resultsJson"])
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
