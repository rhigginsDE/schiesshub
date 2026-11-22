"""Zeiten in der Ablauf-Kurzform der Ausschreibung: ab 60 s in Minuten."""

from decimal import Decimal

import pytest

from app.modules.turnier.announcement import duration_text


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (10, "10 s"),
        (7.5, "7,5 s"),
        (Decimal("59.99"), "59,99 s"),
        (60, "1 Min."),
        (90, "1 Min. 30 s"),
        (300, "5 Min."),
        (150.5, "2 Min. 30,5 s"),
        (3600, "60 Min."),
    ],
)
def test_duration_text(seconds: float | Decimal, text: str) -> None:
    assert duration_text(seconds) == text
