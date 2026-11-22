"""Batch 5: breaking the "ekher marra = the latest price" and "3adatan / m3adal = the average price" shortcuts
(shortcuts.py), decided with Christina on 2026-11-22; her review approved all 150 lines, with one spelling changed
(kerfour -> Carefour). Do not change an expected value to make a test pass. These tests read the saved jobs and her
reviewed versions."""

import json
import re

import pytest

from research.dataset import kinds, shortcuts
from research.dataset.checks import ALSO_ACCEPTED
from research.dataset.rerender import read_prompt
from research.dataset.words import WordsError

JOBS = [json.loads(line) for line in shortcuts.JOBS_FILE.read_text(encoding="utf-8").splitlines()]
REVIEWED = json.loads(shortcuts.REVIEWED.read_text(encoding="utf-8"))
LAST_KINDS, USUAL_KINDS = {"B11", "L1", "L2"}, {"B7", "N8", "B13", "L3"}


@pytest.fixture(scope="module")
def replayed(tmp_path_factory):
    out = tmp_path_factory.mktemp("shortcuts")
    report = shortcuts.replay(out_dir=out)
    rows = [json.loads(line) for split in ("train", "validation")
            for line in (out / f"shortcuts_{split}.jsonl").read_text(encoding="utf-8").splitlines()]  # fmt: skip
    return report, {read_prompt(r["messages"][0]["content"]).question: r for r in rows}


def test_her_reviewed_lines_all_become_examples(replayed):
    report, _ = replayed
    assert report == {"train": 150, "validation": 10, "near test questions, dropped": 0,
                      "kinds": {"B11": 26, "L1": 26, "L2": 30, "B7": 22, "N8": 22, "B13": 20, "L3": 14}}  # fmt: skip


# Her "yali / li jebta" lines (2026-11-22): one more version of each "what I bought the last time" job.
YALI = json.loads((shortcuts.RAW_DIR / "yali_lines.json").read_text(encoding="utf-8"))


def test_her_yali_lines_are_her_forms_and_get_their_jobs_answer(replayed):
    _, by_question = replayed
    assert YALI["s-t-25"] == "shu el ghrad li jebta ekher mara mn Pull and Bear?"
    assert YALI["s-t-27"] == "shu hiye el edewye yali jebta ekher mara mn saydaliyet Mazloum?"
    assert YALI["s-t-30"] == "shu hene el ghrad li talabton ekher marra 3a Toters?"
    targets = {j["job_id"]: j["spec"]["target"] for j in JOBS}
    for job_id, question in YALI.items():
        row = by_question[question]
        assert row["labels"]["template"] == "L2" and row["messages"][1]["content"] == targets[job_id]
        assert not re.search(r"\baam jib", question)  # habitual: not with ekher marra (her ruling)


