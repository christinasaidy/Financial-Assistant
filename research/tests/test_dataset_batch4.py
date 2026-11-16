"""Batch 4 (approved by the user on 2026-11-16): the catalogue extension, the new periods and the batch-4 users.
Batches 1-3 must stay exactly as they were. Do not change an expected value to make a test pass."""

import random
from datetime import date

import pytest
from app.infrastructure.sql.sql_guard import SqlGlotGuard

from research.dataset import batch4 as b4
from research.dataset import batch4_build, periods
from research.dataset.build import Job, UserNames
from research.dataset.catalogue import (
    BATCH3_EXTENSION,
    BATCH4_EXTENSION,
    load_catalogue,
)
from research.dataset.checks import Version
from research.dataset.replies import users_reply

TODAY = date(2028, 1, 12)  # a Wednesday, the approved worked examples' today


def test_the_batch3_catalogue_is_unchanged():
    batch3 = load_catalogue(extension=BATCH3_EXTENSION)
    assert "steak" not in {item.name for item in batch3.items}
    assert "Lakkis" not in {shop.name for shop in batch3.shops}
    assert "earphones" not in batch3.item("headphones").spellings


def test_the_batch4_extension_adds_the_seeds_items_shops_and_spellings_on_top_of_batch3():
    extended = load_catalogue(extension=(BATCH3_EXTENSION, BATCH4_EXTENSION))
    names = {item.name for item in extended.items}
    assert {"steak", "haircut", "pool entry", "protein powder"} <= names
    assert "beer" in names  # batch 3's items are still there
    shops = {shop.name: shop.kind for shop in extended.shops}
    assert {"Lakkis": "restaurant", "Sushi Star": "restaurant", "Glow Paradise": "cafe"}.items() <= shops.items()
    assert "earphones" in extended.item("headphones").spellings
    assert len(extended.items) == len(load_catalogue(extension=BATCH3_EXTENSION).items) + 4


def test_last_year_is_the_previous_calendar_year():  # el sene el madye
    p = periods.last_year(TODAY)
    assert p.sql == ("receipt_date >= date_trunc('year', CURRENT_DATE) - INTERVAL '1 year' "
                     "AND receipt_date < date_trunc('year', CURRENT_DATE)")  # fmt: skip
    assert (p.start, p.end) == (date(2027, 1, 1), date(2028, 1, 1))
    assert "el sene el madye" in p.words and "last year" in p.words


def test_the_last_two_years_work_like_the_last_n_months():  # mn sentain la hala2, ekher sentain
    p = periods.last_years(TODAY, 2)
    assert p.sql == "receipt_date > CURRENT_DATE - INTERVAL '2 years' AND receipt_date <= CURRENT_DATE"
    assert (p.start, p.end) == (date(2026, 1, 13), date(2028, 1, 13))
    assert "sentain" in p.words


def test_the_last_few_weeks_are_the_last_three_weeks():  # ekher kam jem3a
    p = periods.last_few_weeks(TODAY)
    assert p.sql == "receipt_date > CURRENT_DATE - 21 AND receipt_date <= CURRENT_DATE"
    assert (p.start, p.end) == (date(2027, 12, 23), date(2028, 1, 13))
    assert "ekher kam jem3a" in p.words


def test_since_summer_starts_on_the_first_of_june_of_the_most_recent_summer():  # mn el sayfiye la hala2
    assert periods.since_summer(TODAY).sql == "receipt_date >= '2027-06-01'"
    assert (periods.since_summer(TODAY).start, periods.since_summer(TODAY).end) == (date(2027, 6, 1), date(2028, 1, 13))
    assert periods.since_summer(date(2028, 6, 20)).sql == "receipt_date >= '2028-06-01'"
    assert periods.since_summer(date(2028, 5, 31)).sql == "receipt_date >= '2027-06-01'"
    assert "sayfiye" in periods.since_summer(TODAY).words


