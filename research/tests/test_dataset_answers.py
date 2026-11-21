"""Batch 5 part 2: the written answer sentences (answers_build.py). Every answer was written from its query's real
result and approved by Christina on 2026-11-20 (the 40 pilot answers, then a 200-answer review of the 1,514); do not
change an expected value to make a test pass. These tests read the approved jobs and answers (raw/batch5/)."""

import json

import pytest

from research.dataset import answers_build as ab

JOBS = ab.load_jobs()
WRITTEN, FAILING = ab.check_authored(JOBS)


# --- the approved answers ---


def test_every_job_has_one_approved_answer_and_every_answer_passes():
    assert len(JOBS) == 1504 and set(WRITTEN) == set(JOBS)  # 1,514 - 10 on questions the batch-1 cleanup dropped
    assert FAILING == {}


def test_the_pilot_jobs_are_kept_as_reviewed_beside_the_new_ones():
    assert sum(job_id.startswith("pilot-") for job_id in JOBS) == 40
    assert len(ab._read_jobs(ab.JOBS_FILE)) == 1464  # 2026-11-21: 10 left with their questions


def test_every_approved_answer_becomes_one_example_with_its_jobs_prompt(tmp_path):
    report = ab.replay(out_dir=tmp_path)
    assert report == {"kept": {"train": 1311, "validation": 193}, "left_out": {}}  # 2026-11-21 cleanup
    rows = [json.loads(line) for line in (tmp_path / "answers_train.jsonl").read_text(encoding="utf-8").splitlines()]
    example = next(r for r in rows if r["labels"]["job_id"] == "a-t-0018")
    assert example["messages"] == [{"role": "user", "content": JOBS["a-t-0018"]["prompt"]},
                                   {"role": "assistant", "content": WRITTEN["a-t-0018"]}]  # fmt: skip
    assert (example["labels"]["kind"], example["labels"]["template"], example["labels"]["result"]) == (
        "answer", "ANSWER", "compare")
    assert {r["labels"]["split"] for r in rows} == {"train"}


# --- the checks, on approved answers changed one way ---


def _with(job_id: str, text: str) -> list[str]:
    return ab.problems(JOBS[job_id], text)


def test_a_number_not_in_the_result_is_refused():
    assert _with("a-t-0018", WRITTEN["a-t-0018"]) == []
    assert _with("a-t-0018", WRITTEN["a-t-0018"].replace("$8.90", "$8.95"))


def test_an_answer_on_several_lines_or_too_long_is_refused():
    text = WRITTEN["a-t-0018"]
    assert "empty, several lines or longer than 400 characters" in _with("a-t-0018", text.replace(", w ", "\nw "))
    assert "empty, several lines or longer than 400 characters" in _with("a-t-0018", text + " w" * 200)
    assert "empty, several lines or longer than 400 characters" in _with("a-t-0018", "  ")


def test_the_cheaper_shop_must_be_named_first_whatever_the_rows_order():
    """33 answers named the dearer shop first when the code assumed sorted rows (fixed 2026-11-20)."""
    job = JOBS["a-t-0018"]  # Netflix $10.40, Shahid $8.90
    assert ab.winner("compare", job["columns"], job["rows"]) == "Shahid"
    assert ab.winner("compare", job["columns"], job["rows"][::-1]) == "Shahid"
    swapped = "Netflix was dearer: $10.40, w Shahid $8.90, bel 30 yom el ekhrin."
    assert _with("a-t-0018", swapped) == ["the first name given must be Shahid"]


def test_no_shop_must_come_first_across_two_currencies_or_a_tie():
    job = JOBS["a-t-0215"]  # 45,000 LBP at Abou Jihad, $0.49 at Spinneys
    assert ab.winner("compare", job["columns"], job["rows"]) is None
    assert _with("a-t-0215", WRITTEN["a-t-0215"]) == []
    tie = [["Netflix", "USD", 1, "8.90"], ["Shahid", "USD", 1, "8.90"]]
    assert ab.winner("compare", JOBS["a-t-0018"]["columns"], tie) is None


def test_a_category_is_ranked_by_all_its_currencies_in_usd_and_tax_is_never_first():
    job = JOBS["pilot-a-t-0524"]
    assert ab.winner("categories", job["columns"], job["rows"]) == "Dining"  # $62.85 + 2,410,000 LBP
    groceries, dining_usd, groceries_usd = job["rows"][1], ["Dining", "USD", "50.00", "50.00"], job["rows"][3]
    assert ab.winner("categories", job["columns"], [groceries, dining_usd, groceries_usd]) == "Groceries"  # $61.96
    tax = ["Tax, discounts & rounding", "USD", "99.00", "99.00"]
    assert ab.winner("categories", job["columns"], [dining_usd, tax]) == "Dining"


@pytest.mark.parametrize("word", ["kallefetne", "kallefoune", "3elka", "eshhor", "jem3at"])
def test_a_rejected_spelling_is_refused(word):
    assert f"rejected spelling ['{word}']" in _with("a-t-1350", f"{WRITTEN['a-t-1350']} {word}")


def test_a_fraction_of_a_visit_is_refused_but_a_price_before_marra_is_not():
    assert _with("a-t-1350", "0.7 marra bel shaher, 3and Burger House.")[-1].startswith("a fraction of a visit")
    assert _with("a-v-1160", WRITTEN["a-v-1160"]) == []  # "$4.85 marra wa7de bas"


def test_how_often_is_answered_over_the_last_3_months():
    assert "bel 3 eshor el ekhrin" in WRITTEN["a-t-1350"]


@pytest.mark.parametrize(("job_id", "word"), [
    ("pilot-a-t-0647", "sarafet"),  # a woman: "ma jebte", never the man's forms
    ("pilot-a-t-0959", "sarafte"),  # a man
    ("pilot-a-t-0241", "sarafet"), ("pilot-a-t-0241", "sarafte"),  # not given: neither
])  # fmt: skip
def test_an_arabizi_answer_uses_only_the_users_gender(job_id, word):
    assert _with(job_id, WRITTEN[job_id]) == []
    gender = JOBS[job_id]["gender"]
    assert _with(job_id, f"{WRITTEN[job_id]} {word}") == [f"{gender}: words of the other gender ['{word}']"]


def test_an_english_answer_is_not_checked_for_arabizi_gender_words():
    job = JOBS["pilot-a-t-0524"]
    assert (job["language"], job["gender"]) == ("english", "woman")
    assert _with("pilot-a-t-0524", WRITTEN["pilot-a-t-0524"] + " sarafet") == []  # a man's form, in English: not checked


def test_an_answer_for_no_such_job_or_failing_a_check_is_left_out_and_reported(tmp_path):
    authored = tmp_path / "authored"
    authored.mkdir()
    (authored / "chunk.json").write_text(json.dumps({
        "a-t-0018": WRITTEN["a-t-0018"], "a-t-1350": "0.7 marra bel shaher", "a-x-9999": "hi"}), encoding="utf-8")
    report = ab.replay(authored_dir=authored, out_dir=tmp_path / "out")
    assert report["kept"] == {"train": 1, "validation": 0}
    assert set(report["left_out"]) == {"a-t-1350", "a-x-9999"} and report["left_out"]["a-x-9999"] == ["no such job"]
