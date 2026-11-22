"""Batch 5 part 4: the new query kinds (kinds.py), in chats (kinds_chats.py), her added lines and the end of the month
(kinds_more.py). Every line was approved by Christina on 2026-11-22 (raw/batch5/part4_review.md with her edits and
additions, part4_more_review.md, part4_there_review.md); do not change an expected value to make a test pass. These
tests read the stored batch 3-4 data and the approved jobs and lines."""

import json
from datetime import date

import pytest

from app.domain.assistant.prompt import INSTRUCTIONS, Gender
from research.dataset import kinds, kinds_chats, kinds_more
from research.dataset.genders import PRICES, for_gender
from research.dataset.rerender import PART4_PERIOD_RULE, PART4_RULES, read_prompt, without_batch5_lines
from research.dataset.words import WordsError

JOBS = [json.loads(line) for line in kinds.JOBS_FILE.read_text(encoding="utf-8").splitlines()]
BY_ID = {j["job_id"]: j for j in JOBS}
REVIEWED = json.loads(kinds.REVIEWED.read_text(encoding="utf-8"))
CHAT_JOBS = {j["job_id"]: j for j in map(json.loads, kinds_chats.JOBS_FILE.read_text(encoding="utf-8").splitlines())}
MORE_JOBS = {j["job_id"]: j for j in map(json.loads, kinds_more.JOBS_FILE.read_text(encoding="utf-8").splitlines())}


def _rows(out, name):
    return {r["labels"]["spec"] + "|" + read_prompt(r["messages"][0]["content"]).question: r
            for split in ("train", "validation")
            for r in map(json.loads, (out / f"{name}_{split}.jsonl").read_text(encoding="utf-8").splitlines())}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("kinds")
    reports = (kinds.replay(out_dir=out), kinds_chats.replay(out_dir=out), kinds_more.replay(out_dir=out))
    return reports, {**_rows(out, "kinds"), **_rows(out, "kinds_chats"), **_rows(out, "kinds_more")}


# --- what she approved, all of it ---


def test_every_approved_line_becomes_one_example_and_none_is_near_a_test_question(built):
    (k, c, m), _ = built
    assert k == {"train": 247, "validation": 33, "near test questions, dropped": 0, "kinds": {
        "N1": 42, "N2": 15, "N3": 31, "N4": 27, "N5": 27, "N6": 21, "N7": 30, "N8": 24, "N10": 27, "N9": 15, "C2": 21}}
    assert c == {"train": 29, "validation": 1, "near test questions, dropped": 0,
                 "kinds": {"K4L": 6, "K4T": 6, "K4Y": 4, "K4P": 8, "C9": 6}}
    assert m == {"train": 25, "validation": 1, "near test questions, dropped": 0,
                 "kinds": {"N1": 1, "N2": 1, "N11": 1, "N3": 3, "N4": 1, "N5": 1, "N12": 15, "C4": 3}}


def test_the_saved_jobs_are_the_plan_and_no_query_answers_nothing():
    assert all(j["rows"] for j in JOBS if j["spec"]["kind"] == "sql")
    assert all(all(r for r in j["rows"]) for j in CHAT_JOBS.values())
    assert all(j["rows"] for j in MORE_JOBS.values() if j["target"])


@pytest.mark.parametrize(("job_id", "line"), [
    ("k-t-13", "top matare7 reht aalayon hal shaher, mratabin hasab kam marra"),  # her edit
    ("k-t-48", "2arenle masroufe 3al ma3jun snen hal shaher 3an ekher shaher"),  # her spelling
    ("k-t-26", "aya tlet shaghlet kalafoune aktar shi heda el shaher?"),
    ("k-t-17", "haydik el jemaa betzakar re7t 3a dekenet abou jihad, 2ele shu jebet mn honik"),  # her added line
])  # fmt: skip
def test_her_edits_and_additions_are_the_versions_used(built, job_id, line):
    _, rows = built
    assert f"{job_id}|{line}" in rows


# --- the kinds ---


def test_a_list_of_shops_has_no_limit_while_the_top_one_has():
    target = BY_ID["k-t-0"]["spec"]["target"]  # every shop this month
    assert "GROUP BY vendor, currency ORDER BY total_spent_usd DESC" in target and "LIMIT" not in target


def test_the_list_after_a_top_one_answer_is_the_same_query_without_its_limit():
    job = CHAT_JOBS["kc-list-0"]
    assert job["turns"][0][1].endswith(" LIMIT 1") and job["target"] == job["turns"][0][1].removesuffix(" LIMIT 1")


