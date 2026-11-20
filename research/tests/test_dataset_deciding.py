"""Batch 5 part 3: deciding. The groups, the rent rule and every line were approved by Christina on 2026-11-20
(raw/batch5/deciding_review.md -> raw/batch5/deciding/reviewed.json); do not change an expected value to make a test
pass. These tests read the stored batch 3-4 data, the approved lines and the saved rent jobs."""

import json
from collections import Counter
from dataclasses import replace

import pytest

from research.dataset import deciding as dc
from research.dataset import mix, words
from research.dataset.checks import Version, problems
from research.dataset.genders import DECIDING
from research.dataset.rerender import read_prompt
from research.dataset.users import gender_of

REVIEWED = json.loads(dc.REVIEWED.read_text(encoding="utf-8"))
JOBS = [json.loads(line) for line in dc.JOBS_FILE.read_text(encoding="utf-8").splitlines()]
RENT_NUMBERS = {number for _, number, _ in dc.RENT_USERS}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("deciding")
    report = dc.replay(out_dir=out)
    rows = [json.loads(line) for split in ("train", "validation")
            for line in (out / f"deciding_{split}.jsonl").read_text(encoding="utf-8").splitlines()]  # fmt: skip
    return report, rows


@pytest.fixture(scope="module")
def stored():
    return words.stored(), words.stored_specs()


def _question(row):
    return read_prompt(row["messages"][0]["content"]).question


def test_every_approved_line_becomes_one_example(built):  # counts updated 2026-11-20: her 4 new A lines
    report, _ = built
    assert (report["train"], report["validation"], report["near test questions, dropped"]) == (219, 40, 3)
    assert report["groups"] == {"A": 76, "B1": 39, "C3": 15, "D": 29, "C2": 25, "B2": 10, "E": 50, "C1": 15}
    assert report["kinds"] == {"unsupported": 130, "clarify": 54, "sql": 75}
    assert "batch5/deciding_{split}.jsonl" in mix.SOURCES


def test_another_persons_spending_income_and_budgets_are_refused(built):
    _, rows = built
    refused = [r for r in rows if r["labels"]["deciding"] in ("A", "B1", "C3")]
    assert refused and all(r["messages"][1]["content"] == "UNSUPPORTED" for r in refused)
    assert {r["labels"]["template"] for r in refused if r["labels"]["deciding"] == "C3"} == {"U1"}  # budgets


def test_a_name_that_is_not_the_user_is_refused_and_a_mention_of_one_is_not(built):
    """Her rule: "how much Ali spent" is not the user's; "Ali 2ale eno ma sajalet shi, kam fatoura ..." is."""
    _, rows = built
    by_question = {_question(r): r for r in rows}
    assert by_question["Ali aday saraf 3al benzin?"]["messages"][1]["content"] == "UNSUPPORTED"
    assert by_question["Ali 2ale eno ma sajalet shi, kam fatoura hatayt mbere7?"]["messages"][1]["content"].startswith(
        "SELECT")


def test_rent_is_answered_for_a_user_with_a_rent_category_and_asked_back_for_one_without(built):
    _, rows = built
    answered = {_question(r) for r in rows if r["labels"]["deciding"] == "C1"}
    asked = {_question(r): r for r in rows if r["labels"]["deciding"] == "C2"}
    assert answered <= set(asked)  # the same questions, both ways
    rent = {f.man for f in DECIDING["rent"]} | {dc.ENGLISH["rent"]}
    assert all(r["messages"][1]["content"] in rent for r in asked.values())
    assert not {r["labels"]["user"] for r in asked.values()} & RENT_NUMBERS  # "has rent" and "has none" kept apart
    for r in rows:
        if r["labels"]["deciding"] == "C1":
            assert "Rent" in r["messages"][1]["content"] and r["labels"]["user"] in RENT_NUMBERS


def test_the_rent_users_have_a_rent_category_and_a_rent_each_month():
    user = dc.rent_user(dc.batch3, 37, dc.Decimal("450.00"))
    rent = [r for r in user.receipts if r.category == dc.RENT]
    assert "Rent" in user.private_categories and len(rent) == 14
    assert {r.day.day for r in rent} == {1} and {r.total for r in rent} == {dc.Decimal("450.00")}
    assert max(r.day for r in rent) == user.today.replace(day=1)
    assert all("Rent" in job["names"]["categories"] and job["rows"] > 0 for job in JOBS)  # every query had a result


