"""Static game rules for supported lottery games.

These are the fixed rules of the games themselves (how many numbers you pick,
from what range, and which match-counts are official prize tiers) - they do
not come from the Lotto Open API and never change per-draw.
"""
from __future__ import annotations

from dataclasses import dataclass

from .const import GAME_EUROJACKPOT, GAME_LOTTO

# Winning (main_matches, euro_matches) combinations for EuroJackpot, ranked
# best (1) to worst (12), per the official EuroJackpot prize plan.
EUROJACKPOT_PRIZE_TIERS: dict[tuple[int, int], int] = {
    (5, 2): 1,
    (5, 1): 2,
    (5, 0): 3,
    (4, 2): 4,
    (4, 1): 5,
    (3, 2): 6,
    (4, 0): 7,
    (2, 2): 8,
    (3, 1): 9,
    (3, 0): 10,
    (1, 2): 11,
    (2, 1): 12,
}

# Winning match-counts for standard Lotto (6 of 49).
LOTTO_PRIZE_TIERS: dict[int, int] = {6: 1, 5: 2, 4: 3, 3: 4}


@dataclass(frozen=True)
class GameRules:
    """Number-picking rules for a single game."""

    game_type: str
    numbers_count: int
    numbers_min: int
    numbers_max: int
    euro_count: int = 0
    euro_min: int = 0
    euro_max: int = 0

    def as_dict(self) -> dict:
        return {
            "game_type": self.game_type,
            "numbers_count": self.numbers_count,
            "numbers_min": self.numbers_min,
            "numbers_max": self.numbers_max,
            "euro_count": self.euro_count,
            "euro_min": self.euro_min,
            "euro_max": self.euro_max,
        }


GAME_RULES: dict[str, GameRules] = {
    GAME_LOTTO: GameRules(
        game_type=GAME_LOTTO,
        numbers_count=6,
        numbers_min=1,
        numbers_max=49,
    ),
    GAME_EUROJACKPOT: GameRules(
        game_type=GAME_EUROJACKPOT,
        numbers_count=5,
        numbers_min=1,
        numbers_max=50,
        euro_count=2,
        euro_min=1,
        euro_max=12,
    ),
}


def validate_numbers(
    game_type: str, numbers: list[int], euro_numbers: list[int] | None = None
) -> None:
    """Validate a set of coupon numbers against the game's rules.

    Raises ValueError with a human-readable reason if invalid.
    """
    rules = GAME_RULES.get(game_type)
    if rules is None:
        raise ValueError(f"Nieznany typ losowania: {game_type}")

    if len(numbers) != rules.numbers_count or len(set(numbers)) != len(numbers):
        raise ValueError(
            f"Wybierz dokładnie {rules.numbers_count} różnych liczb "
            f"({rules.numbers_min}-{rules.numbers_max})."
        )
    if any(n < rules.numbers_min or n > rules.numbers_max for n in numbers):
        raise ValueError(
            f"Liczby muszą być z zakresu {rules.numbers_min}-{rules.numbers_max}."
        )

    euro_numbers = euro_numbers or []
    if rules.euro_count:
        if len(euro_numbers) != rules.euro_count or len(set(euro_numbers)) != len(
            euro_numbers
        ):
            raise ValueError(
                f"Wybierz dokładnie {rules.euro_count} różnych liczb Euro "
                f"({rules.euro_min}-{rules.euro_max})."
            )
        if any(n < rules.euro_min or n > rules.euro_max for n in euro_numbers):
            raise ValueError(
                f"Liczby Euro muszą być z zakresu {rules.euro_min}-{rules.euro_max}."
            )
    elif euro_numbers:
        raise ValueError(f"{game_type} nie używa liczb Euro.")


def match_draw(
    game_type: str,
    coupon_numbers: list[int],
    coupon_euro_numbers: list[int],
    drawn_numbers: list[int],
    drawn_euro_numbers: list[int],
) -> dict:
    """Compare a coupon's numbers against a draw's results.

    Returns a dict with matched_numbers, matched_euro_numbers, is_win and
    prize_tier (int rank, lower is better, or None if not a winning combo).
    """
    matched_numbers = len(set(coupon_numbers) & set(drawn_numbers))
    matched_euro_numbers = len(set(coupon_euro_numbers) & set(drawn_euro_numbers))

    prize_tier: int | None
    if game_type == GAME_EUROJACKPOT:
        prize_tier = EUROJACKPOT_PRIZE_TIERS.get((matched_numbers, matched_euro_numbers))
    else:
        prize_tier = LOTTO_PRIZE_TIERS.get(matched_numbers)

    return {
        "matched_numbers": matched_numbers,
        "matched_euro_numbers": matched_euro_numbers,
        "is_win": prize_tier is not None,
        "prize_tier": prize_tier,
    }
