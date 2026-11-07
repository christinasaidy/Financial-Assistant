"""The dataset's periods and templates. The SQL shapes and the worked examples (today 2027-02-10) were approved by
the user on 2026-11-05 and 2026-11-07; do not change an expected value to make a test pass."""

import random
import tempfile
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from app.domain.assistant.prompt import VIEW_CATEGORIES, UserNames
from app.infrastructure.sql.query_rules import SqlGlotQueryRules
from app.infrastructure.sql.sql_guard import SqlGlotGuard

from research.dataset import periods, templates
from research.dataset.catalogue import load_catalogue
from research.dataset.templates import UserData, make_specs
from research.dataset.users import (
    PlannedLine,
    PlannedReceipt,
    SyntheticUser,
    make_users,
    remove_user,
    seed_user,
)
from research.evaluation.expected_model import ExpectedAnswersModel
from research.evaluation.wiring import build_evaluation

CATALOGUE = load_catalogue()
TODAY = date(2027, 2, 10)  # a Wednesday
GUARD, RULES = SqlGlotGuard(), SqlGlotQueryRules()


# --- Periods (the approved table) ---


@pytest.mark.parametrize(("period", "start", "end", "sql"), [
    (periods.today_period(TODAY), "2027-02-10", "2027-02-11", "receipt_date = CURRENT_DATE"),
    (periods.yesterday(TODAY), "2027-02-09", "2027-02-10", "receipt_date = CURRENT_DATE - 1"),
    (periods.this_week(TODAY), "2027-02-08", "2027-02-15", periods.THIS_WEEK),
    (periods.last_week(TODAY), "2027-02-01", "2027-02-08", periods.LAST_WEEK),
    (periods.last_days(TODAY, 7), "2027-02-04", "2027-02-11",
     "receipt_date > CURRENT_DATE - 7 AND receipt_date <= CURRENT_DATE"),
    (periods.last_weeks(TODAY, 2), "2027-01-28", "2027-02-11",
     "receipt_date > CURRENT_DATE - 14 AND receipt_date <= CURRENT_DATE"),
    (periods.last_months(TODAY, 3), "2026-11-11", "2027-02-11",
     "receipt_date > CURRENT_DATE - INTERVAL '3 months' AND receipt_date <= CURRENT_DATE"),
    (periods.since_start_of_year(TODAY), "2027-01-01", "2027-02-11", "receipt_date >= date_trunc('year', CURRENT_DATE)"),
    (periods.weekday(TODAY, 0), "2027-02-08", "2027-02-09", "receipt_date = '2027-02-08'"),  # nhar el tanayn
    (periods.weekday(TODAY, 2), "2027-02-10", "2027-02-11", "receipt_date = '2027-02-10'"),  # today is Wednesday
    (periods.weekday(TODAY, 4), "2027-02-05", "2027-02-06", "receipt_date = '2027-02-05'"),  # nhar el jem3a
    (periods.weekend(TODAY), "2027-02-06", "2027-02-08", "receipt_date >= '2027-02-06' AND receipt_date < '2027-02-08'"),
    (periods.weekend(date(2027, 2, 13)), "2027-02-13", "2027-02-15",
     "receipt_date >= '2027-02-13' AND receipt_date < '2027-02-15'"),  # asked on a Saturday
    (periods.summer(TODAY), "2026-06-01", "2026-09-01", "receipt_date >= '2026-06-01' AND receipt_date < '2026-09-01'"),
    (periods.day_range(TODAY, 10, 1, 15), "2026-10-01", "2026-10-16",
     "receipt_date >= '2026-10-01' AND receipt_date < '2026-10-16'"),
    (periods.named_month(TODAY, 10), "2026-10-01", "2026-11-01",
     "receipt_date >= '2026-10-01' AND receipt_date < '2026-11-01'"),
    (periods.named_month(TODAY, 2), "2027-02-01", "2027-03-01",
     "receipt_date >= '2027-02-01' AND receipt_date < '2027-03-01'"),
    (periods.since_month(TODAY, 8), "2026-08-01", "2027-02-11", "receipt_date >= '2026-08-01'"),
])  # fmt: skip
def test_each_period_covers_the_approved_days(period, start, end, sql):
    assert (period.start.isoformat(), period.end.isoformat(), period.sql) == (start, end, sql)


