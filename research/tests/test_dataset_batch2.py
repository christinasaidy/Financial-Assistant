"""Batch 2 selection uses planned receipts only; never connects to a database."""

from collections import Counter, defaultdict
from dataclasses import replace

import pytest
from app.domain.assistant.prompt import VIEW_CATEGORIES, UserNames
from app.infrastructure.sql.query_rules import SqlGlotQueryRules
from app.infrastructure.sql.sql_guard import SqlGlotGuard

from research.dataset import batch2, templates
from research.dataset.batch2 import make_batch2_plan, make_batch2_specs
from research.dataset.catalogue import load_catalogue
from research.dataset.templates import UserData, make_specs
from research.dataset.users import make_users


@pytest.fixture(scope="module")
def data():
    catalogue = load_catalogue()
    return [UserData(user, catalogue) for user in make_users(catalogue)]


@pytest.fixture(scope="module")
def train(data):
    return make_batch2_plan(data[:27], {n: 30 for n in range(1, 28)}, "approved")


@pytest.fixture(scope="module")
def validation(data):
    return make_batch2_plan(data[27:], {28: 40, 29: 40, 30: 40}, "approved")


def test_training_budget_covers_available_items_in_independent_families(data, train):
    counts, families = Counter(), defaultdict(set)
    for number, specs in train.specs.items():
        assert len(specs) == 30
        identities = [(s.template, s.target, s.description) for s in specs]
        assert len(set(identities)) == len(identities)
        for spec in specs:
            if spec.kind == "sql" and not spec.base and spec.labels.get("item"):
                name = spec.labels["item"]
                assert name in data[number - 1].items
                counts[name] += 1
                families[name].add(spec.labels["batch2_family"])
    available = {name for user in data[:27] for name in user.items}
    assert set(counts) == available
    assert all(counts[name] >= 3 and len(families[name]) >= 2 for name in available)
    assert not train.item_shortfalls


def test_direct_items_span_users_when_available(data, train):
    owners, selected = defaultdict(set), defaultdict(set)
    for user in data[:27]:
        for name in user.items:
            owners[name].add(user.user.number)
    for number, specs in train.specs.items():
        for spec in specs:
            if spec.kind == "sql" and not spec.base and spec.labels.get("item"):
                selected[spec.labels["item"]].add(number)
    assert all(len(selected[name]) >= min(2, len(users)) for name, users in owners.items())
    assert not train.diversity_shortfalls


def test_months_periods_boundaries_comparisons_and_brand_followups(train):
    specs = [s for rows in train.specs.values() for s in rows]
    periods = Counter(s.labels.get("period") for s in specs if s.kind == "sql")
    for month in range(1, 13):
        assert periods[f"month_{month}"] >= 2
        assert periods[f"since_month_{month}"] >= 2
    assert all(periods[p] >= 2 for p in (
        "last_week", "last_14_days", "last_2_weeks", "last_3_months", "since_start_of_year"))
    assert {s.labels.get("compared") for s in specs if s.template == "T13"} == {
        "per 100 g or ml", "per piece", "per unit"}
    assert {s.template for s in specs if s.kind == "clarify"} >= {f"C{i}" for i in range(1, 7)}
    assert {s.template for s in specs if s.kind == "unsupported"} == {f"U{i}" for i in range(1, 6)}
    assert {s.labels.get("group") for s in specs if s.template == "C5"} == {"gifts", "repairs"}
    assert {s.labels.get("period") for s in specs if s.template == "C4"} == {
        "kanoun", "semester", "awal el sene"}
    follows = [s for s in specs if s.template == "F7"]
    assert len(follows) >= 12
    for spec in follows:
        assert spec.base.template == "T9"
        assert "brand =" not in spec.base.target
        assert spec.labels["brand"] in spec.mentions[0]
        assert spec.base.labels["item"] == spec.labels["item"]
        assert spec.base.labels["period"] == spec.labels["period"]
        assert "brand =" in spec.target
    assert not train.feature_shortfalls


