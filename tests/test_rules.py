"""Unit tests for game rules: number validation and draw matching."""
import pytest

from custom_components.lotto.const import GAME_EUROJACKPOT, GAME_LOTTO
from custom_components.lotto.rules import match_draw, validate_numbers


def test_validate_numbers_accepts_valid_lotto_coupon():
    validate_numbers(GAME_LOTTO, [1, 2, 3, 4, 5, 6])


def test_validate_numbers_rejects_wrong_count():
    with pytest.raises(ValueError):
        validate_numbers(GAME_LOTTO, [1, 2, 3])


def test_validate_numbers_rejects_duplicates():
    with pytest.raises(ValueError):
        validate_numbers(GAME_LOTTO, [1, 1, 2, 3, 4, 5])


def test_validate_numbers_rejects_out_of_range():
    with pytest.raises(ValueError):
        validate_numbers(GAME_LOTTO, [1, 2, 3, 4, 5, 50])


def test_validate_numbers_eurojackpot_requires_euro_numbers():
    validate_numbers(GAME_EUROJACKPOT, [1, 2, 3, 4, 5], [1, 2])
    with pytest.raises(ValueError):
        validate_numbers(GAME_EUROJACKPOT, [1, 2, 3, 4, 5], [1])


def test_validate_numbers_lotto_rejects_euro_numbers():
    with pytest.raises(ValueError):
        validate_numbers(GAME_LOTTO, [1, 2, 3, 4, 5, 6], [1, 2])


def test_match_draw_lotto_jackpot():
    result = match_draw(GAME_LOTTO, [1, 2, 3, 4, 5, 6], [], [1, 2, 3, 4, 5, 6], [])
    assert result == {
        "matched_numbers": 6,
        "matched_euro_numbers": 0,
        "is_win": True,
        "prize_tier": 1,
    }


def test_match_draw_lotto_below_minimum_tier_is_not_a_win():
    result = match_draw(GAME_LOTTO, [1, 2, 3, 4, 5, 6], [], [1, 2, 9, 10, 11, 12], [])
    assert result["matched_numbers"] == 2
    assert result["is_win"] is False
    assert result["prize_tier"] is None


def test_match_draw_eurojackpot_jackpot():
    result = match_draw(
        GAME_EUROJACKPOT, [1, 2, 3, 4, 5], [1, 2], [1, 2, 3, 4, 5], [1, 2]
    )
    assert result["is_win"] is True
    assert result["prize_tier"] == 1


def test_match_draw_eurojackpot_lowest_paying_tier():
    # 2 main + 1 euro is the lowest official winning combination.
    result = match_draw(
        GAME_EUROJACKPOT, [1, 2, 3, 4, 5], [1, 2], [1, 2, 30, 31, 32], [1, 9]
    )
    assert result["matched_numbers"] == 2
    assert result["matched_euro_numbers"] == 1
    assert result["is_win"] is True
    assert result["prize_tier"] == 12