# Her approved lines, with the answer each must have (from the saved jobs she approved).
APPROVED = {
    "aymta ekher mara rehet 3a Burger King?":
        "SELECT MAX(receipt_date) AS last_time FROM receipts WHERE vendor = 'Burger King'",
    "ekher mara rehet 3a Carefour, shu ken el total?":
        "SELECT receipt_date, vendor, currency, total, total_usd FROM receipts WHERE vendor = 'Carrefour' "
        "ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1",
    "shu hene el osas li jebton ekher mara rehet 3a Al Rifai?":
        "SELECT receipt_date, item_name, currency, line_total FROM purchases WHERE receipt_id = (SELECT receipt_id "
        "FROM receipts WHERE vendor = 'Al Rifai' ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1)",
    "el joz bl 3ade adeysh aam bi kalefne bil shaher?":
        "SELECT currency, ROUND(SUM(line_total) / 3.0, 2) AS usual_per_month, ROUND(SUM(line_total_usd) / 3.0, 2) "
        "AS usual_per_month_usd FROM purchases WHERE item_name = 'walnuts' AND receipt_date >= date_trunc('month', "
        "CURRENT_DATE) - INTERVAL '3 months' AND receipt_date < date_trunc('month', CURRENT_DATE) GROUP BY currency",
    "aday bedfa3 3adatan la Uber kel marra?":
        "SELECT currency, ROUND(AVG(total), 2) AS average_per_visit, ROUND(AVG(total_usd), 2) AS "
        "average_per_visit_usd, COUNT(*) AS visits FROM receipts WHERE vendor = 'Uber' GROUP BY currency",
    "kam marra 3am ru7 ma3 Allo Taxi 3adatan?":
        "SELECT ROUND(COUNT(DISTINCT receipt_id) / 3.0, 1) AS visits_per_month FROM receipts WHERE vendor = "
        "'Allo Taxi' AND receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '3 months' AND receipt_date < "
        "date_trunc('month', CURRENT_DATE)",
    "shu howe aktar ma7al brou7 3le 3adatan?":
        "SELECT vendor, COUNT(DISTINCT receipt_id) AS visits FROM category_spending WHERE category <> 'Utilities' "
        "AND vendor NOT IN ('Anghami') GROUP BY vendor ORDER BY visits DESC LIMIT 1",
}


@pytest.mark.parametrize("question", APPROVED)
def test_an_approved_line_gets_its_answer(replayed, question):
    _, by_question = replayed
    assert by_question[question]["messages"][1]["content"] == APPROVED[question]
    assert by_question[question]["labels"]["part"] == "shortcuts"


def test_her_spelling_carefour_is_kept_and_accepted():
    assert REVIEWED["s-t-17"][1]["question"] == "ekher mara rehet 3a Carefour, shu ken el total?"
    assert "Carefour" in ALSO_ACCEPTED["Carrefour"]


def test_every_line_uses_the_shortcut_word_of_its_kind(replayed):
    _, by_question = replayed
    last = re.compile(r"(?<!\w)(ekher|akher) ?mar+a(?!\w)|last time", re.IGNORECASE)
    usual = re.compile("|".join(re.escape(w) for w in shortcuts.USUALLY), re.IGNORECASE)
    for question, row in by_question.items():
        kind = row["labels"]["template"]
        assert (last if kind in LAST_KINDS else usual).search(question), (kind, question)


def test_no_answer_is_a_price():
    """The point of the module: with these words, the answer is never an item's latest or average price."""
    for job in JOBS:
        assert "unit_price" not in job["spec"]["target"], job["job_id"]


def test_the_last_time_at_a_shop_is_its_latest_receipt():
    for job in JOBS:
        if job["spec"]["template"] in ("L1", "L2"):
            shop = job["spec"]["labels"]["shop"].replace("'", "''")
            assert f"vendor = '{shop}' ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1" in job["spec"]["target"]


def test_the_usual_shop_leaves_out_bills_and_the_users_subscriptions():
    data = {n: d for n, _, d in kinds.users()}
    for job in JOBS:
        if job["spec"]["template"] == "L3":
            assert f"WHERE {kinds._not_bills(data[job['user']])} GROUP BY vendor" in job["spec"]["target"]


def test_every_job_has_an_answer_and_stays_in_its_users_split():
    splits = {n: s for n, s, _ in kinds.users()}
    for job in JOBS:
        assert job["rows"] > 0 and splits[job["user"]] == job["split"], job["job_id"]


def test_jobs_that_are_not_the_plan_are_refused(tmp_path):
    changed = [dict(job, spec=dict(job["spec"], target=job["spec"]["target"] + " ")) if i == 0 else job
               for i, job in enumerate(JOBS)]  # fmt: skip
    saved = tmp_path / "jobs.jsonl"
    saved.write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in changed), encoding="utf-8")
    with pytest.raises(WordsError, match="prepare again"):
        shortcuts.replay(jobs_file=saved, out_dir=tmp_path / "out")
