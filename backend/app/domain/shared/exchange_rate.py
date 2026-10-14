"""Converting between USD and LBP.

Rates are always written as "LBP per 1 USD" (e.g. 89500), the way they are quoted in Lebanon.
"""

from decimal import Decimal

from app.domain.shared.currency import Currency
from app.domain.shared.errors import DomainError

MAX_RATE = Decimal("999999999999.999999")  # NUMERIC(18, 6)


class InvalidExchangeRate(DomainError):
    default_message = "The exchange rate must be a positive number of LBP per USD"


def validate_rate(lbp_per_usd: Decimal) -> None:
    if not 0 < lbp_per_usd <= MAX_RATE:
        raise InvalidExchangeRate


def convert(amount: Decimal, from_currency: Currency, to_currency: Currency, lbp_per_usd: Decimal) -> Decimal:
    """Exact conversion. Rounding happens once, when a total is shown, not per amount."""
    if from_currency is to_currency:
        return amount
    validate_rate(lbp_per_usd)
    if from_currency is Currency.USD:
        return amount * lbp_per_usd
    return amount / lbp_per_usd
