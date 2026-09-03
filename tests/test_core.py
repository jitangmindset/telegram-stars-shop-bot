from decimal import Decimal

import pytest

from bot.handlers import calculate_total, format_money, normalize_username
from bot.keyboards import stars_keyboard


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@durov", "@durov"),
        ("durov", "@durov"),
        ("https://t.me/telegram", "@telegram"),
        ("bad-name", None),
        ("abc", None),
        ("_wrong", None),
        ("юзернейм", None),
    ],
)
def test_normalize_username(raw: str, expected: str | None) -> None:
    assert normalize_username(raw) == expected


def test_calculate_and_format_total() -> None:
    total = calculate_total(500, Decimal("1.75"))
    assert total == Decimal("875.00")
    assert format_money(total) == "875,00"


def test_admin_panel_button_is_visible_only_to_owner() -> None:
    customer_callbacks = [
        button.callback_data
        for row in stars_keyboard(is_owner=False).inline_keyboard
        for button in row
    ]
    owner_callbacks = [
        button.callback_data
        for row in stars_keyboard(is_owner=True).inline_keyboard
        for button in row
    ]

    assert "panel:main" not in customer_callbacks
    assert "panel:main" in owner_callbacks


def test_custom_presets_are_rendered() -> None:
    callbacks = [
        button.callback_data
        for row in stars_keyboard(presets=(25, 250, 1000, 2500)).inline_keyboard
        for button in row
    ]

    assert callbacks[:4] == ["stars:25", "stars:250", "stars:1000", "stars:2500"]
    assert "stars:custom" in callbacks
