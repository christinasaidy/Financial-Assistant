"""Batch 5: "not what I meant" with what they meant (corrections.py). The lines were approved by Christina on
2026-11-22 (raw/batch5/corrections_review.md, "all good", then "X msh Y" and "ma azde hek" added); do not change an
expected value to make a test pass. These tests read the stored batch 3-4 data and the approved jobs and lines."""

import json

import pytest

from research.dataset import corrections as c
from research.dataset.rerender import read_prompt

JOBS = [json.loads(line) for line in c.JOBS_FILE.read_text(encoding="utf-8").splitlines()]
BY_ID = {j["job_id"]: j for j in JOBS}
REVIEWED = json.loads(c.REVIEWED.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("corrections")
    report = c.replay(out_dir=out)
    rows = [json.loads(line) for split in ("train", "validation")
            for line in (out / f"corrections_{split}.jsonl").read_text(encoding="utf-8").splitlines()]  # fmt: skip
    return report, {r["labels"]["spec"]: r for r in rows}


def test_the_saved_jobs_are_the_plan_and_no_answer_is_empty():
    assert [(j["job_id"], j["target"]) for j in JOBS] == [(j["job_id"], j["target"]) for j in c.plan()]
    assert len(JOBS) == 22 and all(j["rows"] > 0 for j in JOBS)


def test_every_approved_line_becomes_one_example(built):
    report, _ = built
    assert report == {"train": 31, "validation": 2, "near test questions, dropped": 0, "kinds": {"K1": 22, "C6": 11}}


def test_a_correction_answers_with_the_corrected_sql_after_the_first_question_and_its_answer(built):
    _, rows = built
    example = rows["k1-t-0"]  # "aday seret defe3 3al mozzarella men nisen la lyom" -> "... 3am ehki aan el jebne"
    parts = read_prompt(example["messages"][0]["content"])
    assert parts.question == "la2 msh hek azdi, 3am ehki aan el jebne"
    assert [e.question for e in parts.history] == ["aday seret defe3 3al mozzarella men nisen la lyom"]
    first_sql, gold = parts.history[0].reply, example["messages"][1]["content"]
    assert "item_name = 'mozzarella'" in first_sql and gold == first_sql.replace("'mozzarella'", "'cheese'")
    assert example["labels"]["history"] == 1 and example["labels"]["correction"] == "item"


def test_a_measure_correction_keeps_the_item_and_period():
    job = BY_ID["k1-t-8"]  # khebez, last month: how much -> "baddi kam marra jebt msh adde"
    assert job["target"].startswith("SELECT COUNT(DISTINCT receipt_id) AS times FROM purchases WHERE item_name = 'bread'")
    assert "date_trunc('month', CURRENT_DATE) - INTERVAL '1 month'" in job["target"]


def test_a_category_correction_keeps_the_period():
    job = BY_ID["k1-t-10"]  # "aday sarafet bi ekher kam jem3a?" -> "la2 msh hek azdi, bas el groceries"
    assert "FROM category_spending WHERE category = 'Groceries'" in job["target"]


@pytest.mark.parametrize(("job_id", "line"), [("k1-t-18", "la2, azdi el steak msh el kafta"),
                                              ("k1-t-19", "ma azde hek, azde ekher shaher")])
def test_her_added_lines_are_there(built, job_id, line):
    _, rows = built
    assert read_prompt(rows[job_id]["messages"][0]["content"]).question == line


def test_a_vague_line_alone_asks_back_with_nothing_earlier(built):
    _, rows = built
    example = rows["k2-1"]
    parts = read_prompt(example["messages"][0]["content"])
    assert parts.question == "ma fhemet, azdi el masrouf msh el fwatir" and parts.history == ()
    assert example["messages"][1]["content"] == "CLARIFY: shu baddak ta3ref bel zabt?"  # the mix gives the user's form
    assert example["labels"]["template"] == "C6" and example["labels"]["kind"] == "clarify"


def test_a_line_missing_or_unplanned_refuses_everything(tmp_path):
    missing = {**REVIEWED, "K1": REVIEWED["K1"][:-1]}
    (tmp_path / "r.json").write_text(json.dumps(missing), encoding="utf-8")
    with pytest.raises(c.CorrectionError, match="not the planned chats"):
        c.replay(reviewed_file=tmp_path / "r.json", out_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_a_rejected_spelling_is_refused(tmp_path):
    bad = json.loads(json.dumps(REVIEWED))
    bad["K1"][0]["question"] = "la2 msh hek azdi, jem3at"
    (tmp_path / "r.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(Exception, match="rejected spelling"):
        c.replay(reviewed_file=tmp_path / "r.json", out_dir=tmp_path / "out")


def test_a_line_near_a_held_out_question_is_dropped(tmp_path):
    report = c.replay(out_dir=tmp_path, held_out=("la2 msh hek azdi, 3am ehki aan el jebne",))
    assert report["near test questions, dropped"] == 1 and report["train"] == 30