# --- the plan (decisions approved 2026-11-16) ---


@pytest.fixture(scope="module")
def train_specs():
    return [spec for specs in b4.plan(b4.TRAIN).values() for spec in specs]


def test_the_batch4_users_are_42_to_51_with_their_set_today():
    assert b4.TRAIN == tuple(range(42, 50)) and b4.VALIDATION == (50, 51)
    assert all(b4.batch4_user(n).today == b4.TODAYS[n] for n in (42, 50))


def test_the_plan_is_deterministic_and_about_150_training_specs(train_specs):
    again = [spec for specs in b4.plan(b4.TRAIN).values() for spec in specs]
    assert [(s.template, s.target, s.description) for s in again] == [(s.template, s.target, s.description)
                                                                     for s in train_specs]  # fmt: skip
    assert 140 <= len(train_specs) <= 160
    assert sum(len(specs) for specs in b4.plan(b4.VALIDATION, one_each=True).values()) <= 30


def test_an_aday_set_asks_count_price_and_money_on_the_same_item_and_period(train_specs):
    by_set: dict[tuple, dict] = {}
    for spec in train_specs:
        if spec.labels.get("aday") in ("count", "price", "money"):
            by_set.setdefault((spec.labels["item"], spec.labels["period"]), {})[spec.labels["aday"]] = spec
    complete = [s for s in by_set.values() if len(s) == 3]
    assert len(complete) >= 8
    for found in complete:
        assert found["count"].target.startswith("SELECT SUM(quantity) AS quantity_bought FROM purchases")
        assert b4.AS_COUNT in found["count"].mentions and b4.BOUGHT in found["count"].mentions
        assert b4.MONEY not in found["count"].mentions  # "aday jebet" with no money word is a count
        assert b4.BI_ADAY in found["price"].mentions and "AVG(" in found["price"].target
        assert b4.MONEY in found["money"].mentions and "SUM(line_total)" in found["money"].target


def test_eating_at_a_restaurant_with_aday_counts_visits(train_specs):  # aday akalet bi Sushi Star
    times = [s for s in train_specs if s.labels.get("aday") == "times" and not s.labels.get("drink")]  # a cafe names
    # the drink instead (the user's review, 2026-11-16): see test_at_a_cafe_the_aday_question_names_the_drink
    assert times and all(s.target.startswith("SELECT COUNT(DISTINCT receipt_id) AS visits FROM receipts WHERE vendor")
                         and b4.EAT_DRINK in s.mentions for s in times)  # fmt: skip


def test_a_lead_in_keeps_the_question_and_adds_its_words(train_specs):
    lead = [s for s in train_specs if s.labels.get("lead_in")]
    assert {s.labels["lead_in"] for s in lead} == set(b4.LEAD_INS)
    assert len(lead) == 30
    for spec in lead:
        assert b4.LEAD_INS[spec.labels["lead_in"]][0] in spec.mentions
    became = next(s for s in lead if s.labels["lead_in"] == "became")
    assert "NOT 'so far'" in became.description  # sert / soret = I have become


def test_the_last_time_is_the_latest_date(train_specs):  # approved example 6
    last = [s for s in train_specs if s.template == "B11"]
    assert len(last) == 10
    items = [s for s in last if "item" in s.labels]
    assert items and all(s.target == f"SELECT MAX(receipt_date) AS last_time FROM purchases WHERE item_name = "
                         f"'{s.labels['item']}'" for s in items)  # fmt: skip
    shops = [s for s in last if "shop" in s.labels]
    assert shops and all(s.target == f"SELECT MAX(receipt_date) AS last_time FROM receipts WHERE vendor = "
                         f"'{s.labels['shop']}'" for s in shops)  # fmt: skip


