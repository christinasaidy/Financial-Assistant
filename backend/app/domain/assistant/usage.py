"""What answering a question used, what it is estimated to cost, and the Standard mode's limits (2026-11-23).

- Tokens are what the provider reported. A call that reported nothing makes the turn's tokens and cost unknown
  (None), never 0. Beta's model reports no usage, so a Beta question's tokens are always unknown.
- The cost is an estimate from the configured prices (STANDARD_PRICE_*: not constants in the code), saved with the
  pricing version it used, so an old estimate stays what it was when prices change. A cache write whose lifetime is
  not reported is priced at the dearer 1-hour rate: an upper bound, never an undercount.
- Limits (decided with the owner on 2026-11-23): 30 Standard questions per user per day and a $10 app-wide monthly cap,
  both counted in Beirut time. A question whose cost is not known yet (still running, or it failed without a
  report) counts at the reserve, the most one question is expected to cost, so questions running at the same time
  cannot all slip under the cap.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class Pricing:
    """Dollars per million tokens."""

    version: str
    input: Decimal
    output: Decimal
    cache_write_5m: Decimal
    cache_write_1h: Decimal
    cache_read: Decimal


@dataclass(frozen=True)
class CallTokens:
    """One model call's reported tokens (None: not reported)."""

    input: int | None
    output: int | None
    cache_write: int | None = None  # both lifetimes together
    cache_write_5m: int | None = None
    cache_write_1h: int | None = None
    cache_read: int | None = None


@dataclass(frozen=True)
class TurnUsage:
    model_calls: int
    input_tokens: int | None
    output_tokens: int | None
    cache_write_tokens: int | None
    cache_read_tokens: int | None
    dollars: Decimal | None  # None: not known (a call reported nothing, or no prices are configured)
    pricing_version: str | None


@dataclass(frozen=True)
class StandardQuota:
    daily_questions_per_user: int | None  # None: no per-user limit
    monthly_cap_dollars: Decimal | None  # None: no cap
    reserve_dollars: Decimal  # what a question of unknown cost counts as
    time_zone: str  # whose days and months count


def turn_usage(calls: Sequence[CallTokens | None], pricing: Pricing | None) -> TurnUsage:
    def total(values: list[int | None]) -> int | None:
        return None if not values or any(v is None for v in values) else sum(values)

    known = [call for call in calls if call is not None]
    unknown = len(known) < len(calls)
    sums = {
        "input": total([c.input for c in known]),
        "output": total([c.output for c in known]),
        "cache_write": total([c.cache_write or 0 for c in known]),
        "cache_read": total([c.cache_read or 0 for c in known]),
    }
    if unknown:
        sums = dict.fromkeys(sums)
    dollars = None
    if pricing is not None and not unknown and sums["input"] is not None and sums["output"] is not None:
        dollars = sum((_call_dollars(call, pricing) for call in known), Decimal(0)).quantize(Decimal("0.000001"))
    return TurnUsage(len(calls), sums["input"], sums["output"], sums["cache_write"], sums["cache_read"], dollars,
                     pricing.version if dollars is not None else None)  # fmt: skip


def _call_dollars(call: CallTokens, pricing: Pricing) -> Decimal:
    if call.cache_write_5m is not None or call.cache_write_1h is not None:
        writes = ((call.cache_write_5m or 0) * pricing.cache_write_5m
                  + (call.cache_write_1h or 0) * pricing.cache_write_1h)  # fmt: skip
    else:  # the lifetime was not reported: the 1-hour rate, the dearer one
        writes = (call.cache_write or 0) * pricing.cache_write_1h
    tokens = (call.input or 0) * pricing.input + (call.output or 0) * pricing.output + (call.cache_read or 0) * \
        pricing.cache_read  # fmt: skip
    return (tokens + writes) / MILLION


def over_cap(spent: Decimal, unpriced: int, quota: StandardQuota) -> bool:
    """Whether one more question could pass the monthly cap: what is known, plus the reserve for each question of
    unknown cost and for this one."""
    if quota.monthly_cap_dollars is None:
        return False
    return spent + quota.reserve_dollars * (unpriced + 1) > quota.monthly_cap_dollars
