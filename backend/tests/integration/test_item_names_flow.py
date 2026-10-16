"""Stable item names and brands through the real API and database (feature/better-item-names, approved by the user
on 2026-10-16). The vision model is a fake, so these tests check what the code does with its answer, never the
model's own choices (those are measured separately with the real API)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.app import create_app
from app.domain.receipts.extraction import ExtractedLine, ExtractedReceipt
from app.infrastructure.config import Settings
from app.infrastructure.database.connection import user_scoped_connection
from app.infrastructure.database.receipt_repository import SqlReceiptRepository
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.fakes import FakeReceiptExtractor


@pytest.fixture
def extractor():
    return FakeReceiptExtractor()


@pytest.fixture
def container(engine, extractor, tmp_path):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")
    return build_container(settings, extractor=extractor, storage=LocalFileStorage(tmp_path))


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


def category_id(client, headers, name):
    return next(c["id"] for c in client.get("/categories", headers=headers).json() if c["name"] == name)


def confirm_manually(client, headers, lines, total="10"):
    """A receipt the user typed in and confirmed. `lines` are (normalized_name, category name or None, brand)."""
    body = {
        "receipt_date": "2026-10-10", "currency": "USD", "total": total,
        "lines": [
            {"description": name.upper(), "normalized_name": name, "line_total": "1", "brand": brand,
             "category_id": category_id(client, headers, category) if category else None}
            for name, category, brand in lines
        ],
    }  # fmt: skip
    response = client.post("/receipts/manual", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


_uploads = iter(range(10**6))


def read_by_model(client, headers, extractor, *lines: ExtractedLine) -> dict:
    """Upload a receipt that the fake model reads as `lines`; returns the draft."""
    extractor.result = ExtractedReceipt(vendor_name="Spinneys", receipt_date=date(2026, 10, 15), currency="USD",
                                        total=Decimal(len(lines)), lines=lines)  # fmt: skip
    content = f"receipt-{next(_uploads)}-{uuid.uuid4()}".encode()
    receipt_id = client.post("/receipts", files={"file": ("r", content, "image/jpeg")}, headers=headers).json()["id"]
    draft = client.get(f"/receipts/{receipt_id}", headers=headers).json()
    assert draft["status"] == "needs_review", draft
    return draft


def line(name, category=None, brand=None) -> ExtractedLine:
    return ExtractedLine(description=(name or "?").upper(), line_total=Decimal(1), normalized_name=name,
                         category=category, brand=brand)  # fmt: skip


# --- The model is given the user's names, and its name takes the user's spelling ---


def test_the_model_gets_the_users_confirmed_names_most_recent_first(client, sign_in, extractor):
    alice, _ = sign_in()
    confirm_manually(client, alice, [("milk", None, None), ("taanayel low fat milk 1l", None, None)])
    confirm_manually(client, alice, [("olive oil", None, None), ("milk", None, None)])
    read_by_model(client, alice, extractor, line("bread"))  # a draft: its name is not offered
    read_by_model(client, alice, extractor, line("tea"))

    # milk was used again most recently; the 5-word name is not offered; the draft's "bread" is not confirmed.
    assert extractor.known_names == ["milk", "olive oil"]


def test_another_users_names_are_never_offered(client, sign_in, extractor):
    alice, _ = sign_in()
    bob, _ = sign_in()
    confirm_manually(client, alice, [("labneh", None, None)])
    read_by_model(client, bob, extractor, line("tea"))
    assert extractor.known_names == []


@pytest.mark.parametrize(
    ("model_name", "known", "expected"),
    [
        ("Oil  Olive", "olive oil", "olive oil"),
        ("small water", "water", "water"),
        ("water heater", "water", "water heater"),
        ("water", "water heater", "water"),
        ("pizza 2pcs large", None, "pizza"),
    ],
)
def test_the_saved_name_follows_the_approved_examples(client, sign_in, extractor, model_name, known, expected):
    alice, _ = sign_in()
    if known:
        confirm_manually(client, alice, [(known, None, None)])
    draft = read_by_model(client, alice, extractor, line(model_name))
    assert draft["lines"][0]["normalized_name"] == expected


def test_a_name_typed_by_the_user_is_kept_as_typed(client, sign_in):
    alice, _ = sign_in()
    confirm_manually(client, alice, [("olive oil", None, None)])
    receipt = confirm_manually(client, alice, [("Oil  Olive", None, None)])
    assert receipt["lines"][0]["normalized_name"] == "oil olive"  # tidied, not replaced


# --- Category memory compares the same words in any order, in the database too ---


def test_category_memory_matches_the_same_words_in_another_order(client, sign_in, extractor):
    alice, _ = sign_in()
    confirm_manually(client, alice, [("olive oil", "Groceries", None)])
    draft = read_by_model(client, alice, extractor, line("oil olive"))
    assert draft["lines"][0]["category_id"] == category_id(client, alice, "Groceries")


def test_category_memory_never_matches_part_of_a_name(client, sign_in, extractor):
    alice, _ = sign_in()
    confirm_manually(client, alice, [("water", "Dining", None)])
    draft = read_by_model(client, alice, extractor, line("water heater", category="Household"))
    assert draft["lines"][0]["category_id"] == category_id(client, alice, "Household")  # the model's suggestion


@pytest.mark.parametrize(
    "words", [("zaatar", "pâté"), ("fig", "éclair"), ("عيران", "لبن"), ("b", "a", "c"), ("oil", "olive", "extra")]
)  # "éclair" sorts before "fig" in the dev database's English collation, after it in Python
def test_the_databases_name_key_sorts_words_exactly_like_python(client, sign_in, extractor, words):
    # Category memory compares keys computed in SQL with keys computed in Python; accents and Arabic must sort the
    # same way in both, or a stored name would never be found again.
    alice, _ = sign_in()
    confirm_manually(client, alice, [(" ".join(words), "Groceries", None)])
    draft = read_by_model(client, alice, extractor, line(" ".join(reversed(words))))
    assert draft["lines"][0]["category_id"] == category_id(client, alice, "Groceries")


# --- Brands ---


def test_a_brand_is_saved_tidied_and_can_be_corrected_or_cleared(client, sign_in, extractor):
    alice, _ = sign_in()
    draft = read_by_model(client, alice, extractor, line("spaghetti", brand=" Barilla "), line("crepe"))
    names_and_brands = [(row["normalized_name"], row["brand"]) for row in draft["lines"]]
    assert names_and_brands == [("spaghetti", "barilla"), ("crepe", None)]

    body = {"receipt_date": "2026-10-15", "currency": "USD", "total": "2", "lines": [
        {"description": "BARILLA SPAGHETTI", "normalized_name": "spaghetti", "line_total": "1", "brand": "De Cecco"},
        {"description": "CREPE", "normalized_name": "crepe", "line_total": "1", "brand": ""},
    ]}  # fmt: skip
    confirmed = client.post(f"/receipts/{draft['id']}/confirm", json=body, headers=alice).json()
    assert [row["brand"] for row in confirmed["lines"]] == ["de cecco", None]  # an empty brand is no brand


def test_a_brand_with_a_nul_character_is_refused(client, sign_in):
    alice, _ = sign_in()
    body = {"receipt_date": "2026-10-15", "currency": "USD", "total": "1",
            "lines": [{"description": "x", "line_total": "1", "brand": "bar\u0000illa"}]}  # fmt: skip
    assert client.post("/receipts/manual", json=body, headers=alice).status_code == 422


def test_the_assistant_can_ask_for_a_brand(container, client, sign_in):
    # The user's question that led to the brand: "Barilla spaghetti five months ago vs now".
    if not Settings().readonly_database_url:
        pytest.skip("READONLY_DATABASE_URL is not set")
    alice, alice_id = sign_in()
    confirm_manually(client, alice, [("spaghetti", None, "barilla"), ("spaghetti", None, "de cecco")])
    result = container.assistant.run_query(
        alice_id, "SELECT item_name, brand FROM purchases WHERE item_name = 'spaghetti' AND brand = 'barilla'"
    )
    assert result.rows == [("spaghetti", "barilla")]


def test_known_item_names_respects_the_limit(engine, client, sign_in):
    alice, alice_id = sign_in()
    confirm_manually(client, alice, [("a", None, None), ("b", None, None), ("c", None, None)])
    with user_scoped_connection(engine, alice_id) as conn:
        assert SqlReceiptRepository(conn).known_item_names(2) == ["c", "b"]
