"""Reading the model's replies and checking the numbers in its answers. Decisions and examples approved by the user
on 2026-11-03; do not change an expected value to make a test pass."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.assistant import answer as answers
from app.domain.assistant.answer import ReplyForm, check_numbers, read_reply
from app.domain.assistant.errors import UnusableReply

# --- The four reply forms ---


@pytest.mark.parametrize(
    ("raw", "form", "text"),
    [
        ("SELECT SUM(total) FROM receipts", ReplyForm.SQL, "SELECT SUM(total) FROM receipts"),
        ("  select 1  \n", ReplyForm.SQL, "select 1"),
        ("```sql\nSELECT 1\n```", ReplyForm.SQL, "SELECT 1"),
        ("```\nSELECT 1\n```", ReplyForm.SQL, "SELECT 1"),
        ("WITH t AS (SELECT 1) SELECT * FROM t", ReplyForm.SQL, "WITH t AS (SELECT 1) SELECT * FROM t"),
        ("CLARIFY: Did you mean laban?", ReplyForm.CLARIFY, "Did you mean laban?"),
        ("clarify:   The last what?", ReplyForm.CLARIFY, "The last what?"),
        ("UNSUPPORTED", ReplyForm.UNSUPPORTED, ""),
        ("Unsupported.", ReplyForm.UNSUPPORTED, ""),
        ("REPLY: Hi! Ask me about your spending.", ReplyForm.REPLY, "Hi! Ask me about your spending."),
    ],
)
def test_the_four_forms_are_read(raw, form, text):
    assert read_reply(raw) == answers.ModelReply(form, text)


@pytest.mark.parametrize(
    "raw",
    [None, "", "   ", "You spent $8.00", "Sure! SELECT 1", "CLARIFY:", "REPLY:   ", "UNSUPPORTED because budgets"],
)
def test_anything_else_cannot_be_used(raw):
    with pytest.raises(UnusableReply):
        read_reply(raw)


# --- Numbers: only standalone numbers are checked (round 3, Q2) ---


def test_standalone_numbers_are_found_with_separators_and_decimals():
    assert answers.numbers_in("$13.50 and 1,450,000 LBP, about $29.70 in total.") == [
        Decimal("13.50"), Decimal("1450000"), Decimal("29.70"),
    ]  # fmt: skip


def test_digits_inside_arabizi_words_are_letters_not_numbers():
    assert answers.numbers_in("Dafa3et $3.75 3al laban hal sha3er, 2addesh ma7al") == [Decimal("3.75")]


def test_e8_arabizi_answer_passes_and_a_wrong_amount_does_not():
    allowed = [Decimal("3.75"), Decimal("3.75")]
    check_numbers("Dafa3et $3.75 3al laban hal shahr.", allowed, "the result")
    with pytest.raises(UnusableReply, match="3.80"):
        check_numbers("Dafa3et $3.80 3al laban hal shahr.", allowed, "the result")


def test_rounding_to_the_places_written_matches():
    allowed = [Decimal("16.2011173184"), Decimal("1000.000")]
    check_numbers("about $16.20, or about $16, for 1000 g", allowed, "the result")


def test_e2_combined_total_comes_from_the_usd_column_total():
    columns = ["currency", "total_spent", "total_spent_usd"]
    rows = [("USD", Decimal("13.50"), Decimal("13.50")), ("LBP", Decimal("1450000"), Decimal("16.2011173184"))]
    totals = answers.column_totals(columns, rows)
    allowed = [*answers.result_numbers(rows), *totals.values()]
    check_numbers(
        "Last month you spent $13.50 and 1,450,000 LBP on Groceries, about $29.70 in total.", allowed, "the result"
    )
    with pytest.raises(UnusableReply, match="29.71"):  # E19: a wrong rounding is caught
        check_numbers("You spent $13.50 and 1,450,000 LBP, about $29.71 in total.", allowed, "the result")


def test_column_totals_need_two_rows_and_skip_text_and_dates():
    rows = [("USD", Decimal("1.25"), date(2026, 11, 1)), ("LBP", 3, date(2026, 10, 25))]
    assert answers.column_totals(["currency", "amount", "day"], rows) == {"amount": Decimal("4.25")}
    assert answers.column_totals(["amount"], [(Decimal("8.00"),)]) == {}


def test_dates_in_the_result_allow_their_day_month_and_year():
    allowed = answers.result_numbers([(date(2026, 11, 1), "Spinneys", Decimal("3.75"))])
    check_numbers("You last paid $3.75 at Spinneys on 1 November 2026 (1/11).", allowed, "the result")


def test_numbers_inside_text_cells_are_allowed():
    check_numbers("You bought 7 up twice.", answers.result_numbers([("7 up", 2)]), "the result")


def test_e5_numbers_written_in_the_sql_are_allowed():
    sql = "SELECT ROUND(AVG(unit_price / size_amount * 100), 2) AS average_price_per_100 FROM purchases"
    allowed = [Decimal("0.36"), *answers.numbers_in(sql)]
    check_numbers("Per 100 g of laban you paid on average $0.36.", allowed, "the result")


def test_clarify_and_reply_may_only_repeat_numbers_from_the_question():
    question = "how much did I spend on my top 3 items?"
    check_numbers("Your top 3 items by amount or by count?", answers.numbers_in(question), "the question")
    with pytest.raises(UnusableReply, match="50"):
        check_numbers("Sure! You spent about $50 this week.", answers.numbers_in("hi"), "the question")


# --- Results and fixed messages ---


@pytest.mark.parametrize("rows", [[], [(None,)], [(None, None), (None, None)]])
def test_no_rows_or_only_nulls_means_nothing_matched(rows):
    assert answers.is_empty_result(rows)


def test_a_zero_is_still_an_answer():
    assert not answers.is_empty_result([(Decimal(0),)])


def test_fixed_messages_are_the_approved_texts():
    assert answers.NO_MATCHES == "I couldn't find any confirmed receipts matching that."
    assert answers.UNSUPPORTED == (
        "I can answer questions about your confirmed receipts: what you spent, on what, where and when, "
        "and what you paid for items. For budgets, see the Budgets screen."
    )
    assert answers.FAILURE == "Sorry, I couldn't answer that. Try asking it a different way."
    assert answers.NOT_AVAILABLE == "The assistant isn't available right now."
    assert answers.TABLE_INTRO == "Here are the results:"
    assert answers.review_note(1) == "1 receipt is still waiting for your review and isn't included."
    assert answers.review_note(2) == "2 receipts are still waiting for your review and aren't included."


def test_a_table_is_saved_as_exact_text():
    rows = [(date(2026, 10, 5), "Spinneys", Decimal("16.2011173184"), None, 2)]
    assert answers.as_text(rows) == (("2026-10-05", "Spinneys", "16.2011173184", None, "2"),)