def test_honik_after_an_answer_is_that_answers_shop_over_the_same_period():
    job = CHAT_JOBS["kc-there-0"]  # "wen sarafet aktar shi el shaher el madi?" -> "w kam marra rehet la honik?"
    first = job["turns"][0][1]
    assert f"vendor = (SELECT vendor FROM ({first}) AS earlier)" in job["target"]
    assert job["target"].startswith("SELECT COUNT(DISTINCT receipt_id) AS visits FROM receipts")
    assert "date_trunc('month', CURRENT_DATE) - INTERVAL '1 month'" in job["target"].split("AS earlier)")[1]


def test_an_unknown_shop_asks_back_in_arabizi_and_uses_the_written_english_reply(built):
    _, rows = built
    arabizi = rows["k-t-76|3edele shu jebet mn 3and Bou Khalil"]
    english = rows["k-t-76|What did I buy at Bou Khalil?"]
    assert arabizi["messages"][1]["content"] == "CLARIFY: ma la2ayt fatoura bi Bou Khalil, 2asdak O&C?"
    assert english["messages"][1]["content"] == "CLARIFY: I couldn't find any receipts from Bou Khalil. Did you mean O&C?"


def test_a_version_missing_its_period_word_or_with_a_rejected_spelling_is_refused():
    job = BY_ID["k-t-0"]
    with pytest.raises(WordsError, match="does not mention"):
        kinds.examples([job], {"k-t-0": [{"language": "arabizi", "question": "wayn sarafet? samile kel el amekin"}]})
    with pytest.raises(WordsError, match="rejected spelling"):
        kinds.examples([job], {"k-t-0": [{"language": "arabizi", "question": "wayn sarafet hal shaher jem3at"}]})


# --- the end of the month (her rulings: the 21st to the end) ---


def test_the_end_of_this_month_and_of_a_named_month():
    this = kinds_more.end_of_month(date(2026, 5, 26))
    assert (this.start, this.end) == (date(2026, 5, 21), date(2026, 6, 1))
    assert "date_trunc('month', CURRENT_DATE) + INTERVAL '20 days'" in this.sql
    named = kinds_more.end_of_month(date(2027, 4, 21), 2)  # shbat
    assert named.sql == "receipt_date >= '2027-02-21' AND receipt_date < '2027-03-01'"


def test_bi_ekher_el_shaher_alone_asks_back_and_eh_gets_this_months_end(built):
    _, rows = built
    ask = rows["e-ask-33|adde sarafet bi ekher el shaher?"]
    assert ask["messages"][1]["content"] == "CLARIFY: azdak ekher 10 iyem mn hal shaher?"
    yes = rows["e-yes-33|eh"]
    parts = read_prompt(yes["messages"][0]["content"])
    assert [(e.question, e.reply) for e in parts.history] == [
        ("adde sarafet bi ekher el shaher?", "CLARIFY: azdak ekher 10 iyem mn hal shaher?")]
    assert "INTERVAL '20 days'" in yes["messages"][1]["content"]
    assert for_gender(ask["messages"][1]["content"], Gender.WOMAN) == "CLARIFY: azdik ekher 10 iyem mn hal shaher?"


def test_the_end_of_that_month_follows_a_question_about_the_named_month(built):
    _, rows = built
    example = next(r for k, r in rows.items() if k.startswith("e-that-39|"))
    parts = read_prompt(example["messages"][0]["content"])
    assert parts.history[0].question == "aday sarafet bi shbat?"
    assert "'2027-02-21'" in example["messages"][1]["content"]


# --- her lines that needed receipts (2026-11-22: never assume a user has none) ---


def test_only_the_users_of_her_lines_get_extra_receipts_and_only_in_part_4():
    users = {n: d for n, _, d in kinds.users()}
    nike = kinds_more.user_with_extra(45, users[45])
    assert "Nike" in nike.shops and "Nike" not in users[45].user.shops
    assert kinds_more.user_with_extra(33, users[33]) is users[33].user
    assert "Nike" in MORE_JOBS["h-nike"]["names"]["vendors"]


# --- the questions back about prices in general, and the prompt rules ---


def test_a_price_question_back_takes_the_users_gender():
    man = PRICES["thing"].man.format(x="beirut", y="khodra")
    assert for_gender(man, Gender.WOMAN) == (
        "CLARIFY: ma fiye 2elik 3an kel beirut, bas fiye shuf wen jebta arkhas mn fwatirik. 3an aya khodra badik ta3rfe?")


def test_the_part_4_rules_are_in_the_prompt_and_older_prompts_still_rebuild():
    assert PART4_RULES in INSTRUCTIONS and PART4_PERIOD_RULE in INSTRUCTIONS
    without = without_batch5_lines(INSTRUCTIONS)
    assert "aghla fatoura" not in without and "bi ekher heda el shaher" not in without
