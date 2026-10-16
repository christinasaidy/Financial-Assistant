"""The assistant's views and the read-only role, against the real database.

Two things are proven here:
1. the views apply the spending rules, so simple generated SQL gives the right numbers;
2. the database role is a real second line of defence: even SQL that never went through the checker
   cannot write, cannot read anything but the views, and cannot see another user's rows.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.api.app import create_app
from app.domain.assistant.errors import QueryFailed, UnsafeQuery
from app.infrastructure.config import Settings
from app.infrastructure.database.connection import create_db_engine
from app.infrastructure.database.readonly_query_runner import SqlReadOnlyQueryRunner
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.fakes import FakeReceiptExtractor

THIS_MONTH = date.today().replace(day=1)


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
def container(settings, tmp_path):
    return build_container(settings, extractor=FakeReceiptExtractor(), storage=LocalFileStorage(tmp_path))


@pytest.fixture
def raw_runner(settings):
    """Runs SQL as ai_readonly WITHOUT the checker, to prove the database role holds on its own."""
    return SqlReadOnlyQueryRunner(create_db_engine(settings.readonly_database_url), timeout_ms=1000)


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


def add(client, headers, total, currency="USD", category=None, lines=(), vendor="Spinneys", day=None, rate="89500"):
    body = {
        "vendor_name": vendor,
        "receipt_date": (day or THIS_MONTH).isoformat(),
        "currency": currency,
        "total": total,
        "primary_category_id": category,
        "lines": [
            {"description": name, "normalized_name": name.lower(), "line_total": amount, "category_id": cat}
            for name, amount, cat in lines
        ],
        "lbp_per_usd": rate,
    }
    response = client.post("/receipts/manual", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def alice_with_receipts(client, sign_in):
    """October-style month: items with and without categories, tax, a no-item receipt, and pounds."""
    headers, user_id = sign_in()
    ids = {c["name"]: c["id"] for c in client.get("/categories", headers=headers).json()}
    g, h, d = ids["Groceries"], ids["Household"], ids["Dining"]
    add(client, headers, "23.00", lines=[("Milk", "5", g), ("Bread", "3", None), ("Detergent", "12", h)], category=g)
    add(client, headers, "15.00", category=d, vendor="Cafe")
    add(client, headers, "8.50", vendor="Pharmacy")
    add(client, headers, "895000", currency="LBP", category=g, vendor="Carrefour")  # $10 at 89,500
    return headers, user_id


def one_value(result):
    return result.rows[0][0]


# --- The views apply the agreed rules ---


def test_category_spending_applies_the_rules(container, alice_with_receipts):
    _, alice = alice_with_receipts
    result = container.assistant.run_query(
        alice, "SELECT category, SUM(amount_usd) FROM category_spending GROUP BY category ORDER BY category"
    )
    amounts = {category: round(amount, 2) for category, amount in result.rows}
    assert amounts == {
        "Dining": Decimal("15.00"),
        "Groceries": Decimal("18.00"),  # milk 5 + bread 3 (takes the receipt's category) + 10 from pounds
        "Household": Decimal("12.00"),
        "Tax, discounts & rounding": Decimal("3.00"),
        "Uncategorized": Decimal("8.50"),  # pharmacy: no items, no category
    }


def test_category_spending_adds_up_to_the_receipts(container, alice_with_receipts):
    _, alice = alice_with_receipts
    by_category = one_value(container.assistant.run_query(alice, "SELECT SUM(amount_usd) FROM category_spending"))
    by_receipt = one_value(container.assistant.run_query(alice, "SELECT SUM(total_usd) FROM receipts"))
    assert round(by_category, 2) == round(by_receipt, 2) == Decimal("56.50")


def test_amounts_in_pounds_are_also_given_in_dollars_at_the_saved_rate(container, alice_with_receipts):
    _, alice = alice_with_receipts
    result = container.assistant.run_query(alice, "SELECT total, total_usd FROM receipts WHERE currency = 'LBP'")
    total, total_usd = result.rows[0]
    assert (total, round(total_usd, 2)) == (Decimal("895000.00"), Decimal("10.00"))


def test_purchases_show_each_item_with_its_effective_category(container, alice_with_receipts):
    _, alice = alice_with_receipts
    result = container.assistant.run_query(
        alice, "SELECT item, item_name, category, vendor FROM purchases ORDER BY item"
    )
    assert result.columns == ["item", "item_name", "category", "vendor"]
    assert result.rows == [
        ("Bread", "bread", "Groceries", "Spinneys"),
        ("Detergent", "detergent", "Household", "Spinneys"),
        ("Milk", "milk", "Groceries", "Spinneys"),
    ]


def test_only_confirmed_receipts_are_visible(container, client, alice_with_receipts):
    headers, alice = alice_with_receipts
    client.post("/receipts", files={"file": ("r", b"img", "image/jpeg")}, headers=headers)  # ends "failed"
    assert one_value(container.assistant.run_query(alice, "SELECT COUNT(*) FROM receipts")) == 4


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT SUM(total_usd) FROM receipts WHERE receipt_date >= date_trunc('month', CURRENT_DATE)",
        "SELECT COUNT(*) FROM receipts WHERE vendor ILIKE '%spinneys%' "
        "AND receipt_date >= date_trunc('month', CURRENT_DATE)",
        "SELECT receipt_date, vendor, item, unit_price, line_total, currency, size_amount, size_unit "
        "FROM purchases WHERE item_name ILIKE '%milk%' ORDER BY receipt_date DESC LIMIT 1",
    ],
)
def test_the_approved_example_queries_run(container, alice_with_receipts, sql):
    _, alice = alice_with_receipts
    assert container.assistant.run_query(alice, sql).rows  # runs after being checked and rebuilt


def test_the_approved_examples_give_the_right_numbers(container, alice_with_receipts):
    _, alice = alice_with_receipts
    month = "receipt_date >= date_trunc('month', CURRENT_DATE)"
    spent = one_value(container.assistant.run_query(alice, f"SELECT SUM(total_usd) FROM receipts WHERE {month}"))
    visits_sql = f"SELECT COUNT(*) FROM receipts WHERE vendor ILIKE '%spinneys%' AND {month}"
    visits = one_value(container.assistant.run_query(alice, visits_sql))
    assert (round(spent, 2), visits) == (Decimal("56.50"), 1)


# --- Isolation: users never see each other's rows ---


def test_a_user_only_ever_sees_their_own_rows(container, alice_with_receipts, client, sign_in):
    headers, alice = alice_with_receipts
    _, bob = sign_in()
    for view in ("receipts", "purchases", "category_spending"):
        assert one_value(container.assistant.run_query(bob, f"SELECT COUNT(*) FROM {view}")) == 0
    assert one_value(container.assistant.run_query(alice, "SELECT COUNT(*) FROM receipts")) == 4


@pytest.fixture
def one_connection(settings):
    """An engine with exactly one database connection, so every use is the same physical connection."""
    engine = create_engine(settings.readonly_database_url, pool_size=1, max_overflow=0)
    yield engine
    engine.dispose()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) FROM receipts",  # succeeds
        "SELECT no_such_column FROM receipts",  # fails
        "SELECT pg_sleep(2)",  # times out (the runner below allows 0.5 s)
    ],
    ids=["after success", "after failure", "after timeout"],
)
def test_nothing_is_left_on_the_connection_for_the_next_query(one_connection, alice_with_receipts, sql):
    # Code review weakness A: the old version of this test looked at a different connection pool.
    _, alice = alice_with_receipts
    runner = SqlReadOnlyQueryRunner(one_connection, timeout_ms=500)

    def connection_state():
        with one_connection.connect() as conn:
            return (
                conn.exec_driver_sql("SELECT pg_backend_pid()").scalar_one(),
                conn.exec_driver_sql("SELECT current_setting('app.user_id', true)").scalar_one(),
                conn.exec_driver_sql("SHOW search_path").scalar_one(),
                conn.exec_driver_sql("SHOW statement_timeout").scalar_one(),
            )

    before = connection_state()
    try:
        runner.run(alice, sql)
    except QueryFailed:
        pass
    after = connection_state()

    assert after[0] == before[0]  # really the same physical connection
    assert after[1] in ("", None)  # no user left behind
    assert after[2:] == before[2:]  # search path and time limit back to the role's defaults
    with one_connection.connect() as conn:  # and an unscoped query on it sees nothing
        conn.exec_driver_sql("SET search_path = assistant")
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM receipts").scalar_one() == 0


# --- The database role holds even without the checker (second line of defence) ---


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM public.users",
        "SELECT * FROM public.receipts",
        "SELECT * FROM public.receipt_items",
        "SELECT * FROM public.notifications",
    ],
)
def test_the_role_cannot_read_the_real_tables(raw_runner, alice_with_receipts, sql):
    _, alice = alice_with_receipts
    with pytest.raises(QueryFailed, match="permission denied"):
        raw_runner.run(alice, sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM public.receipts",
        "UPDATE public.receipts SET total = 0",
        "INSERT INTO public.categories (name) VALUES ('x')",
        "CREATE TABLE assistant.stolen (a int)",
    ],
)
def test_the_role_cannot_change_anything(raw_runner, alice_with_receipts, sql):
    _, alice = alice_with_receipts
    with pytest.raises(QueryFailed):
        raw_runner.run(alice, sql)


def test_a_slow_query_is_stopped(raw_runner, alice_with_receipts):
    _, alice = alice_with_receipts
    with pytest.raises(QueryFailed, match="statement timeout"):
        raw_runner.run(alice, "SELECT pg_sleep(3)")


def test_results_are_capped_at_200_rows(raw_runner, alice_with_receipts):
    _, alice = alice_with_receipts
    result = raw_runner.run(alice, "SELECT n FROM generate_series(1, 500) AS n")
    assert (len(result.rows), result.truncated) == (200, True)


@pytest.mark.parametrize(
    "template",
    [
        "SELECT set_config('app.user_id', '{alice}', false) AS s, (SELECT COUNT(*) FROM receipts) AS n",
        "SELECT COUNT(*) FROM receipts WHERE set_config('app.user_id', '{alice}', false) IS NOT NULL",
        # switch, read, then switch back, so the setting looks unchanged afterwards
        "SELECT set_config('app.user_id', '{alice}', false), (SELECT COUNT(*) FROM receipts), "
        "set_config('app.user_id', '{bob}', false)",
    ],
)
def test_switching_user_is_refused_by_the_database_even_without_the_checker(
    raw_runner, alice_with_receipts, sign_in, template
):
    _, alice = alice_with_receipts
    _, bob = sign_in()
    with pytest.raises(QueryFailed, match="permission denied for function set_config"):
        raw_runner.run(bob, template.format(alice=alice, bob=bob))
    assert raw_runner.run(bob, "SELECT COUNT(*) FROM receipts").rows == [(0,)]


def test_chaining_statements_is_refused_by_the_database_even_without_the_checker(raw_runner, alice_with_receipts):
    _, alice = alice_with_receipts
    with pytest.raises(QueryFailed, match="multiple commands"):
        raw_runner.run(alice, "SELECT 1; SET app.user_id = '999'")


def test_switching_user_inside_a_query_is_refused_by_the_checker(container, alice_with_receipts, sign_in):
    _, alice = alice_with_receipts
    _, bob = sign_in()
    sql = f"SELECT set_config('app.user_id', '{alice}', true), COUNT(*) FROM receipts"
    with pytest.raises(UnsafeQuery):
        container.assistant.run_query(bob, sql)


def test_a_mistake_in_allowed_sql_is_reported_not_crashed(container, alice_with_receipts):
    _, alice = alice_with_receipts
    with pytest.raises(QueryFailed, match="no_such_column"):
        container.assistant.run_query(alice, "SELECT no_such_column FROM receipts")