def test_brand_preserving_period_followup_keeps_brand_and_item(train):
    follows = [s for rows in train.specs.values() for s in rows if s.template == "F8"]
    assert len(follows) >= 6
    for spec in follows:
        assert spec.base.template == "T10"
        assert spec.base.labels["brand"] == spec.labels["brand"]
        assert spec.base.labels["item"] == spec.labels["item"]
        assert spec.base.labels["period"] != spec.labels["period"]
        condition = f"brand = {templates.quoted(spec.labels['brand'])}"
        assert condition in spec.base.target and condition in spec.target
        assert spec.base.mentions[0] == templates.item_words(
            load_catalogue().item(spec.labels["item"]))
        assert spec.labels["brand"] in spec.base.mentions[1]
        assert all(spec.labels["brand"] not in group for group in spec.mentions)


def test_all_existing_template_families_present_in_both_splits(train, validation):
    expected = set(templates.SQL_TEMPLATES) | set(templates.FOLLOW_UPS) | {"T3g", "F7", "F8"}
    expected |= set(templates.CLARIFY) | {f"U{i}" for i in range(1, 6)} | {f"R{i}" for i in range(1, 5)}
    for plan in (train, validation):
        actual = {s.template for rows in plan.specs.values() for s in rows}
        assert expected <= actual


def test_validation_reserves_months_boundary_variants_and_unit_regimes(validation):
    for month in range(1, 13):
        for prefix in ("month_", "since_month_"):
            assert validation.feature_counts.get(f"period:{prefix}{month}", 0) >= 1
    for unit in ("per 100 g or ml", "per piece", "per unit"):
        assert validation.feature_counts.get(f"comparison:{unit}", 0) >= 1
    for feature in ("unclear:kanoun", "unclear:semester", "unclear:awal el sene",
                    "missing:gifts", "missing:repairs"):
        assert validation.feature_counts.get(feature, 0) >= 1


def test_followups_never_count_towards_direct_item_quotas(data, monkeypatch):
    candidates = batch2._candidates(data[0], "follow-only")
    follow = next(s for s in candidates if s.template == "F7")
    monkeypatch.setattr(batch2, "_candidates", lambda *args: [follow])
    plan = make_batch2_plan([data[0]], {1: 1}, "follow-only")
    assert plan.item_shortfalls[follow.labels["item"]] == (3, 2)
    assert not any(key.startswith("period:") for key in plan.feature_counts)


def test_exhausted_pool_is_explicit_and_empty_input_is_valid(data, monkeypatch):
    monkeypatch.setattr(batch2, "_candidates", lambda *args: [])
    with pytest.raises(ValueError, match="candidate pool"):
        make_batch2_specs(data[0], 1, "too-many")
    assert make_batch2_plan([], {}, "empty").specs == {}


def test_selected_sql_and_followup_bases_pass_guard_and_rules(data, train, validation):
    guard, rules = SqlGlotGuard(), SqlGlotQueryRules()
    for number, specs in (train.specs | validation.specs).items():
        user = data[number - 1]
        names = UserNames(user.items, user.shops, list(user.catalogue.default_categories)
                          + list(user.user.private_categories) + list(VIEW_CATEGORIES))
        for spec in specs:
            if spec.kind == "sql":
                rules.prepare(guard.check(spec.target), names, user.today)
                if spec.base:
                    rules.prepare(guard.check(spec.base.target), names, user.today)


def test_deterministic_seed_order_and_batch1_unchanged(data):
    before = make_specs(data[0], 24, "fyp-dataset/specs/1")
    first = make_batch2_plan(data[:2], {1: 20, 2: 20}, "a")
    assert first == make_batch2_plan(list(reversed(data[:2])), {2: 20, 1: 20}, "a")
    assert first.specs != make_batch2_plan(data[:2], {1: 20, 2: 20}, "b").specs
    assert before == make_specs(data[0], 24, "fyp-dataset/specs/1")
    assert make_batch2_specs(data[0], 20, "a") == make_batch2_plan([data[0]], {1: 20}, "a").specs[1]


def test_validation_and_small_budgets_report_unattained_quotas(data, validation):
    plan = validation
    assert sum(map(len, plan.specs.values())) == 120
    assert plan.item_shortfalls  # 120 cannot supply three specs for every available item.
    kinds = Counter(s.kind for rows in plan.specs.values() for s in rows)
    assert kinds["clarify"] >= 6 and kinds["unsupported"] >= 5
    assert all(n in (28, 29, 30) for n in plan.specs)
    empty = make_batch2_plan([data[0]], {1: 0}, "zero")
    assert empty.specs == {1: []}
    assert len(empty.item_shortfalls) == len(data[0].items)


