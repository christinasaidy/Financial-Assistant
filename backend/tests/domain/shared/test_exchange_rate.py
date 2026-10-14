from decimal import Decimal

import pytest

from app.domain.shared.currency import Currency
from app.domain.shared.exchange_rate import InvalidExchangeRate, convert, validate_rate

RATE = Decimal("89500")


def test_usd_to_lbp_and_back():
    assert convert(Decimal("2"), Currency.USD, Currency.LBP, RATE) == Decimal("179000")
    assert convert(Decimal("179000"), Currency.LBP, Currency.USD, RATE) == Decimal("2")


def test_same_currency_is_unchanged_even_without_a_usable_rate():
    assert convert(Decimal("5"), Currency.USD, Currency.USD, Decimal(0)) == Decimal("5")


@pytest.mark.parametrize("bad", [Decimal(0), Decimal(-1), Decimal("1e15")])
def test_impossible_rates_are_rejected(bad):
    with pytest.raises(InvalidExchangeRate):
        validate_rate(bad)
    with pytest.raises(InvalidExchangeRate):
        convert(Decimal(1), Currency.USD, Currency.LBP, bad)
