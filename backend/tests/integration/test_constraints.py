"""Integrity rules from scope section 6.2 that the database itself must enforce."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.integration.test_isolation import add_line, add_receipt, add_vendor, sqlstate

CHECK_VIOLATION = "23514"
UNIQUE_VIOLATION = "23505"


def test_negative_receipt_total_is_rejected(as_user, alice):
    with pytest.raises(DBAPIError) as err, as_user(alice) as conn:
        add_receipt(conn, alice, total=-1, currency="USD")
    assert sqlstate(err) == CHECK_VIOLATION


def test_only_usd_and_lbp_are_valid_currencies(as_user, alice):
    with pytest.raises(DBAPIError) as err, as_user(alice) as conn:
        add_receipt(conn, alice, total=5, currency="EUR")
    assert sqlstate(err) == CHECK_VIOLATION


def test_confirmed_receipt_needs_date_currency_and_total(as_user, alice):
    with pytest.raises(DBAPIError) as err, as_user(alice) as conn:
        add_receipt(conn, alice, status="confirmed")
    assert sqlstate(err) == CHECK_VIOLATION


def test_confirmed_receipt_with_all_fields_is_accepted(as_user, alice):
    with as_user(alice) as conn:
        add_receipt(
            conn, alice, status="confirmed", receipt_date="2026-10-01", currency="LBP", total=450000,
            exchange_rate_used=89500,
        )  # fmt: skip


def test_a_confirmed_receipt_must_have_an_exchange_rate(as_user, alice):
    # Migration 0005: the assistant's USD views divide by the rate, so it can never be missing.
    with pytest.raises(DBAPIError) as err, as_user(alice) as conn:
        add_receipt(conn, alice, status="confirmed", receipt_date="2026-10-01", currency="LBP", total=450000)
    assert sqlstate(err) == CHECK_VIOLATION


def test_duplicate_file_hash_is_rejected_per_user_but_allowed_across_users(as_user, alice, bob):
    with as_user(alice) as conn:
        add_receipt(conn, alice, file_hash="abc")
    with as_user(bob) as conn:
        add_receipt(conn, bob, file_hash="abc")
    with pytest.raises(DBAPIError) as err, as_user(alice) as conn:
        add_receipt(conn, alice, file_hash="abc")
    assert sqlstate(err) == UNIQUE_VIOLATION


def test_vendor_names_are_unique_per_user_ignoring_case(as_user, alice, bob):
    with as_user(alice) as conn:
        add_vendor(conn, alice, "Spinneys")
    with as_user(bob) as conn:
        add_vendor(conn, bob, "Spinneys")
    with pytest.raises(DBAPIError) as err, as_user(alice) as conn:
        add_vendor(conn, alice, "  SPINNEYS ")
    assert sqlstate(err) == UNIQUE_VIOLATION


@pytest.mark.parametrize(
    "bad",
    [
        {"quantity": 0},
        {"line_total": -1},
        {"unit_price": -1},
        {"description": "   "},
        {"size_amount": 250},  # size needs its unit
        {"size_unit": "ml"},  # unit needs its size
        {"size_amount": 0, "size_unit": "ml"},
        {"size_amount": 250, "size_unit": "oz"},
    ],
)
def test_invalid_receipt_lines_are_rejected(as_user, alice, bad):
    with as_user(alice) as conn:
        receipt = add_receipt(conn, alice)
    with pytest.raises(DBAPIError) as err, as_user(alice) as conn:
        add_line(conn, receipt, alice, **bad)
    assert sqlstate(err) == CHECK_VIOLATION


def test_valid_line_with_size_is_accepted(as_user, alice):
    with as_user(alice) as conn:
        receipt = add_receipt(conn, alice)
        add_line(conn, receipt, alice, size_amount=250, size_unit="ml", quantity=3, unit_price=1.5, line_total=4.5)


def test_one_budget_per_category_and_month_whatever_the_currency(as_user, alice):
    # Migration 0002 (agreed 2026-10-14): a budget counts both currencies, so a second one in another
    # currency for the same category and month is refused.
    insert = text(
        "INSERT INTO budgets (user_id, category_id, month, currency, limit_amount) "
        "VALUES (:u, (SELECT id FROM categories WHERE name = 'Groceries'), :month, :cur, 100)"
    )
    with as_user(alice) as conn:
        conn.execute(insert, {"u": alice, "month": "2026-10-01", "cur": "USD"})
        conn.execute(insert, {"u": alice, "month": "2026-11-01", "cur": "USD"})  # another month is fine
    with pytest.raises(DBAPIError) as err, as_user(alice) as conn:
        conn.execute(insert, {"u": alice, "month": "2026-10-01", "cur": "LBP"})
    assert sqlstate(err) == UNIQUE_VIOLATION


def test_budget_month_must_be_the_first_day(as_user, alice):
    with pytest.raises(DBAPIError) as err, as_user(alice) as conn:
        conn.execute(
            text(
                "INSERT INTO budgets (user_id, category_id, month, currency, limit_amount) "
                "VALUES (:u, (SELECT id FROM categories WHERE name = 'Groceries'), '2026-10-15', 'USD', 100)"
            ),
            {"u": alice},
        )
    assert sqlstate(err) == CHECK_VIOLATION


def test_category_and_vendor_in_use_cannot_be_deleted(as_user, alice):
    with as_user(alice) as conn:
        category = conn.execute(
            text("INSERT INTO categories (user_id, name) VALUES (:u, 'Used') RETURNING id"), {"u": alice}
        ).scalar_one()
        vendor = add_vendor(conn, alice)
        add_receipt(conn, alice, vendor_id=vendor, primary_category_id=category)

    with pytest.raises(DBAPIError) as err, as_user(alice) as conn:
        conn.execute(text("DELETE FROM categories WHERE id = :id"), {"id": category})
    assert sqlstate(err) == FK_VIOLATION

    with pytest.raises(DBAPIError) as err, as_user(alice) as conn:
        conn.execute(text("DELETE FROM vendors WHERE id = :id"), {"id": vendor})
    assert sqlstate(err) == FK_VIOLATION


def test_deleting_a_receipt_deletes_its_lines(as_user, alice):
    with as_user(alice) as conn:
        receipt = add_receipt(conn, alice)
        add_line(conn, receipt, alice)
    with as_user(alice) as conn:
        conn.execute(text("DELETE FROM receipts WHERE id = :id"), {"id": receipt})
        assert conn.execute(text("SELECT count(*) FROM receipt_items")).scalar_one() == 0


FK_VIOLATION = "23503"
