"""The question flow through the real API and database (assistant phase 3). The test data and the worked examples
E1-E21 were approved by the user on 2026-11-03; do not change an expected value to make a test pass.

The language model is a fake that returns the replies written below, so these tests check everything the code
does with a reply (the checks, the date, the query, the sources, the number check, what is saved), never whether a
real model would write it. That is what the phase 4 evaluation measures.

One difference from the examples as approved: there is no "Restaurants" category (the defaults are Groceries,
Dining, ...), so R6 (Barbar) is Dining and E17 asks about dining.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.app import create_app
from app.application.assistant.assistant_service import AssistantService
from app.domain.assistant import answer as answers
from app.domain.assistant.conversation import AnswerKind, Step
from app.domain.receipts.extraction import ExtractedLine, ExtractedReceipt
from app.infrastructure.config import Settings
from app.infrastructure.database.connection import create_db_engine
from app.infrastructure.database.readonly_query_runner import SqlReadOnlyQueryRunner
from app.infrastructure.database.unit_of_work import SqlUnitOfWorkFactory
from app.infrastructure.language_model.unavailable_assistant_model import UnavailableAssistantModel
from app.infrastructure.sql.query_rules import SqlGlotQueryRules
from app.infrastructure.sql.sql_guard import SqlGlotGuard
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.fakes import FakeAssistantModel, FakeReceiptExtractor

TODAY = date(2026, 11, 3)
THIS_MONTH = "receipt_date >= date_trunc('month', CURRENT_DATE) AND receipt_date < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month'"  # noqa: E501
LAST_MONTH = "receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month' AND receipt_date < date_trunc('month', CURRENT_DATE)"  # noqa: E501
MONEY = "SELECT currency, SUM({amount}) AS total_spent, SUM({amount}_usd) AS total_spent_usd FROM {view} WHERE {where} GROUP BY currency"  # noqa: E501

E1_SQL = MONEY.format(amount="amount", view="category_spending", where=f"category = 'Groceries' AND {THIS_MONTH}")
E2_SQL = MONEY.format(amount="amount", view="category_spending", where=f"category = 'Groceries' AND {LAST_MONTH}")
E3_SQL = MONEY.format(amount="line_total", view="purchases", where="item_name = 'laban'")
E4_SQL = ("SELECT receipt_date, vendor, currency, unit_price AS latest_price, size_amount, size_unit FROM purchases "
          "WHERE item_name = 'laban' ORDER BY receipt_date DESC LIMIT 1")  # fmt: skip
E5_SQL = ("SELECT vendor, currency, size_unit, COUNT(*) AS purchase_count, MIN(receipt_date) AS first_date, "
          "MAX(receipt_date) AS last_date, ROUND(AVG(unit_price / size_amount * 100), 2) AS average_price_per_100 "
          "FROM purchases WHERE item_name = 'laban' AND vendor IN ('Spinneys', 'Carrefour') "
          "AND size_amount IS NOT NULL GROUP BY vendor, currency, size_unit")  # fmt: skip
E6_SQL = ("SELECT vendor, currency, COUNT(*) AS purchase_count, ROUND(AVG(unit_price), 2) AS average_price, "
          "MAX(receipt_date) AS last_date, COUNT(size_amount) AS with_size_count FROM purchases "
          "WHERE item_name = 'bread' AND vendor IN ('Spinneys', 'Carrefour') GROUP BY vendor, currency")  # fmt: skip
E7_SQL = MONEY.format(amount="line_total", view="purchases", where="item_name = 'water'")
E8_SQL = MONEY.format(amount="line_total", view="purchases", where=f"item_name = 'laban' AND {THIS_MONTH}")
E13_SQL = MONEY.format(amount="total", view="receipts", where=THIS_MONTH)
E17_SQL = MONEY.format(amount="amount", view="category_spending",
                       where="category = 'Dining' AND receipt_date >= '2026-09-01' AND receipt_date < '2026-10-01'")

E1_ANSWER = "You spent $8.00 on Groceries this month."
E2_ANSWER = "Last month you spent $13.50 and 1,450,000 LBP on Groceries, about $29.70 in total."


# --- Setup ---


@pytest.fixture
def settings(engine):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")
    if not settings.readonly_database_url:
        if __import__("os").environ.get("CI"):
            raise RuntimeError("READONLY_DATABASE_URL must be set in CI")
        pytest.skip("READONLY_DATABASE_URL is not set (the ai_readonly role's connection)")
    return settings


@pytest.fixture
def model():
    return FakeAssistantModel()


@pytest.fixture
def extractor():
    return FakeReceiptExtractor()


@pytest.fixture
def container(settings, model, extractor, tmp_path):
    return build_container(settings, extractor=extractor, storage=LocalFileStorage(tmp_path), today=lambda: TODAY,
                           assistant_model=model)  # fmt: skip


@pytest.fixture
def client(container):
    return TestClient(create_app(container))


@pytest.fixture
def sign_in(client, engine):
    emails: list[str] = []

    def _sign_in() -> tuple[dict[str, str], int]:
        email = f"{uuid.uuid4()}@test.local"
        emails.append(email)
        body = {"email": email, "password": "correct-horse"}
        assert client.post("/auth/register", json=body).status_code == 201
        result = client.post("/auth/login", json=body).json()
        return {"Authorization": f"Bearer {result['access_token']}"}, result["user"]["id"]

    yield _sign_in
    with engine.begin() as conn:
        for email in emails:
            conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


def add(client, headers, day, vendor, currency, total, category, lines=()):
    """A confirmed receipt. `lines` are (name, brand, size, unit, quantity, unit_price, line_total)."""
    categories = {c["name"]: c["id"] for c in client.get("/categories", headers=headers).json()}
    body = {
        "vendor_name": vendor, "receipt_date": day, "currency": currency, "total": total,
        "primary_category_id": categories[category], "lbp_per_usd": "89500",
        "lines": [
            {"description": name.upper(), "normalized_name": name, "brand": brand, "size_amount": size,
             "size_unit": unit, "quantity": quantity, "unit_price": price, "line_total": line_total}
            for name, brand, size, unit, quantity, price, line_total in lines
        ],
    }  # fmt: skip
    response = client.post("/receipts/manual", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def alice(client, sign_in):
    """The approved test data (rate 89,500 LBP per USD, today 2026-11-03)."""
    headers, user_id = sign_in()
    r = {
        "R1": add(client, headers, "2026-10-05", "Spinneys", "USD", "6.50", "Groceries", [
            ("laban", "taanayel", "1000", "g", "1", "3.50", "3.50"),
            ("water", "sohat", "1500", "ml", "6", "0.50", "3.00")]),
        "R2": add(client, headers, "2026-10-12", "Carrefour", "USD", "7.00", "Groceries", [
            ("laban", "taanayel", "500", "g", "1", "2.00", "2.00"),
            ("laban", None, None, None, "1", "4.00", "4.00"),
            ("bread", None, None, None, "1", "1.00", "1.00")]),
        "R3": add(client, headers, "2026-10-18", "Bou Khalil", "USD", "45.00", "Household", [
            ("water heater", None, None, None, "1", "45.00", "45.00")]),
        "R4": add(client, headers, "2026-10-25", "Spinneys", "LBP", "1450000", "Groceries", [
            ("laban", "taanayel", "1000", "g", "2", "325000", "650000"),
            ("bread", None, None, None, "4", "200000", "800000")]),
        "R5": add(client, headers, "2026-11-01", "Spinneys", "USD", "8.00", "Groceries", [
            ("laban", "taanayel", "1000", "g", "1", "3.75", "3.75"),
            ("water", "sohat", "1500", "ml", "6", "0.50", "3.00"),
            ("bread", None, None, None, "1", "1.25", "1.25")]),
        "R6": add(client, headers, "2026-11-02", "Barbar", "USD", "14.00", "Dining"),
    }  # fmt: skip
    return headers, user_id, r


@pytest.fixture
def bob(client, sign_in):
    headers, user_id = sign_in()
    b = {
        "B1": add(client, headers, "2026-11-01", "Zaatar w Zeit", "USD", "500.00", "Dining", [
            ("manakish", None, None, None, "1", "500.00", "500.00")]),
        "B2": add(client, headers, "2026-11-01", "Spinneys", "USD", "300.00", "Groceries", [
            ("laban", None, None, None, "1", "300.00", "300.00")]),
    }  # fmt: skip
    return headers, user_id, b


def ask(client, headers, question, conversation_id=None) -> dict:
    body = {"question": question, "conversation_id": conversation_id}
    response = client.post("/assistant/ask", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def sources(answer: dict) -> list[int]:
    return [source["receipt_id"] for source in answer["source_receipts"]]


def saved_details(container, user_id, answer):
    view = container.assistant.open_conversation(user_id, answer["conversation_id"])
    return next(m.details for m in view.messages if m.id == answer["id"])


# --- E1, E2: a total by category, and a follow-up ---


def test_e1_groceries_this_month(client, model, alice):
    headers, _, r = alice
    model.sql_replies, model.answer_replies = [E1_SQL], [E1_ANSWER]

    answer = ask(client, headers, "How much did I spend on groceries this month?")

    assert (answer["kind"], answer["content"]) == ("answer", E1_ANSWER)
    assert sources(answer) == [r["R5"]]
    assert "CAST('2026-11-03' AS DATE)" in answer["sql"] and "CURRENT_DATE" not in answer["sql"]
    assert "Row: USD | 8.00 | 8.00" in model.answer_prompts[0]


def test_e2_and_last_month_uses_the_earlier_question_and_sql_never_its_numbers(client, model, alice):
    headers, _, r = alice
    model.sql_replies, model.answer_replies = [E1_SQL, E2_SQL], [E1_ANSWER, E2_ANSWER]
    first = ask(client, headers, "How much did I spend on groceries this month?")

    answer = ask(client, headers, "and last month?", first["conversation_id"])

    assert answer["conversation_id"] == first["conversation_id"]
    assert (answer["kind"], answer["content"]) == ("answer", E2_ANSWER)
    assert sources(answer) == [r["R1"], r["R2"], r["R4"]]  # not R3's water heater (Household)
    prompt = model.sql_prompts[1]
    assert f"Question: How much did I spend on groceries this month?\nReply: {E1_SQL}" in prompt
    assert "8.00" not in prompt
    assert prompt.endswith("Question: and last month?\nReply:")
    assert "Column totals: total_spent_usd = 29.70" in model.answer_prompts[1]


# --- E3-E8: items and prices ---


def test_e3_laban_spend(client, model, alice, bob):
    headers, _, r = alice
    expected = "You spent $13.25 and 650,000 LBP on laban, about $20.51 in total."
    model.sql_replies, model.answer_replies = [E3_SQL], [expected]

    answer = ask(client, headers, "How much did I spend on laban?")

    assert answer["content"] == expected
    assert sources(answer) == [r["R1"], r["R2"], r["R4"], r["R5"]]  # never Bob's B2 ($300 of laban)
    assert "Row: USD | 13.25 | 13.25" in model.answer_prompts[0]


def test_e4_latest_price_is_based_on_the_one_purchase_shown(client, model, alice):
    headers, _, r = alice
    expected = "You last paid $3.75 for laban (1000 g) at Spinneys on 1 November 2026."
    model.sql_replies, model.answer_replies = [E4_SQL], [expected]

    answer = ask(client, headers, "How much did I pay for laban last time?")

    assert answer["content"] == expected
    assert sources(answer) == [r["R5"]]


def test_e5_vendor_comparison_per_size(client, model, alice):
    headers, _, r = alice
    expected = (
        "Per 100 g of laban, you paid on average $0.36 at Spinneys (2 purchases, 5 October to 1 November 2026) "
        "and $0.40 at Carrefour (1 purchase, 12 October 2026). You also paid 32,500 LBP per 100 g at Spinneys once "
        "(25 October 2026). This compares only your own purchases with a known size."
    )
    model.sql_replies, model.answer_replies = [E5_SQL], [expected]

    answer = ask(client, headers, "Is laban cheaper at Spinneys or Carrefour?")

    assert answer["content"] == expected  # "100" is allowed because it is written in the SQL
    assert sources(answer) == [r["R1"], r["R2"], r["R4"], r["R5"]]
    prompt = model.answer_prompts[0]
    assert "Row: Spinneys | USD | g | 2 | 2026-10-05 | 2026-11-01 | 0.36" in prompt
    assert "Row: Carrefour | USD | g | 1 | 2026-10-12 | 2026-10-12 | 0.40" in prompt
    assert "Row: Spinneys | LBP | g | 1 | 2026-10-25 | 2026-10-25 | 32500.00" in prompt


def test_e6_vendor_comparison_without_sizes(client, model, alice):
    headers, _, r = alice
    expected = (
        "You paid $1.25 for bread at Spinneys (1 November 2026) and $1.00 at Carrefour (12 October 2026). "
        "Your receipts don't show sizes, so the packs may differ. You also paid 200,000 LBP at Spinneys on "
        "25 October 2026."
    )
    model.sql_replies, model.answer_replies = [E6_SQL], [expected]

    answer = ask(client, headers, "Compare bread prices at Spinneys and Carrefour.")

    assert answer["content"] == expected
    assert sources(answer) == [r["R2"], r["R4"], r["R5"]]
    assert "Row: Spinneys | LBP | 1 | 200000.00 | 2026-10-25 | 0" in model.answer_prompts[0]


def test_e7_water_is_not_the_water_heater(client, model, alice):
    headers, _, r = alice
    model.sql_replies, model.answer_replies = [E7_SQL], ["You spent $6.00 on water."]

    answer = ask(client, headers, "How much did I spend on water?")

    assert answer["content"] == "You spent $6.00 on water."
    assert sources(answer) == [r["R1"], r["R5"]]
    assert "Row: USD | 6.00 | 6.00" in model.answer_prompts[0]


def test_e8_arabizi_question_and_answer(client, model, alice):
    headers, _, r = alice
    model.sql_replies, model.answer_replies = [E8_SQL], ["Dafa3et $3.75 3al laban hal shahr."]

    answer = ask(client, headers, "addesh dafa3et 3al laban hal shahr?")

    assert answer["content"] == "Dafa3et $3.75 3al laban hal shahr."  # the 3s in the words are letters
    assert sources(answer) == [r["R5"]]


# --- E9-E12: clarify, unsupported, reply (no data, no answer step) ---


@pytest.mark.parametrize(
    ("question", "reply", "kind", "content"),
    [
        ("How much did I spend on milk?", "CLARIFY: I can't find milk in your receipts. Did you mean laban?",
         "clarify", "I can't find milk in your receipts. Did you mean laban?"),  # E9
        ("How much was the last one?", "CLARIFY: The last what? A receipt, or a particular item?",
         "clarify", "The last what? A receipt, or a particular item?"),  # E10
        ("Am I over my groceries budget?", "UNSUPPORTED", "unsupported", answers.UNSUPPORTED),  # E11
        ("hi", "REPLY: Hi! Ask me about your spending, for example how much you spent on groceries this month.",
         "reply", "Hi! Ask me about your spending, for example how much you spent on groceries this month."),  # E12
    ],
)  # fmt: skip
def test_e9_to_e12_replies_without_data(client, model, alice, question, reply, kind, content):
    headers, _, _ = alice
    model.sql_replies = [reply]

    answer = ask(client, headers, question)

    assert (answer["kind"], answer["content"], answer["sql"], answer["source_receipts"]) == (kind, content, None, [])
    assert model.answer_prompts == []


def test_a_clarifying_question_with_a_made_up_number_is_asked_again(client, model, alice):
    headers, _, _ = alice
    model.sql_replies = ["REPLY: Hi! You spent about $50 this week.", "REPLY: Hi! Ask me about your spending."]
    answer = ask(client, headers, "hi")
    assert answer["content"] == "Hi! Ask me about your spending."
    assert "numbers that are not in the question: 50" in model.sql_prompts[1]


# --- E13-E16: repairs and failure ---


def test_e13_a_guard_refusal_is_repaired(client, container, model, alice):
    headers, user_id, r = alice
    refused = "SELECT currency, SUM(total) AS total_spent FROM public.receipts GROUP BY currency"
    model.sql_replies, model.answer_replies = [refused, E13_SQL], ["You spent $22.00 this month."]

    answer = ask(client, headers, "How much did I spend in total this month?")

    assert answer["content"] == "You spent $22.00 this month."
    assert sources(answer) == [r["R5"], r["R6"]]
    assert "Only the receipts, purchases and category_spending views can be queried" in model.sql_prompts[1]
    attempts = saved_details(container, user_id, answer).attempts
    assert [(a.step, a.output, a.problem is None) for a in attempts] == [
        (Step.SQL, refused, False), (Step.SQL, E13_SQL, True), (Step.ANSWER, "You spent $22.00 this month.", True),
    ]  # fmt: skip
    assert attempts[0].model == "fake-sql-model" and attempts[2].model == "fake-answer-model"


def test_e14_a_loose_item_match_is_repaired(client, model, alice):
    headers, _, r = alice
    loose = MONEY.format(amount="line_total", view="purchases", where="item_name ILIKE '%water%'")
    model.sql_replies, model.answer_replies = [loose, E7_SQL], ["You spent $6.00 on water."]

    answer = ask(client, headers, "How much did I spend on water?")

    assert answer["content"] == "You spent $6.00 on water."  # not $51.00 with the water heater
    assert sources(answer) == [r["R1"], r["R5"]]
    assert "Item names must match exactly: use item_name = '<name>' with a name from the list" in model.sql_prompts[1]


def test_e15_a_database_error_is_repaired(client, model, alice):
    headers, _, _ = alice
    wrong = E13_SQL.replace("SUM(total) AS", "SUM(totl) AS")
    model.sql_replies, model.answer_replies = [wrong, E13_SQL], ["You spent $22.00 this month."]

    answer = ask(client, headers, "How much did I spend in total this month?")

    assert answer["content"] == "You spent $22.00 this month."
    assert 'column "totl" does not exist' in model.sql_prompts[1]


def test_e16_two_failures_end_politely(client, container, model, alice):
    headers, user_id, _ = alice
    model.sql_replies = ["SELECT * FROM public.receipts", "Sure! Here is the query: SELECT 1"]

    answer = ask(client, headers, "How much did I spend in total this month?")

    assert (answer["kind"], answer["content"], answer["sql"]) == ("error", answers.FAILURE, None)
    assert len(saved_details(container, user_id, answer).attempts) == 2
    assert model.answer_prompts == []


# --- E17-E21: no matches, receipts in review, the table fallback, other users, a cut-off result ---


def test_e17_nothing_matched(client, container, model, alice):
    headers, user_id, _ = alice
    model.sql_replies = [E17_SQL]

    answer = ask(client, headers, "How much did I spend on dining in September?")

    assert (answer["kind"], answer["content"], answer["source_receipts"]) == ("answer", answers.NO_MATCHES, [])
    assert "2026-09-01" in answer["sql"]
    assert model.answer_prompts == []  # no answer-step call
    assert saved_details(container, user_id, answer).row_count == 0


def test_e18_receipts_waiting_for_review_are_mentioned(client, model, extractor, alice):
    headers, _, _ = alice
    extractor.result = ExtractedReceipt(
        vendor_name="Spinneys", receipt_date=TODAY, currency="USD", total=Decimal("5.00"),
        lines=[ExtractedLine("LABAN", Decimal("5.00"))],
    )  # fmt: skip
    upload = client.post("/receipts", files={"file": ("r7", uuid.uuid4().bytes, "image/jpeg")}, headers=headers)
    assert client.get(f"/receipts/{upload.json()['id']}", headers=headers).json()["status"] == "needs_review"
    model.sql_replies, model.answer_replies = [E1_SQL], [E1_ANSWER]

    answer = ask(client, headers, "How much did I spend on groceries this month?")

    assert answer["content"] == (
        "You spent $8.00 on Groceries this month. 1 receipt is still waiting for your review and isn't included."
    )


def test_e19_an_answer_that_fails_the_number_check_twice_becomes_a_table(client, container, model, alice):
    headers, user_id, _ = alice
    wrong = "Last month you spent $13.50 and 1,450,000 LBP on Groceries, about $29.71 in total."
    model.sql_replies, model.answer_replies = [E2_SQL], [wrong, wrong]

    answer = ask(client, headers, "How much did I spend on groceries last month?")

    assert (answer["kind"], answer["content"]) == ("answer", answers.TABLE_INTRO)
    assert answer["columns"] == ["currency", "total_spent", "total_spent_usd"]
    rows = sorted(answer["rows"])
    assert [row[:2] for row in rows] == [["LBP", "1450000.00"], ["USD", "13.50"]]
    assert Decimal(rows[0][2]).quantize(Decimal("0.01")) == Decimal("16.20")
    assert "numbers that are not in the result: 29.71" in model.answer_prompts[1]
    reopened = client.get(f"/assistant/conversations/{answer['conversation_id']}", headers=headers).json()
    assert reopened["messages"][1]["rows"] == answer["rows"]  # drawn again exactly as it was


def test_e20_another_users_data_never_appears(client, container, settings, model, alice, bob):
    headers, user_id, r = alice
    model.sql_replies = [MONEY.format(amount="line_total", view="purchases", where="item_name = 'manakish'")] * 2

    answer = ask(client, headers, "How much did I spend on manakish?")

    assert (answer["kind"], answer["content"]) == ("error", answers.FAILURE)
    assert "'manakish' is not one of the user's items" in model.sql_prompts[1]
    lists = [line for line in model.sql_prompts[0].splitlines() if line.startswith("The user's ")]
    assert len(lists) == 3 and '"laban"' in lists[0] and '"Spinneys"' in lists[1]
    for name in ("manakish", "Zaatar w Zeit"):
        assert all(name not in line for line in lists)
    # Even past the rules, the database shows Alice none of Bob's rows.
    runner = SqlReadOnlyQueryRunner(create_db_engine(settings.readonly_database_url))
    bobs = "SELECT receipt_id FROM purchases WHERE item_name = 'manakish' OR vendor = 'Zaatar w Zeit'"
    rows = runner.run(user_id, bobs)
    assert rows.rows == []
    everything = runner.run(user_id, "SELECT DISTINCT receipt_id FROM category_spending ORDER BY 1").rows
    assert [row[0] for row in everything] == sorted(r.values())
    assert not set(bob[2].values()) & {row[0] for row in everything}


def test_e21_a_cut_off_result_is_announced(settings, engine, model, alice):
    _, user_id, _ = alice
    service = AssistantService(
        SqlUnitOfWorkFactory(engine), SqlGlotGuard(),
        SqlReadOnlyQueryRunner(create_db_engine(settings.readonly_database_url), max_rows=3),
        SqlGlotQueryRules(), model, lambda: TODAY,
    )  # fmt: skip
    expected = (
        "These are your first 3 purchases (the list was cut off): laban for $3.50 and water for $3.00 at Spinneys "
        "on 5 October 2026, and laban for $4.00 at Carrefour on 12 October 2026."
    )
    model.sql_replies = ["SELECT receipt_date, vendor, item_name, line_total FROM purchases "
                         "ORDER BY receipt_date, line_total DESC"]  # fmt: skip
    model.answer_replies = [expected]

    result = service.ask(user_id, None, "List my purchases")

    assert result.answer.content == expected
    assert "only the first 3 rows are shown" in model.answer_prompts[0]


# --- The endpoint ---


def test_without_a_model_the_assistant_is_not_available(settings, tmp_path, sign_in, engine):
    container = build_container(settings, extractor=FakeReceiptExtractor(), storage=LocalFileStorage(tmp_path),
                                today=lambda: TODAY, assistant_model=UnavailableAssistantModel())  # fmt: skip
    client = TestClient(create_app(container))
    email = f"{uuid.uuid4()}@test.local"
    body = {"email": email, "password": "correct-horse"}
    try:
        assert client.post("/auth/register", json=body).status_code == 201
        token = client.post("/auth/login", json=body).json()["access_token"]
        answer = ask(client, {"Authorization": f"Bearer {token}"}, "How much did I spend?")
        assert (answer["kind"], answer["content"]) == ("error", answers.NOT_AVAILABLE)
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


def test_the_question_is_kept_even_if_answering_crashes(container, model, alice):
    _, user_id, _ = alice
    model.sql_replies = []  # the fake fails the call, as a crash in the middle of answering
    with pytest.raises(AssertionError):
        container.assistant.ask(user_id, None, "How much did I spend?")
    conversation = container.assistant.list_conversations(user_id)[0]
    messages = container.assistant.open_conversation(user_id, conversation.id).messages
    assert [(m.role.value, m.content) for m in messages] == [("user", "How much did I spend?")]


def test_asking_needs_a_valid_question_and_ones_own_conversation(client, model, alice, bob):
    alice_headers, _, _ = alice
    bob_headers, _, _ = bob
    assert client.post("/assistant/ask", json={"question": "   "}, headers=alice_headers).status_code == 422
    assert client.post("/assistant/ask", json={"question": "hi"}).status_code == 401
    model.sql_replies = ["REPLY: Hi!"]
    mine = ask(client, alice_headers, "hi")
    stolen = {"question": "and last month?", "conversation_id": mine["conversation_id"]}
    assert client.post("/assistant/ask", json=stolen, headers=bob_headers).status_code == 404
    assert model.sql_prompts == [model.sql_prompts[0]]  # Bob's question never reached the model


def test_the_answer_kind_is_saved_as_answer(container, model, alice):
    _, user_id, _ = alice
    model.sql_replies, model.answer_replies = [E1_SQL], [E1_ANSWER]
    result = container.assistant.ask(user_id, None, "How much did I spend on groceries this month?")
    assert result.answer.details.kind is AnswerKind.ANSWER
    assert result.answer.details.duration_ms is not None


# --- The names in the prompt, for the research dataset (added 2026-11-08) ---


def test_prompt_names_are_exactly_the_names_the_model_is_sent(client, container, model, alice):
    """The dataset builds its training prompts with these names, so they must be the ones the app sends."""
    headers, user_id, _ = alice
    model.sql_replies, model.answer_replies = [E1_SQL], [E1_ANSWER]
    ask(client, headers, "How much did I spend on groceries this month?")

    names = container.assistant.prompt_names(user_id)
    sent = model.sql_prompts[0]
    for label, values in (("items", names.items), ("vendors", names.vendors), ("categories", names.categories)):
        assert f"The user's {label}: " + ", ".join(f'"{v}"' for v in values) in sent
    assert "laban" in names.items and "Spinneys" in names.vendors and "Uncategorized" in names.categories
