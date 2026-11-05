"""The scoring rule, on cases S1-S10 approved by the user on 2026-11-05. Do not change an expected value to make a
test pass. Nothing here touches a database."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.application.assistant.dtos import QueryResult, QuestionOutcome
from app.domain.assistant.answer import ModelReply, ReplyForm
from app.domain.assistant.conversation import Attempt, Step
from research.evaluation.questions import Accepted, PilotQuestion
from research.evaluation.scoring import is_ordered, results_match, score

GROCERIES = "SELECT currency, SUM(amount) AS total_spent FROM category_spending WHERE category = 'Groceries' GROUP BY currency"
LATEST = "SELECT receipt_date, vendor, unit_price FROM purchases WHERE item_name = 'laban' ORDER BY receipt_date DESC LIMIT 1"


def result(*rows, columns=None) -> QueryResult:
    width = len(rows[0]) if rows else 0
    return QueryResult("SELECT ...", columns or [f"c{i}" for i in range(width)], list(rows), False)


def used(sql="SELECT ...") -> Attempt:
    return Attempt(Step.SQL, "m", sql)


def refused(sql="SELECT ...") -> Attempt:
    return Attempt(Step.SQL, "m", sql, "Item names must match exactly")


def question(*accept: Accepted) -> PilotQuestion:
    return PilotQuestion("T1", "q", "en", "total", accept)


def answered(rows: QueryResult, *attempts: Attempt) -> QuestionOutcome:
    return QuestionOutcome(rows, None, attempts or (used(),))


def replied(form: ReplyForm) -> QuestionOutcome:
    return QuestionOutcome(None, ModelReply(form, "text"), (used(),))


USD_8 = result(("USD", Decimal("8.00")))


def test_s1_an_extra_column_is_ignored():
    assert results_match(USD_8, result(("USD", Decimal("8.00"), Decimal("8.00"))))


def test_s2_a_different_number_of_rows_is_wrong():
    two_currencies = result(("USD", Decimal("13.50")), ("LBP", Decimal("1450000")))
    assert not results_match(two_currencies, result((Decimal("29.70"),)))


def test_s3_a_different_amount_is_wrong():
    assert not results_match(result((Decimal("6.00"),)), result((Decimal("51.00"),)))


def test_s4_the_wrong_row_for_latest_is_wrong():
    want = result((date(2026, 11, 1), "Spinneys", Decimal("3.75")))
    got = result((date(2026, 10, 25), "Spinneys", Decimal("3.75")))
    assert is_ordered(LATEST)
    assert not results_match(want, got, ordered=True)


def test_s5_row_order_is_ignored_without_order_by_and_limit():
    rows = [("Dining", Decimal("32")), ("Groceries", Decimal("85.06")), ("Health", Decimal("6.70")),
            ("Household", Decimal("10"))]  # fmt: skip
    assert not is_ordered(GROCERIES)
    assert results_match(result(*rows), result(*reversed(rows)))


def test_order_matters_with_order_by_and_limit():
    top = [("Groceries", Decimal("85.06")), ("Dining", Decimal("32"))]
    assert not results_match(result(*top), result(*reversed(top)), ordered=True)


def test_s6_empty_null_and_zero_all_mean_nothing_matched():
    assert results_match(result(), result((Decimal("0.00"),)))
    assert results_match(result((None,)), result())
    assert not results_match(result(), result((Decimal("5.00"),)))


def test_amounts_are_compared_to_the_cent_and_names_do_not_matter():
    assert results_match(result((Decimal("16.2011173"),), columns=["total"]),
                         result((Decimal("16.20"),), columns=["spent"]))  # fmt: skip
    assert results_match(result((4,)), result((Decimal("4"),)))


def test_a_month_matches_as_a_date_or_a_timestamp_at_midnight():
    beirut = timezone(timedelta(hours=3))
    assert results_match(result((date(2026, 10, 1), Decimal("32"))),
                         result((datetime(2026, 10, 1, tzinfo=beirut), Decimal("32"))))  # fmt: skip


def test_values_must_stay_in_the_same_rows():
    want = result(("Spinneys", Decimal("0.37")), ("Carrefour", Decimal("0.36")))
    swapped = result(("Spinneys", Decimal("0.36")), ("Carrefour", Decimal("0.37")))
    assert not results_match(want, swapped)


def test_s7_a_query_when_a_clarifying_question_was_expected_is_a_guess():
    s = score(question(Accepted(reply=ReplyForm.CLARIFY)), answered(USD_8), [None])
    assert (s.correct, s.reason) == (False, "guessed with a query, expected CLARIFY")


def test_s8_a_clarifying_question_when_an_answer_was_expected_is_wrong():
    s = score(question(Accepted(sql=GROCERIES)), replied(ReplyForm.CLARIFY), [USD_8])
    assert (s.correct, s.reason) == (False, "asked a clarifying question instead of answering")


def test_s9_two_refusals_are_wrong_with_the_reason():
    s = score(question(Accepted(sql=GROCERIES)), QuestionOutcome(None, None, (refused(), refused())), [USD_8])
    assert (s.correct, s.reason) == (False, "failed: Item names must match exactly")


def test_s10_right_after_the_repair_is_not_right_on_the_first_try():
    s = score(question(Accepted(sql=GROCERIES)), answered(USD_8, refused(), used()), [USD_8])
    assert (s.correct, s.first_try) == (True, False)
    s = score(question(Accepted(sql=GROCERIES)), answered(USD_8), [USD_8])
    assert (s.correct, s.first_try) == (True, True)


def test_any_accepted_answer_counts():  # P37: the raw chicken, or a clarifying question
    chicken = question(Accepted(sql=GROCERIES), Accepted(reply=ReplyForm.CLARIFY))
    assert score(chicken, replied(ReplyForm.CLARIFY), [USD_8, None]).correct
    assert score(chicken, answered(USD_8), [USD_8, None]).correct
    assert not score(chicken, answered(result(("USD", Decimal("29.30")))), [USD_8, None]).correct


def test_the_reply_type_must_match():
    s = score(question(Accepted(reply=ReplyForm.UNSUPPORTED)), replied(ReplyForm.REPLY), [None])
    assert (s.correct, s.reason) == (False, "replied REPLY, expected UNSUPPORTED")


def test_columns_may_come_in_any_order_with_extra_ones_first():
    want = result(("USD", Decimal("8.00")), ("LBP", Decimal("530000")))
    got = result((Decimal("8.00"), Decimal("8.00"), "USD"), (Decimal("5.92"), Decimal("530000"), "LBP"))
    assert results_match(want, got)