def test_how_often_with_no_period_is_visits_per_month(train_specs):  # approved example 5
    often = [s for s in train_specs if s.template == "B13"]
    assert len(often) == 8
    for spec in often:
        assert spec.target == ("SELECT ROUND(COUNT(DISTINCT receipt_id) / 3.0, 1) AS visits_per_month FROM receipts "
                               f"WHERE vendor = '{spec.labels['shop']}' AND receipt_date >= date_trunc('month', "
                               "CURRENT_DATE) - INTERVAL '3 months' AND receipt_date < date_trunc('month', CURRENT_DATE)")


def test_a_pharmacy_lists_every_one_of_the_users_pharmacies():  # approved example 7b
    user = next(b4.batch4_user(n) for n in b4.TRAIN if any(
        b4.batch4_user(n).shop(s).kind == "pharmacy" for s in b4.batch4_user(n).shops))  # fmt: skip
    spec = b4.visit_dates(user, random.Random(0), "since_start_of_year", True)
    pharmacies = sorted(s for s in user.shops if user.shop(s).kind == "pharmacy")
    assert spec.target == ("SELECT receipt_date, vendor FROM receipts WHERE vendor IN ("
                           + ", ".join(f"'{s}'" for s in pharmacies)
                           + ") AND receipt_date >= date_trunc('year', CURRENT_DATE) ORDER BY receipt_date")
    assert b4.PHARMACY in spec.mentions


def test_the_beginning_of_the_month_is_a_clarify():  # decision (a), 2026-11-16
    spec = b4.beginning_of_month(b4.batch4_user(42), random.Random(0))
    assert spec.kind == "clarify" and spec.target is None
    assert "bi awal el shaher" in spec.mentions[0]


def test_monthly_bills_are_never_counted(train_specs):  # batch 3's rule still holds
    for spec in train_specs:
        if spec.template in ("T14", "T15", "B11"):
            assert spec.labels.get("item") not in b4.MONTHLY_BILLS


def test_monthly_bills_and_weighed_items_are_not_counted_in_units():
    catalogue = b4.load_batch4_catalogue()
    assert not b4._countable(catalogue.item("internet"))  # paid once a month
    assert not b4._countable(catalogue.item("steak"))  # weighed
    assert b4._countable(catalogue.item("protein powder"))


def test_the_plan_has_the_approved_clarify_and_reply_questions(train_specs):
    assert sum(s.kind == "reply" for s in train_specs) == 7
    assert sum(s.kind == "clarify" for s in train_specs) == 11
    assert sum(s.labels.get("period") == "bi awal el shaher" for s in train_specs) == 2
    assert sum(s.template == "C7" for s in train_specs) == 2  # a lost receipt: ask, don't refuse


def test_every_planned_query_passes_the_apps_guard(train_specs):
    guard = SqlGlotGuard()
    validation = [s for specs in b4.plan(b4.VALIDATION, one_each=True).values() for s in specs]
    for spec in (s for s in train_specs + validation if s.kind == "sql"):
        guard.check(spec.target)


def _job(number, spec_id, split, today, spec):
    return Job(spec, spec_id, number, split, today, UserNames([], [], []), 0, f"prompt {spec_id}")


def test_batch4_jobs_refuse_the_test_user_and_other_batches_ids(train_specs):
    spec = train_specs[0]
    batch4_build.validate_batch4_jobs([_job(42, "b4-42-0", "train", b4.TODAYS[42], spec)])
    with pytest.raises(ValueError, match="Only the batch-4 users 42..51"):
        batch4_build.validate_batch4_jobs([_job(31, "b4-31-0", "validation", b4.TODAYS[50], spec)])
    with pytest.raises(ValueError, match="Only the batch-4 users"):
        batch4_build.validate_batch4_jobs([_job(32, "b4-32-0", "train", b4.TODAYS[42], spec)])  # a batch-3 user
    with pytest.raises(ValueError, match="Invalid batch-4 identity"):
        batch4_build.validate_batch4_jobs([_job(42, "b3-42-0", "train", b4.TODAYS[42], spec)])
    with pytest.raises(ValueError, match="Invalid batch-4 identity"):
        batch4_build.validate_batch4_jobs([_job(50, "b4-50-0", "train", b4.TODAYS[50], spec)])  # a validation user
    with pytest.raises(ValueError, match="set today"):
        batch4_build.validate_batch4_jobs([_job(42, "b4-42-0", "train", b4.TODAYS[43], spec)])