def test_the_last_n_months_moves_to_the_months_last_day_like_postgresql():
    assert periods.last_months(date(2027, 5, 31), 3).start == date(2027, 3, 1)  # 28 February + 1 day
    assert periods.last_months(date(2027, 4, 30), 2).start == date(2027, 3, 1)  # 28 February + 1 day


def test_this_month_and_last_month_are_chosen_about_twice_as_often():
    rng = random.Random(1)
    kinds = Counter(periods.choose(rng, TODAY, date(2026, 1, 1)).kind for _ in range(4000))
    assert 1.5 <= kinds["this_month"] / kinds["this_week"] <= 2.6
    assert kinds["summer"] > 0 and kinds["none"] > 0


def test_a_named_period_before_the_users_first_receipt_is_never_chosen():
    rng = random.Random(2)
    for _ in range(500):
        period = periods.choose(rng, TODAY, date(2026, 12, 1))
        assert period.start is None or period.start >= date(2026, 12, 1)


# --- Hand-made users holding the approved worked examples ---


def line(item, size=None, unit=None, quantity="1", price=None, total="0", brand=None, category=None):
    return PlannedLine(item, brand, Decimal(size) if size else None, unit, Decimal(quantity),
                       Decimal(price) if price else None, Decimal(total), category)  # fmt: skip


def receipt(day, shop, total, lines=(), currency="USD", category="Groceries"):
    return PlannedReceipt(date.fromisoformat(day), shop, currency, Decimal(total), category, tuple(lines))


def hand_made(number, receipts, private=()):
    return SyntheticUser(number, TODAY, tuple(private), tuple(sorted({r.shop for r in receipts})),
                         tuple(sorted({ln.item for r in receipts for ln in r.lines})), tuple(receipts))  # fmt: skip


LABAN_USER = hand_made(901, [
    receipt("2026-12-05", "Spinneys", "10.00", [line("laban", "1000", "g", price="3.00", total="3.00")]),
    receipt("2027-01-03", "Spinneys", "20.00"),
    receipt("2027-01-08", "Carrefour", "30.00", [line("laban", "1000", "g", price="3.40", total="3.40")]),
    receipt("2027-01-15", "Malak el Tawouk", "12.00", category="Dining"),
    receipt("2027-01-20", "Spinneys", "25.00", [line("laban", "500", "g", quantity="2", price="1.80", total="3.60")]),
    receipt("2027-02-03", "Carrefour", "18.00", [line("laban", "1000", "g", price="3.60", total="3.60")]),
    receipt("2027-02-05", "Fahed Supermarket", "1790000", currency="LBP"),
    receipt("2027-02-07", "Spinneys", "22.00", [line("laban", "1000", "g", price="3.50", total="3.50")]),
])
SIZES_USER = hand_made(902, [
    receipt("2027-02-01", "Spinneys", "5.20", [line("rice", "2000", "g", total="4.20"),
                                               line("bread", price="1.00", total="1.00")]),
    receipt("2027-02-02", "Carrefour", "5.70", [line("rice", "1000", "g", quantity="2", price="2.40", total="4.80"),
                                                line("bread", price="0.90", total="0.90")]),
    receipt("2027-02-03", "Fahed Supermarket", "9.50", [line("eggs", "30", "pcs", price="6.00", total="6.00"),
                                                        line("eggs", price="3.50", total="3.50")]),
    receipt("2027-02-04", "Happy", "3.00", [line("eggs", "12", "pcs", price="3.00", total="3.00")]),
])  # fmt: skip
GROUPS_USER = hand_made(903, [
    receipt("2027-02-05", "Zara", "21.00", [line("t-shirt", price="15.00", total="15.00"),
                                            line("socks", "3", "pcs", price="6.00", total="6.00")], category="Shopping"),
    receipt("2027-02-06", "Spinneys", "5.00", [line("chips", "150", "g", price="2.00", total="2.00"),
                                               line("laban", "1000", "g", price="3.00", total="3.00")]),
    receipt("2027-01-20", "Abou Jihad", "3000000", [line("cigarettes", "20", "pcs", price="3000000", total="3000000")],
            currency="LBP"),
])  # fmt: skip


