"""Tokens, cost estimates and the monthly cap's arithmetic (AC-19: unknown usage is never counted as zero)."""

from decimal import Decimal

from app.domain.assistant.usage import CallTokens, Pricing, StandardQuota, over_cap, turn_usage

PRICES = Pricing("test-prices", Decimal("2"), Decimal("10"), Decimal("2.5"), Decimal("4"), Decimal("0.1"))


def test_a_turns_tokens_are_summed_and_priced_by_cache_lifetime():
    calls = [CallTokens(4, 30, 43_139, 0, 43_139, 0), CallTokens(4, 96, 179, 179, 0, 43_002)]
    usage = turn_usage(calls, PRICES)
    assert (usage.model_calls, usage.input_tokens, usage.output_tokens) == (2, 8, 126)
    assert (usage.cache_write_tokens, usage.cache_read_tokens) == (43_318, 43_002)
    # (8*2 + 126*10 + 43139*4 + 179*2.5 + 43002*0.1) / 1,000,000 = 178,579.7 / 1,000,000, to 6 places
    assert usage.dollars == Decimal("0.178580")
    assert usage.pricing_version == "test-prices"


def test_a_cache_write_of_unreported_lifetime_is_priced_at_the_dearer_rate():
    usage = turn_usage([CallTokens(0, 0, 1_000_000)], PRICES)
    assert usage.dollars == Decimal("4.000000")


def test_a_call_that_reported_nothing_makes_the_turn_unknown_not_zero():
    usage = turn_usage([CallTokens(4, 30, 0, 0, 0, 0), None], PRICES)
    assert usage.model_calls == 2
    assert (usage.input_tokens, usage.output_tokens, usage.dollars, usage.pricing_version) == (None, None, None, None)
    assert turn_usage([CallTokens(None, 30)], PRICES).dollars is None


def test_without_prices_the_tokens_are_kept_but_the_cost_is_unknown():
    usage = turn_usage([CallTokens(4, 30, 0, 0, 0, 0)], None)
    assert (usage.input_tokens, usage.dollars, usage.pricing_version) == (4, None, None)


def test_the_cap_counts_the_unknown_questions_and_this_one_at_the_reserve():
    quota = StandardQuota(30, Decimal("10"), Decimal("0.50"), "Asia/Beirut")
    assert not over_cap(Decimal("9.50"), 0, quota)  # 9.50 + 0.50 is exactly the cap
    assert over_cap(Decimal("9.51"), 0, quota)
    assert over_cap(Decimal("9.00"), 2, quota)  # two running questions at the reserve: 9 + 1.5 > 10
    assert not over_cap(Decimal("1000"), 9, StandardQuota(30, None, Decimal("0.50"), "Asia/Beirut"))  # no cap
