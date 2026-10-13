"""Cross-user isolation (scope section 6.5): user A must never reach user B's data."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

RLS_VIOLATION = "42501"
FK_VIOLATION = "23503"


def sqlstate(excinfo) -> str:
    return excinfo.value.orig.sqlstate


def add_vendor(conn, user_id: int, name: str = "Spinneys") -> int:
    return conn.execute(
        text("INSERT INTO vendors (user_id, name) VALUES (:u, :n) RETURNING id"), {"u": user_id, "n": name}
    ).scalar_one()


def add_receipt(conn, user_id: int, **extra) -> int:
    columns = {"user_id": user_id, **extra}
    names = ", ".join(columns)
    params = ", ".join(f":{c}" for c in columns)
    return conn.execute(text(f"INSERT INTO receipts ({names}) VALUES ({params}) RETURNING id"), columns).scalar_one()


def add_line(conn, receipt_id: int, user_id: int, **extra) -> int:
    columns = {"receipt_id": receipt_id, "user_id": user_id, "description": "laban", "line_total": 3, **extra}
    names = ", ".join(columns)
    params = ", ".join(f":{c}" for c in columns)
    statement = text(f"INSERT INTO receipt_items ({names}) VALUES ({params}) RETURNING id")
    return conn.execute(statement, columns).scalar_one()


def count(conn, table: str) -> int:
    return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def test_app_role_does_not_own_tables_or_bypass_rls(engine):
    with engine.connect() as conn:
        owners_query = text("SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'public'")
        owners = conn.execute(owners_query).scalars().all()
        role = conn.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
    assert "app_user" not in owners
    assert tuple(role) == (False, False)


def test_user_sees_only_their_own_rows(as_user, alice, bob):
    with as_user(alice) as conn:
        vendor = add_vendor(conn, alice)
        receipt = add_receipt(conn, alice, vendor_id=vendor, total=10, currency="USD")
        add_line(conn, receipt, alice)

    with as_user(bob) as conn:
        for table in ("vendors", "receipts", "receipt_items"):
            assert count(conn, table) == 0

    with as_user(alice) as conn:
        for table in ("vendors", "receipts", "receipt_items"):
            assert count(conn, table) == 1


def test_no_user_context_sees_nothing(as_user, alice):
    with as_user(alice) as conn:
        add_vendor(conn, alice)
    with as_user(None) as conn:
        assert count(conn, "vendors") == 0


def test_cannot_write_rows_for_another_user(as_user, alice, bob):
    with pytest.raises(DBAPIError) as err, as_user(alice) as conn:
        add_vendor(conn, bob)
    assert sqlstate(err) == RLS_VIOLATION


def test_cannot_modify_or_delete_another_users_rows(as_user, alice, bob):
    with as_user(alice) as conn:
        vendor = add_vendor(conn, alice, "Alice only")

    with as_user(bob) as conn:
        updated = conn.execute(text("UPDATE vendors SET name = 'hacked' WHERE id = :id"), {"id": vendor}).rowcount
        deleted = conn.execute(text("DELETE FROM vendors WHERE id = :id"), {"id": vendor}).rowcount
    assert (updated, deleted) == (0, 0)

    with as_user(alice) as conn:
        name = conn.execute(text("SELECT name FROM vendors WHERE id = :id"), {"id": vendor}).scalar_one()
        assert name == "Alice only"


def test_line_cannot_attach_to_another_users_receipt(as_user, alice, bob):
    with as_user(alice) as conn:
        receipt = add_receipt(conn, alice)
    with pytest.raises(DBAPIError) as err, as_user(bob) as conn:
        add_line(conn, receipt, bob)
    assert sqlstate(err) == FK_VIOLATION


def test_receipt_cannot_use_another_users_vendor(as_user, alice, bob):
    with as_user(alice) as conn:
        vendor = add_vendor(conn, alice)
    with pytest.raises(DBAPIError) as err, as_user(bob) as conn:
        add_receipt(conn, bob, vendor_id=vendor)
    assert sqlstate(err) == FK_VIOLATION


def test_shared_categories_are_visible_but_read_only(as_user, alice):
    with as_user(alice) as conn:
        assert conn.execute(text("SELECT count(*) FROM categories WHERE user_id IS NULL")).scalar_one() >= 8
        updated = conn.execute(text("UPDATE categories SET name = 'hacked' WHERE user_id IS NULL")).rowcount
        deleted = conn.execute(text("DELETE FROM categories WHERE user_id IS NULL")).rowcount
    assert (updated, deleted) == (0, 0)


def test_private_category_is_hidden_and_unusable_by_others(as_user, alice, bob):
    with as_user(alice) as conn:
        category = conn.execute(
            text("INSERT INTO categories (user_id, name) VALUES (:u, 'Alice private') RETURNING id"), {"u": alice}
        ).scalar_one()
        receipt = add_receipt(conn, alice)
        add_line(conn, receipt, alice, category_id=category)  # her own category is fine

    with as_user(bob) as conn:
        assert conn.execute(text("SELECT count(*) FROM categories WHERE id = :id"), {"id": category}).scalar_one() == 0
        bob_receipt = add_receipt(conn, bob)

    with pytest.raises(DBAPIError) as err, as_user(bob) as conn:
        add_line(conn, bob_receipt, bob, category_id=category)
    assert sqlstate(err) == RLS_VIOLATION


def test_shared_category_can_be_used_by_anyone(as_user, alice):
    with as_user(alice) as conn:
        shared = conn.execute(text("SELECT id FROM categories WHERE name = 'Groceries'")).scalar_one()
        receipt = add_receipt(conn, alice, primary_category_id=shared)
        add_line(conn, receipt, alice, category_id=shared)


def test_budget_cannot_use_another_users_private_category(as_user, alice, bob):
    with as_user(alice) as conn:
        category = conn.execute(
            text("INSERT INTO categories (user_id, name) VALUES (:u, 'Alice private') RETURNING id"), {"u": alice}
        ).scalar_one()
    with pytest.raises(DBAPIError) as err, as_user(bob) as conn:
        conn.execute(
            text(
                "INSERT INTO budgets (user_id, category_id, month, currency, limit_amount) "
                "VALUES (:u, :c, '2026-10-01', 'USD', 100)"
            ),
            {"u": bob, "c": category},
        )
    assert sqlstate(err) == RLS_VIOLATION


def test_conversations_messages_and_feedback_are_isolated(as_user, alice, bob):
    with as_user(alice) as conn:
        conversation = conn.execute(
            text("INSERT INTO conversations (user_id) VALUES (:u) RETURNING id"), {"u": alice}
        ).scalar_one()
        message = conn.execute(
            text("INSERT INTO messages (conversation_id, role, content) VALUES (:c, 'assistant', 'hi') RETURNING id"),
            {"c": conversation},
        ).scalar_one()
        conn.execute(text("INSERT INTO assistant_feedback (message_id, rating) VALUES (:m, 1)"), {"m": message})

    with as_user(bob) as conn:
        for table in ("conversations", "messages", "assistant_feedback"):
            assert count(conn, table) == 0

    # Knowing a conversation id must not allow writing into it.
    with pytest.raises(DBAPIError) as err, as_user(bob) as conn:
        conn.execute(
            text("INSERT INTO messages (conversation_id, role, content) VALUES (:c, 'user', 'injected')"),
            {"c": conversation},
        )
    assert sqlstate(err) == RLS_VIOLATION


def test_feedback_is_only_allowed_on_assistant_messages(as_user, alice):
    with as_user(alice) as conn:
        conversation = conn.execute(
            text("INSERT INTO conversations (user_id) VALUES (:u) RETURNING id"), {"u": alice}
        ).scalar_one()
        message = conn.execute(
            text("INSERT INTO messages (conversation_id, role, content) VALUES (:c, 'user', 'hello') RETURNING id"),
            {"c": conversation},
        ).scalar_one()
    with pytest.raises(DBAPIError) as err, as_user(alice) as conn:
        conn.execute(text("INSERT INTO assistant_feedback (message_id, rating) VALUES (:m, 1)"), {"m": message})
    assert sqlstate(err) == FK_VIOLATION


def test_deleting_a_user_removes_their_data_but_keeps_shared_categories(engine, as_user, make_user):
    user = make_user()
    with as_user(user) as conn:
        category = conn.execute(
            text("INSERT INTO categories (user_id, name) VALUES (:u, 'Mine') RETURNING id"), {"u": user}
        ).scalar_one()
        vendor = add_vendor(conn, user)
        receipt = add_receipt(conn, user, vendor_id=vendor)
        add_line(conn, receipt, user, category_id=category)
        conversation = conn.execute(
            text("INSERT INTO conversations (user_id) VALUES (:u) RETURNING id"), {"u": user}
        ).scalar_one()
        conn.execute(
            text("INSERT INTO messages (conversation_id, role, content) VALUES (:c, 'user', 'hi')"),
            {"c": conversation},
        )

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user})
        assert conn.execute(text("SELECT count(*) FROM users WHERE id = :id"), {"id": user}).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM categories WHERE user_id IS NULL")).scalar_one() >= 8