@pytest.fixture
def run_for(settings):
    """Seeds a user once and runs SQL for them as the app would (the date filled in, guard, read-only role)."""
    seeded: list = []

    def _run_for(user):
        storage = tempfile.mkdtemp()
        services = build_evaluation(settings, ExpectedAnswersModel([]), user.today, Path(storage))
        user_id = seed_user(services, user)
        seeded.append((services, user_id))
        data = UserData(user, CATALOGUE)
        names = UserNames(data.items, data.shops, list(CATALOGUE.default_categories) + list(user.private_categories)
                          + list(VIEW_CATEGORIES))  # fmt: skip
        return lambda sql: services.assistant.run_query(user_id, RULES.prepare(GUARD.check(sql), names, user.today)).rows

    yield _run_for
    for services, user_id in seeded:
        remove_user(services, user_id)


def spec_for(maker, user, monkeypatch, period=None, wanted=lambda spec: True):
    """The spec a template makes for a hand-made user; the period fixed when given, and the first seed whose spec
    is the one wanted (a template picks among the user's items at random)."""
    if period is not None:
        monkeypatch.setattr(templates, "_period", lambda data, rng: period)
    data = UserData(user, CATALOGUE)
    for seed in range(200):
        spec = maker(data, random.Random(seed))
        if spec is not None and wanted(spec):
            return spec
    raise AssertionError("no seed gave the wanted spec")


# --- The approved worked examples: exact SQL and result ---


def test_f5_the_price_before_the_last(run_for, monkeypatch):
    spec = spec_for(templates.f5_price_before_last, LABAN_USER, monkeypatch)
    assert spec.target == ("SELECT receipt_date, vendor, currency, COALESCE(unit_price, line_total / quantity) AS price, "
                           "size_amount, size_unit FROM purchases WHERE item_name = 'laban' "
                           "ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1 OFFSET 1")  # fmt: skip
    assert run_for(LABAN_USER)(spec.target) == [(date(2027, 2, 3), "Carrefour", "USD", Decimal("3.60"),
                                                 Decimal("1000.000"), "g")]  # fmt: skip
    assert spec.base.template == "T11" and spec.base.target + " OFFSET 1" == spec.target


def test_f6_where_it_was_last_bought(run_for, monkeypatch):
    spec = spec_for(templates.f6_where_last_bought, LABAN_USER, monkeypatch)
    assert spec.target == ("SELECT receipt_date, vendor FROM purchases WHERE item_name = 'laban' "
                           "ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1")
    assert run_for(LABAN_USER)(spec.target) == [(date(2027, 2, 7), "Spinneys")]


def test_t12k_the_average_per_kilo(run_for, monkeypatch):
    spec = spec_for(templates.t12k_average_per_kilo, LABAN_USER, monkeypatch, periods.no_period())
    price = "COALESCE(unit_price, line_total / quantity) / size_amount * 1000"
    assert spec.target == (f"SELECT currency, COUNT(*) AS purchase_count, ROUND(AVG({price}), 2) AS "
                           f"average_price_per_kilo, ROUND(MIN({price}), 2) AS lowest_per_kilo, ROUND(MAX({price}), 2) "
                           "AS highest_per_kilo FROM purchases WHERE item_name = 'laban' AND size_unit = 'g' "
                           "GROUP BY currency")  # fmt: skip
    assert run_for(LABAN_USER)(spec.target) == [("USD", 5, Decimal("3.42"), Decimal("3.00"), Decimal("3.60"))]


def test_t19_this_month_so_far_against_the_same_days_last_month(run_for):
    spec = templates.t19_month_so_far(UserData(LABAN_USER, CATALOGUE), random.Random(0))
    rows = run_for(LABAN_USER)(spec.target)
    assert [(month.date(), currency, total) for month, currency, total, _ in rows] == [
        (date(2027, 1, 1), "USD", Decimal("50.00")),  # 1-10 January: 20 + 30
        (date(2027, 2, 1), "LBP", Decimal("1790000.00")),
        (date(2027, 2, 1), "USD", Decimal("40.00")),  # 1-10 February: 18 + 22
    ]