def test_the_saved_rent_jobs_are_the_plan_and_a_changed_question_refuses(tmp_path):
    planned = dc.plan_rent(REVIEWED)
    assert [(j["job_id"], j["question"], j["target"]) for j in planned] == [
        (j["job_id"], j["question"], j["target"]) for j in JOBS]
    changed = json.loads(json.dumps(REVIEWED))
    changed["C1"][0]["question"] = "adesh dafa3et ajar hal shaher?"
    (tmp_path / "reviewed.json").write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(dc.DecidingError, match="prepare again"):
        dc.replay(reviewed_file=tmp_path / "reviewed.json", out_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_transfers_never_entered_are_asked_back(built):
    _, rows = built
    transfer = {f.man for f in DECIDING["transfer"]} | {dc.ENGLISH["transfer"]}
    asked = [r for r in rows if r["labels"]["deciding"] == "D"]
    assert asked and all(r["messages"][1]["content"] in transfer for r in asked)


def test_a_version_keeps_its_stored_questions_sql_and_user(built, stored):
    _, rows = built
    rows_by_spec = stored[0]
    versions = [r for r in rows if r["labels"]["deciding"] in ("B2", "E")]
    assert len(versions) == 60
    for r in versions:
        original = rows_by_spec[r["labels"]["spec"]]
        assert r["messages"][1]["content"] == original["messages"][1]["content"]
        assert r["labels"]["user"] == original["labels"]["user"]


def test_a_spouse_line_must_go_on_a_user_of_the_speakers_gender(stored):
    line = next(x for x in REVIEWED["E"] if x["question"].startswith("marti 2aletle eno sarafet ktir"))
    assert gender_of(stored[0][line["spec"]]["labels"]["user"]).value == "man"
    wrong = {**REVIEWED, "B2": [], "E": [dict(line, gender="woman")]}
    with pytest.raises(dc.DecidingError, match="said by a woman"):
        dc.version_examples(wrong, *stored)


def test_a_new_lead_in_replaces_batch4s_lead_in_word_but_the_period_is_still_needed(stored):
    spec = stored[1]["b4-44-4"]  # "badi a3ref ... el shaher li mara2"
    plain = dc.without_lead_in(spec)
    assert len(plain.mentions) == len(spec.mentions) - 1
    question = "3a shu tar ma3ashe el shaher li mara2?"
    assert problems(Version("arabizi", question), spec, words._catalogue("b4-44-4")) != []
    assert problems(Version("arabizi", question), plain, words._catalogue("b4-44-4")) == []
    assert problems(Version("arabizi", "3a shu tar ma3ashe?"), plain, words._catalogue("b4-44-4")) != []
    assert dc.without_lead_in(replace(spec, labels={})) == replace(spec, labels={})


def test_her_spellings_are_accepted(stored):  # 2026-11-20: "ekher l shaher", "sar masroufe"
    specs = stored[1]
    assert problems(Version("arabizi", "ma3ashe ra7 kelo ekher l shaher, wayn sarafto?"),
                    dc.without_lead_in(specs["b4-45-3"]), words._catalogue("b4-45-3")) == []  # fmt: skip
    assert problems(Version("arabizi", "kel el za3tar li jebto, adde sar masroufe 3leh?"), specs["b3-32-10"],
                    words._catalogue("b3-32-10")) == []  # fmt: skip


def test_kam_never_asks_for_money_in_the_new_lines():
    """Her rule (2026-11-20): kam only counts (kam marra, kam fatoura, kam ta7wile); money is aday / adesh."""
    import re
    money = re.compile(r"\bkam\b(?!\s+(marra|mara|marat|fatoura|fetoura|fwatir|ta7wile|transfer|receipt))", re.I)
    lines = [x["question"] for group in ("A", "B1", "C1", "C2", "C3", "D") for x in REVIEWED[group]]
    assert [q for q in lines if money.search(q)] == []


def test_a_line_near_a_test_question_is_dropped(tmp_path):
    report = dc.replay(out_dir=tmp_path, held_out=("jarna adeysh byesrof bel shaher?",))
    assert report["near test questions, dropped"] >= 1
    assert sum(report["groups"].values()) == 262 - report["near test questions, dropped"]


def test_a_version_missing_its_stored_questions_words_refuses(stored):
    line = next(x for x in REVIEWED["B2"] if x["spec"] == "b4-44-4")
    wrong = {**REVIEWED, "B2": [dict(line, question="3a shu tar ma3ashe?")], "E": []}  # no period
    with pytest.raises(dc.DecidingError, match="does not mention"):
        dc.version_examples(wrong, *stored)