def test_invalid_users_counts_and_split_mixing_are_rejected(data):
    with pytest.raises(ValueError, match="1.*30"):
        make_batch2_specs(UserData(replace(data[0].user, number=31), data[0].catalogue), 1, "x")
    for count in (-1, 1.5, True):
        with pytest.raises(ValueError):
            make_batch2_specs(data[0], count, "x")
    with pytest.raises(ValueError):
        make_batch2_plan([data[0], data[27]], {1: 10, 28: 10}, "x")
    with pytest.raises(ValueError):
        make_batch2_plan([data[0], data[0]], {1: 10}, "x")
    with pytest.raises(ValueError):
        make_batch2_plan([data[0]], {}, "x")


@pytest.mark.parametrize("number", [3, 7, 18, 30])
def test_f6_candidates_have_no_period_to_silently_discard(data, number):
    split = "train" if number <= 27 else "validation"
    candidates = batch2._candidates(data[number - 1], f"{batch2.SEED_PREFIX}/{split}")
    follows = [s for s in candidates if s.template == "F6"]
    assert follows
    for spec in follows:
        assert spec.base.labels["period"] == "none", spec.base.description
        assert spec.labels["period"] == "none"
        assert spec.labels["item"] == spec.base.labels["item"]
        assert "receipt_date =" not in spec.target
        assert "receipt_date >" not in spec.target
        assert "receipt_date <" not in spec.target


@pytest.mark.parametrize(("split", "first", "last", "count"), [
    ("train", 1, 27, 30), ("validation", 28, 30, 50),
])
def test_production_selection_independently_recounts_coverage(data, split, first, last, count):
    """Match prepare's counts/seeds without importing or running its DB workflow."""
    users = data[first - 1:last]
    plan = make_batch2_plan(users, dict.fromkeys(range(first, last + 1), count),
                            f"{batch2.SEED_PREFIX}/{split}")
    owners, selected_users, families = defaultdict(set), defaultdict(set), defaultdict(set)
    direct, periods_seen, templates_seen = Counter(), Counter(), Counter()
    semantic_family = {
        "T9": "spending", "T10": "spending",
        "T11": "latest", "T11k": "latest",
        "T12": "average", "T12k": "average",
        "T13": "comparison", "T14": "frequency",
        "T15": "quantity", "T18": "quantity",
    }
    for user in users:
        number = user.user.number
        for name in user.items:
            owners[name].add(number)
        assert len(plan.specs[number]) == count
        periods_by_kind = {p.kind: p for p in templates._all_periods(user)}
        for spec in plan.specs[number]:
            templates_seen[spec.template] += 1
            if spec.template == "F6":
                assert spec.base.labels["period"] == spec.labels["period"] == "none"
            if spec.kind == "sql" and spec.base is None and spec.labels.get("item"):
                name = spec.labels["item"]
                assert templates.item_words(user.catalogue.item(name)) in spec.mentions
                assert templates.item_is(name) in spec.target
                direct[name] += 1
                families[name].add(semantic_family[spec.template])
                selected_users[name].add(number)
            period = spec.labels.get("period")
            if spec.kind == "sql" and period in periods_by_kind:
                p = periods_by_kind[period]
                # Count the new question's explicit words, not inherited metadata.
                if p.words and p.words in spec.mentions:
                    assert p.sql in spec.target
                    periods_seen[period] += 1
    missing_items = {
        name: (max(0, 3 - direct[name]), max(0, 2 - len(families[name])))
        for name in owners if direct[name] < 3 or len(families[name]) < 2
    }
    missing_users = {
        name: min(2, len(owners[name])) - len(selected_users[name])
        for name in owners if len(selected_users[name]) < min(2, len(owners[name]))
    }
    assert plan.item_shortfalls == missing_items
    assert plan.diversity_shortfalls == missing_users
    assert templates_seen["F6"] >= 1
    for month in range(1, 13):
        for prefix in ("month_", "since_month_"):
            period = f"{prefix}{month}"
            assert periods_seen[period] >= (2 if split == "train" else 1)
            assert plan.feature_counts[f"period:{period}"] == periods_seen[period]
    if split == "train":
        assert not missing_items and not missing_users
        assert not plan.feature_shortfalls
    else:
        assert missing_items  # Even 150 cannot cover 151 items three times.
