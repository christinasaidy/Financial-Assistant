"""Batch 3 (approved by the user on 2026-11-15): the catalogue extension, the new periods and the batch-3 users.
Batch 1 and 2 must stay exactly as they were. Do not change an expected value to make a test pass."""

from datetime import date

from research.dataset import periods
from research.dataset.catalogue import BATCH3_EXTENSION, load_catalogue
from research.dataset.users import make_user

TUESDAY = date(2027, 2, 9)
WEDNESDAY = date(2027, 2, 10)


def test_the_base_catalogue_is_unchanged():
    base = load_catalogue()
    assert "beer" not in {item.name for item in base.items}
    assert "Foodies" not in {shop.name for shop in base.shops}
    assert "dekhan" not in base.item("cigarettes").spellings
    assert "dove" not in base.item("shampoo").brands


def test_the_extension_adds_the_seeds_items_shops_and_spellings():
    extended = load_catalogue(extension=BATCH3_EXTENSION)
    names = {item.name for item in extended.items}
    assert {"beer", "protein bars", "hair dye", "argile", "mouthwash", "powdered milk"} <= names
    assert {"Foodies", "Kadri", "Coop"} <= {shop.name for shop in extended.shops}
    assert "dekhan" in extended.item("cigarettes").spellings
    assert "3ela2at" in extended.item("hangers").spellings
    assert "dove" in extended.item("shampoo").brands
    assert len(extended.items) == len(load_catalogue().items) + 6


def test_the_day_before_yesterday():  # abel mbereh / awalt mbereh
    period = periods.day_before_yesterday(WEDNESDAY)
    assert (period.sql, period.start, period.end) == ("receipt_date = CURRENT_DATE - 2", date(2027, 2, 8), date(2027, 2, 9))
    assert {"abel mbereh", "awalt mbereh"} <= set(period.words)


def test_since_a_weekday_never_starts_today():  # asked on a Tuesday, "since Tuesday" is last week's Tuesday
    assert periods.since_weekday(TUESDAY, 1).sql == "receipt_date >= '2027-02-02'"
    assert periods.since_weekday(WEDNESDAY, 1).sql == "receipt_date >= '2027-02-09'"
    thursday = periods.since_weekday(WEDNESDAY, 3)
    assert (thursday.sql, thursday.start, thursday.end) == ("receipt_date >= '2027-02-04'", date(2027, 2, 4),
                                                            date(2027, 2, 11))  # fmt: skip
    assert "khamis" in thursday.words


def test_since_yesterday():  # men mberha la lyom
    period = periods.since_yesterday(WEDNESDAY)
    assert (period.sql, period.start, period.end) == ("receipt_date >= CURRENT_DATE - 1", date(2027, 2, 9),
                                                      date(2027, 2, 11))  # fmt: skip
    assert "men mberha" in period.words


def test_a_batch3_user_gets_the_given_today_and_existing_users_do_not_change():
    catalogue = load_catalogue()
    assert make_user(catalogue, 5).today == make_user(catalogue, 5, today=None).today
    assert make_user(load_catalogue(extension=BATCH3_EXTENSION), 32, today=date(2026, 3, 17)).today == date(2026, 3, 17)


# --- the plan and the job rules ---

from collections import Counter  # noqa: E402

import pytest  # noqa: E402

from app.infrastructure.sql.sql_guard import SqlGlotGuard  # noqa: E402
from research.dataset import batch3_build  # noqa: E402
from research.dataset.batch3 import TODAYS, TRAIN, VALIDATION, plan  # noqa: E402
from research.dataset.build import Job, UserNames  # noqa: E402


@pytest.fixture(scope="module")
def train_plan():
    return plan(TRAIN)


def test_the_train_plan_has_the_approved_mix(train_plan):
    specs = [spec for found in train_plan.values() for spec in found]
    kinds = Counter(spec.kind for spec in specs)
    assert kinds["clarify"] + kinds["unsupported"] >= 0.45 * len(specs)  # to lift their Arabizi share to 15%
    templates = Counter(spec.template for spec in specs)
    assert {f"B{n}" for n in range(1, 11)} <= set(templates)
    assert templates["T13"] == 13 and all("100" not in s.description.split("NOT")[0] for s in specs if s.template == "T13")
    assert plan(TRAIN) == train_plan  # deterministic


def test_every_planned_query_passes_the_apps_guard(train_plan):
    guard = SqlGlotGuard()
    for spec in (s for found in list(train_plan.values()) + list(plan(VALIDATION, one_each=True).values())
                 for s in found if s.kind == "sql"):
        guard.check(spec.target)


def test_since_weekday_totals_and_negations_are_planned(train_plan):
    specs = [spec for found in train_plan.values() for spec in found]
    assert sum(spec.labels.get("period", "").startswith("since_weekday") for spec in specs) >= 8
    assert sum(bool(spec.labels.get("negation")) for spec in specs) >= 8
    assert sum(bool(spec.labels.get("sarle")) for spec in specs) == 5
    periods_of_totals = Counter(spec.labels["period"] for spec in specs if spec.template == "T1")
    assert all(periods_of_totals[p] >= 2 for p in ("this_month", "last_month", "yesterday"))


def job(number, spec_id, split, today):
    return Job(plan(TRAIN)[32][0], spec_id, number, split, today, UserNames([], [], []), 0, f"prompt {spec_id}")


def test_batch3_jobs_refuse_the_test_user_and_batch2_ids():
    batch3_build.validate_jobs([job(32, "b3-32-0", "train", TODAYS[32])])
    with pytest.raises(ValueError, match="Only the batch-3 users"):  # the test user, whatever its split
        batch3_build.validate_jobs([job(31, "b3-31-0", "validation", TODAYS[40])])
    with pytest.raises(ValueError):
        batch3_build.validate_jobs([job(32, "b2-32-0", "train", TODAYS[32])])
    with pytest.raises(ValueError):
        batch3_build.validate_jobs([job(40, "b3-40-0", "train", TODAYS[40])])  # 40 is a validation user


def test_lately_gets_the_users_own_reply_line():  # approved 2026-11-15: "azdak mn emta la emta?"
    import random

    from research.dataset.batch3 import lately
    from research.dataset.checks import Version
    from research.dataset.replies import users_reply

    spec = lately(None, random.Random(0))
    reply = users_reply(Version("arabizi", "aday sarafet hal fatra?", "CLARIFY: x"), spec, load_catalogue(), random.Random(0))
    assert reply.reply == "CLARIFY: azdak mn emta la emta?"