# --- the user's reply lines and her chunk-0 review (2026-11-16) ---



def _reply(spec, question, language="arabizi", seed=0):
    return users_reply(Version(language, question, "x"), spec, b4.load_batch4_catalogue(), random.Random(seed)).reply


def test_a_lost_receipt_gets_the_users_line():
    spec = b4.lost_receipt(b4.batch4_user(42), random.Random(0))
    assert _reply(spec, "shtrit X bas ma aam le2e el fatoura") == (
        "CLARIFY: aymta w mn aya mahal jebto? aw shu fi yekun maktoub 3al fatoura?")


def test_are_you_there_gets_eh_hon():
    spec = b4.greeting(b4.batch4_user(42), random.Random(0), 0)
    assert _reply(spec, "Marhaba, kifak? enta hon?") == "REPLY: eh hon, fiye se3dak?"


def test_a_sign_off_gets_ya_hala_or_walaw_sometimes_with_bye():
    spec = b4.greeting(b4.batch4_user(42), random.Random(0), 3)
    assert spec.template == "R5"
    replies = {_reply(spec, "khalas ma ba2 baddi shi, yalla bye", seed=seed) for seed in range(40)}
    assert replies <= {"REPLY: Ya Hala", "REPLY: Walaw", "REPLY: Ya Hala, Bye!", "REPLY: Walaw, Bye!"}
    assert any("Bye!" in r for r in replies) and any("Bye!" not in r for r in replies)


def test_the_beginning_of_the_month_asks_which_period():
    spec = b4.beginning_of_month(b4.batch4_user(42), random.Random(0))
    assert _reply(spec, "aday sarafet bi awal el shaher") == "CLARIFY: azdak mn emta la emta?"


def test_iqos_is_the_device_and_sponge_has_the_users_words():
    catalogue = b4.load_batch4_catalogue()
    assert "iqos" in catalogue.item("heated tobacco device").spellings
    assert {"sfenje", "sfenjet jale", "sponge jale"} <= set(catalogue.item("sponge").spellings)


def test_at_a_cafe_the_aday_question_names_the_drink(train_specs):  # "aday shrebet ahwe bi X"
    at_cafes = [s for s in train_specs if s.labels.get("aday") == "times" and s.labels.get("drink")]
    assert at_cafes
    for spec in at_cafes:
        assert spec.target.startswith("SELECT COUNT(DISTINCT receipt_id) AS times FROM purchases WHERE item_name = "
                                      f"'{spec.labels['drink']}' AND vendor = '{spec.labels['shop']}'")
        assert b4.EAT_DRINK in spec.mentions


def test_batch4_accepts_the_users_ekher_forms_without_changing_batch3():  # chunk-2 review, 2026-11-16
    from research.dataset import batch3 as b3

    user = b4.batch4_user(42)
    assert {"ekher jemaa", "ekher jem3a", "e5er jemaa"} <= set(b4.period_named(user, "last_week", random.Random(0)).words)
    assert "e5er shaher" in b4.period_named(user, "last_month", random.Random(0)).words
    assert {"ekher sene", "e5er sene"} <= set(b4.period_named(user, "last_year", random.Random(0)).words)
    assert "ekher jemaa" not in b3.period_named(b3.batch3_user(32), "last_week", random.Random(0)).words
    lead = b4.lead_in(user, random.Random(0), "trying", "times", "last_week")  # batch 3's makers get them too
    assert lead is None or "ekher jemaa" in next(g for g in lead.mentions if "last week" in g)
