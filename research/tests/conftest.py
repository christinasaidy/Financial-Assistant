"""Tests that seed the evaluation data need the real database, like the backend's integration tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from research.evaluation.wiring import load_settings


@pytest.fixture(scope="session")
def settings():
    settings = load_settings()
    try:
        with create_engine(settings.database_url).connect():
            pass
    except OperationalError:
        pytest.skip("PostgreSQL is not reachable with DATABASE_URL; skipping the evaluation's database tests")
    if not settings.readonly_database_url:
        pytest.skip("READONLY_DATABASE_URL is not set")
    return settings
