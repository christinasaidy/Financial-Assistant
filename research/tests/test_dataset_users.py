"""The dataset's catalogue and synthetic users. The choices were delegated to the assistant by the user on 2026-11-08
(recorded in research/dataset/users.py); do not change an expected value to make a test pass."""

import json
import tempfile
from collections import Counter
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from research.dataset.catalogue import CATALOGUE_FILE, CatalogueError, load_catalogue
from research.dataset.users import (
    HISTORY_DAYS,
    RATE,
    PlannedLine,
    _Planner,
    _printed,
    make_user,
    make_users,
    remove_user,
    seed_user,
)
from research.evaluation.expected_model import ExpectedAnswersModel
from research.evaluation.wiring import build_evaluation

CATALOGUE = load_catalogue()
USERS = make_users(CATALOGUE)


# --- The catalogue ---


def test_the_catalogue_loads_with_its_checks():
    assert (len(CATALOGUE.items), len(CATALOGUE.shops)) == (197, 73)


def _broken(change) -> Path:
    data = json.loads(CATALOGUE_FILE.read_text(encoding="utf-8"))
    change(data)
    path = Path(tempfile.mkdtemp()) / "catalogue.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize(("change", "message"), [
    (lambda d: d["items"][0].update(category="Snacks"), "unknown category Snacks"),
    (lambda d: d["items"][1].update(words=["may"]), "spelling on two items: may"),
    (lambda d: d["items"][0].update(price=[1, 2]), "needs exactly one of sizes"),
    (lambda d: d["items"][0].update(at=["spaceport"]), "no shop of kind spaceport"),
    (lambda d: d["items"].append(dict(d["items"][0])), "item listed twice: water"),
])  # fmt: skip
def test_mistakes_in_the_catalogue_stop_it_loading(change, message):
    with pytest.raises(CatalogueError, match=message):
        load_catalogue(_broken(change))


# --- Who the users are ---


def test_the_same_number_always_gives_the_same_user():
    assert make_user(CATALOGUE, 7) == make_user(CATALOGUE, 7)
    assert make_user(CATALOGUE, 7) != make_user(CATALOGUE, 8)


def test_todays_are_spread_over_2025_to_2027_and_cover_every_month_and_weekday():
    todays = [user.today for user in USERS]
    assert todays == sorted(todays) and len(set(todays)) == 30
    assert todays[0].isoformat() >= "2025-03-01" and todays[-1].year == 2027
    assert {d.month for d in todays} == set(range(1, 13))
    assert {d.weekday() for d in todays} == set(range(7))


def test_each_user_has_about_150_to_250_receipts_within_14_months_before_today():
    for user in USERS:
        assert 150 <= len(user.receipts) <= 300, user.number
        assert all(user.today - timedelta(days=HISTORY_DAYS) <= r.day <= user.today for r in user.receipts)
    counts = sorted(len(user.receipts) for user in USERS)
    assert 150 <= counts[15] <= 250  # the median


def test_receipts_come_only_from_the_users_shops_and_items_sold_there():
    kinds = {shop.name: shop.kind for shop in CATALOGUE.shops}
    for user in USERS:
        for receipt in user.receipts:
            assert receipt.shop in user.shops
            for line in receipt.lines:
                item = CATALOGUE.item(line.item)
                assert line.item in user.items and kinds[receipt.shop] in item.at
                assert not item.vendors or receipt.shop in item.vendors


def test_users_without_a_car_pet_or_habit_never_buy_for_one():
    for user in USERS:
        items = set(user.items)
        planner = _Planner(CATALOGUE, user.number)
        if not planner.has_car:
            assert not items & {"fuel", "car wash", "parking"}
        if not planner.has_pet:
            assert not items & {"cat food", "dog food", "cat litter", "pet treats"} and "Pets" not in user.private_categories
        if not planner.smokes:
            assert not items & {"cigarettes", "tobacco sticks", "heated tobacco device"}
            assert "Tobacco" not in user.private_categories


# --- The receipts ---


def _lines():
    return [(user, receipt, line) for user in USERS for receipt in user.receipts for line in receipt.lines]


def test_amounts_are_rounded_as_prices_are_written():
    for _, receipt, line in _lines():
        if receipt.currency == "LBP":
            assert line.line_total % 1000 == 0 and line.line_total >= 1000
        else:
            assert (line.line_total * 20) % 1 == 0 and line.line_total >= Decimal("0.05")


def test_a_line_total_is_its_unit_price_times_its_quantity():
    for _, _, line in _lines():
        if line.unit_price is not None:
            assert line.line_total == line.unit_price * line.quantity


def test_weighed_food_and_fuel_are_their_weight_or_volume_with_quantity_1():
    for _, _, line in _lines():
        item = CATALOGUE.item(line.item)
        if item.weight_g:
            assert (line.size_unit, line.quantity) == ("g", 1) and item.weight_g[0] <= line.size_amount <= item.weight_g[1]
        if item.litres:
            assert (line.size_unit, line.quantity) == ("ml", 1) and line.size_amount % 1000 == 0