def test_t20_the_percent_change(run_for):
    spec = templates.t20_percent_change(UserData(LABAN_USER, CATALOGUE), random.Random(0))
    (this, last, change), = run_for(LABAN_USER)(spec.target)
    assert (round(this, 2), round(last, 2), change) == (Decimal("60.00"), Decimal("87.00"), Decimal("-31.0"))


def test_t7_the_top_shop_with_its_total(run_for, monkeypatch):
    spec = spec_for(templates.t7_top_shop, LABAN_USER, monkeypatch, periods.this_year(TODAY))
    assert spec.target == (f"SELECT vendor, SUM(total_usd) AS total_spent_usd FROM receipts WHERE {periods.THIS_YEAR} "
                           "GROUP BY vendor ORDER BY total_spent_usd DESC LIMIT 1")
    assert run_for(LABAN_USER)(spec.target) == [("Spinneys", Decimal("67.00"))]  # December is last year


@pytest.mark.parametrize(("item", "expected"), [
    ("rice", [("Carrefour", "USD", 1, Decimal("0.24")), ("Spinneys", "USD", 1, Decimal("0.21"))]),  # per 100 g
    ("eggs", [("Fahed Supermarket", "USD", 1, Decimal("0.20")), ("Happy", "USD", 1, Decimal("0.25"))]),  # per piece
    ("bread", [("Carrefour", "USD", 1, Decimal("0.90")), ("Spinneys", "USD", 1, Decimal("1.00"))]),  # per unit
])  # fmt: skip
def test_t13_compares_per_100_g_per_piece_or_per_unit(run_for, monkeypatch, item, expected):
    spec = spec_for(templates.t13_compare_shops, SIZES_USER, monkeypatch, periods.no_period(),
                    lambda s: s.labels["item"] == item)  # fmt: skip
    assert sorted(run_for(SIZES_USER)(spec.target)) == expected


def test_t11k_the_latest_price_per_kilo(run_for, monkeypatch):
    spec = spec_for(templates.t11k_latest_per_kilo, SIZES_USER, monkeypatch)
    assert run_for(SIZES_USER)(spec.target) == [(date(2027, 2, 2), "Carrefour", "USD", Decimal("2.40"))]


@pytest.mark.parametrize(("item", "expected"), [("rice", [(Decimal(4), 0)]), ("eggs", [(Decimal("3.5"), 1)])])
def test_t18_kilos_and_dozens(run_for, monkeypatch, item, expected):
    spec = spec_for(templates.t18_weight, SIZES_USER, monkeypatch, periods.no_period(),
                    lambda s: s.labels["item"] == item)  # fmt: skip
    assert run_for(SIZES_USER)(spec.target) == expected
    if item == "rice":
        assert spec.target == ("SELECT SUM(quantity * size_amount) FILTER (WHERE size_unit = 'g') / 1000 AS kilos, "
                               "COUNT(*) FILTER (WHERE size_amount IS NULL) AS purchases_without_size FROM purchases "
                               "WHERE item_name = 'rice'")  # fmt: skip


def test_a_kind_of_product_is_the_users_items_of_that_kind(run_for, monkeypatch):
    run = run_for(GROUPS_USER)
    clothes = spec_for(templates.t3_category, GROUPS_USER, monkeypatch, periods.this_month(TODAY),
                       lambda s: s.labels.get("group") == "clothes")  # fmt: skip
    assert "item_name IN ('socks', 't-shirt')" in clothes.target
    assert run(clothes.target) == [("USD", Decimal("21.00"), Decimal("21.00"))]
    tobacco = spec_for(templates.t3_category, GROUPS_USER, monkeypatch, periods.no_period(),
                       lambda s: s.labels.get("group") == "tobacco")  # fmt: skip
    assert "item_name IN ('cigarettes')" in tobacco.target  # no Tobacco category: its items
    (currency, spent, _), = run(tobacco.target)
    assert (currency, spent) == ("LBP", Decimal("3000000.00"))


# --- Every template, for real synthetic users ---


USERS = make_users(CATALOGUE)


def names_of(data: UserData) -> UserNames:
    return UserNames(data.items, data.shops, list(CATALOGUE.default_categories) + list(data.user.private_categories)
                     + list(VIEW_CATEGORIES))  # fmt: skip


