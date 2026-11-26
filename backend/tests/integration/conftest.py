"""Integration tests run against the real PostgreSQL database as the runtime `app_user` role."""

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.infrastructure.config import Settings
from app.infrastructure.database.connection import user_scoped_connection


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(Settings().database_url)
    try:
        with engine.connect():
            pass
    except OperationalError:
        pytest.skip("PostgreSQL is not reachable with DATABASE_URL; skipping integration tests")
    return engine


@pytest.fixture
def as_user(engine):
    """Open a transaction acting as the given user, the same way the API will."""

    @contextmanager
    def _as_user(user_id: int | None):
        if user_id is None:  # no user context at all
            with engine.begin() as conn:
                yield conn
        else:  # the same helper the API will use
            with user_scoped_connection(engine, user_id) as conn:
                yield conn

    return _as_user


def forget_usage(engine, user_id: int) -> None:
    """Delete a test user's usage rows before the user. Otherwise they stay (an account's spending counts after it
    is deleted) and a test's crashed Standard questions, each counted at the reserve, would fill this month's cap on
    the development database."""
    with user_scoped_connection(engine, user_id) as conn:
        conn.execute(text("DELETE FROM assistant_usage"))


def forget_usage_by_email(engine, email: str) -> None:
    with engine.connect() as conn:
        user_id = conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email}).scalar_one_or_none()
    if user_id is not None:
        forget_usage(engine, user_id)


def _create_user(engine) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text("INSERT INTO users (email, password_hash) VALUES (:e, 'x') RETURNING id"),
            {"e": f"{uuid.uuid4()}@test.local"},
        ).scalar_one()


@pytest.fixture
def make_user(engine):
    """Create users for a test and delete them (cascading all their data) afterwards."""
    created: list[int] = []

    def _make() -> int:
        user_id = _create_user(engine)
        created.append(user_id)
        return user_id

    yield _make

    for user_id in created:
        forget_usage(engine, user_id)
    with engine.begin() as conn:
        for user_id in created:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})


@pytest.fixture
def alice(make_user) -> int:
    return make_user()


@pytest.fixture
def bob(make_user) -> int:
    return make_user()