def test_only_food_and_drink_come_more_than_two_to_a_line():
    for _, receipt, line in _lines():
        if line.quantity > 2:
            assert CATALOGUE.item(line.item).category in ("Groceries", "Dining"), line


def test_the_mix_of_receipts_matches_the_decisions():
    receipts = [receipt for user in USERS for receipt in user.receipts]
    lines = [line for _, _, line in _lines()]
    assert 0.25 <= sum(r.currency == "LBP" for r in receipts) / len(receipts) <= 0.45
    assert 0.2 <= sum(line.unit_price is None for line in lines) / len(lines) <= 0.35
    assert 0 < sum(not r.lines for r in receipts) / len(receipts) <= 0.05
    differing = [r for r in receipts if r.lines and r.total != sum(line.line_total for line in r.lines)]
    assert 0.05 <= len(differing) / len(receipts) <= 0.2
    for receipt in differing:  # a service charge, a discount or LBP rounding: never far from the lines
        lines_total = sum(line.line_total for line in receipt.lines)
        assert abs(receipt.total - lines_total) <= max(lines_total * Decimal("0.11"), Decimal(10000))


def test_categories_follow_the_users_private_categories():
    private = set(CATALOGUE.private_categories)
    for user, receipt, line in _lines():
        for category in (receipt.category, line.category):
            if category in private:
                assert category in user.private_categories
        assert line.category != receipt.category  # a line names its category only when it differs
    assert Counter(c for user in USERS for c in user.private_categories).keys() == private


def test_bills_come_once_a_month_from_their_own_shop():
    for user in USERS:
        edl = [r.day for r in user.receipts if r.shop == "EDL"]
        if edl:
            assert len({d.day for d in edl}) == 1  # always the same day of the month
            assert len({(d.year, d.month) for d in edl}) == len(edl)
            assert all(line.item == "electricity bill" for r in user.receipts if r.shop == "EDL" for line in r.lines)


def test_money_is_rounded_to_005_dollars_or_5000_pounds():
    money = _Planner._money
    assert money(2.42, "USD") == Decimal("2.40") and money(2.43, "USD") == Decimal("2.45")
    assert money(0.01, "USD") == Decimal("0.05")
    assert money(1.0, "LBP") == Decimal(90000)  # 89,500 rounded to 5,000
    assert money(1.0, "LBP", weighed=True) == Decimal(90000) and money(1.01, "LBP", weighed=True) == Decimal(90000)
    assert money(0.01, "LBP") == Decimal(5000)
    assert RATE == 89500


def test_a_line_is_printed_like_a_receipt():
    line = PlannedLine("water", "rim", Decimal(1500), "ml", Decimal(1), None, Decimal("0.60"), None)
    assert _printed(line) == "RIM WATER 1500ML"
    assert _printed(PlannedLine("bread", None, None, None, Decimal(1), None, Decimal(1), None)) == "BREAD"


# --- Writing a user to the database ---


def test_a_seeded_user_has_exactly_the_planned_receipts_and_is_removed(settings):
    user = next(user for user in USERS if user.private_categories)
    with tempfile.TemporaryDirectory() as storage:
        services = build_evaluation(settings, ExpectedAnswersModel([]), user.today, Path(storage))
        user_id = seed_user(services, user)
        try:
            count, total_usd = services.assistant.run_query(
                user_id, "SELECT COUNT(*), SUM(total_usd) FROM receipts").rows[0]
            planned = sum(r.total if r.currency == "USD" else r.total / RATE for r in user.receipts)
            assert count == len(user.receipts)
            assert round(total_usd, 2) == round(planned, 2)
            lines = services.assistant.run_query(user_id, "SELECT COUNT(*) FROM purchases").rows[0][0]
            assert lines == sum(len(r.lines) for r in user.receipts)
            names = {c.name for c in services.categories.list_all(user_id) if not c.is_shared}
            assert names == set(user.private_categories)
        finally:
            remove_user(services, user_id)
        with create_engine(settings.database_url).connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM users WHERE id = :id"), {"id": user_id}).scalar_one() == 0


def test_a_user_is_the_same_in_every_python_process():
    """Sets iterate in a different order in each process (hash randomisation); the plan must not depend on it."""
    import os
    import subprocess
    import sys

    script = ("from research.dataset.catalogue import load_catalogue; from research.dataset.users import make_user; "
              "c = load_catalogue(); print([(len(u.receipts), u.items, sum(r.total for r in u.receipts)) "
              "for u in (make_user(c, n) for n in range(1, 31))])")
    outputs = set()
    for seed in ("1", "2", "3"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        outputs.add(subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env,
                                   cwd=Path(__file__).resolve().parents[2], check=True).stdout)  # fmt: skip
    assert len(outputs) == 1