def all_specs():
    for user in USERS:
        data = UserData(user, CATALOGUE)
        yield data, make_specs(data, 24, f"test/{user.number}")


def test_the_specs_are_the_same_from_the_same_seed():
    data = UserData(USERS[0], CATALOGUE)
    assert make_specs(data, 24, "a") == make_specs(data, 24, "a")


def test_the_mix_of_things_asked_matches_the_decisions():
    kinds = Counter()
    for _, specs in all_specs():
        for spec in specs:
            kinds["follow_up" if spec.base else spec.kind] += 1
    total = sum(kinds.values())
    assert total == 30 * 24
    share = {kind: count / total for kind, count in kinds.items()}
    assert 0.53 <= share["sql"] <= 0.67 and 0.10 <= share["follow_up"] <= 0.20
    assert 0.06 <= share["clarify"] <= 0.14 and 0.04 <= share["unsupported"] <= 0.12 and 0.03 <= share["reply"] <= 0.11


def test_every_sql_passes_the_guard_and_the_rules():
    for data, specs in all_specs():
        for spec in specs:
            for sql in (spec.target, spec.base.target if spec.base else None):
                if spec.kind == "sql" and sql:
                    RULES.prepare(GUARD.check(sql), names_of(data), data.today)


def test_a_question_must_name_its_item_shop_and_period():
    for data, specs in all_specs():
        for spec in specs:
            if spec.template in ("T9", "T14", "T15", "T11", "T12"):
                assert data.catalogue.item(spec.labels["item"]).name in spec.mentions[0]
            if spec.template in ("T6", "T8"):
                assert spec.labels["shop"] in spec.mentions[0]
            period = spec.labels.get("period")
            if spec.kind == "sql" and not spec.base and period not in (None, "none", "month_so_far", "two_months") \
                    and "+" not in period:
                assert spec.mentions[-1] == next(p for p in templates._all_periods(data) if p.kind == period).words


def test_clarify_asks_about_what_the_user_does_not_have():
    for data, specs in all_specs():
        for spec in specs:
            if spec.template == "C1":
                assert spec.labels["item"] not in data.items and spec.labels["suggestion"] in data.items
            if spec.template == "C2":
                assert spec.labels["shop"] not in data.shops


def test_a_synthetic_users_questions_all_run_and_totals_match_their_receipts(run_for):
    user = USERS[2]
    run = run_for(user)
    data = UserData(user, CATALOGUE)
    specs = [s for s in make_specs(data, 80, "test/run") if s.kind == "sql"]
    empty = 0
    for spec in specs:
        for sql in (spec.target, spec.base.target if spec.base else None):
            if sql:
                rows = run(sql)
                empty += sql == spec.target and (not rows or all(v in (None, 0) for v in rows[0]))
    assert empty / len(specs) <= 0.35, empty / len(specs)  # the share itself is pinned by the test below

    def usd(amount, currency):
        return amount if currency == "USD" else amount / Decimal(89500)

    checked = 0
    for spec in specs:
        if spec.template == "T1" and not spec.base:
            period = next(p for p in templates._all_periods(data) if p.kind == spec.labels["period"])
            planned = sum(usd(r.total, r.currency) for r in data.receipts_in(period))
            rows = run(spec.target)
            assert round(sum(row[2] for row in rows), 2) == round(planned, 2), spec.labels
            checked += 1
    assert checked >= 2


def test_about_one_item_or_shop_question_in_ten_asks_about_a_period_with_nothing_bought():
    asked = empty = 0
    for data, specs in all_specs():
        for spec in (s for s in specs if s.template in ("T6", "T8", "T9", "T14", "T15") and not s.base):
            period = next(p for p in templates._all_periods(data) if p.kind == spec.labels["period"])
            if period.start is None:
                continue
            asked += 1
            bought = data.bought(period, item=spec.labels.get("item"), shop=spec.labels.get("shop"))
            empty += not bought and not any(r.shop == spec.labels.get("shop") for r in data.receipts_in(period))
    assert asked >= 60
    assert 0.05 <= empty / asked <= 0.16, empty / asked
