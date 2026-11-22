"""Batch 5 part 6: her "la hadit hala2" (until_now.py), decided with Christina on 2026-11-22: approved questions asked
again with only "la hala2 / la halla2" changed, a few as "la hadit halla2". Do not change an expected value to make a
test pass. These tests read the stored data."""

import json
import re

from research.dataset import until_now
from research.dataset.fixes import fixed_question
from research.dataset.rerender import read_prompt


def _built(tmp_path):
    report = until_now.build_files(out_dir=tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "until_now_train.jsonl").read_text(encoding="utf-8").splitlines()]
    return report, rows


def _stored(spec: str) -> dict:
    return next(c for c in until_now.candidates() if c["row"]["labels"]["spec"] == spec)


def test_20_lines_4_of_them_halla2_and_no_validation(tmp_path):
    report, rows = _built(tmp_path)
    assert report == {"train": 20, "halla2": 4, "candidates": 254}  # 252 before sho / mish / numbers (2026-11-23)
    assert (tmp_path / "until_now_validation.jsonl").read_text(encoding="utf-8") == ""
    assert all(r["labels"]["part"] == "until_now" for r in rows)


def test_only_the_phrase_changes_and_the_answer_and_user_are_the_stored_ones(tmp_path):
    _, rows = _built(tmp_path)
    for row in rows:
        question = read_prompt(row["messages"][0]["content"]).question
        # only the phrase changes, then the approved question fixes run again (their picks read the new text)
        source = next(c for c in until_now.candidates() if c["row"]["labels"]["spec"] == row["labels"]["from_spec"]
                      and question in {fixed_question(until_now.UNTIL_NOW.sub(p, c["question"]))
                                       for p in ("la hadit hala2", "la hadit halla2")})  # fmt: skip
        assert row["messages"][1] == source["row"]["messages"][1]
        assert row["labels"]["user"] == source["row"]["labels"]["user"]
        old, new = source["row"]["messages"][0]["content"], row["messages"][0]["content"]
        assert old.replace(f"Question: {source['stored']}\n", f"Question: {question}\n") == new


def test_her_sarli_line_is_in_with_its_stored_answer(tmp_path):
    _, rows = _built(tmp_path)
    found = {read_prompt(r["messages"][0]["content"]).question: r for r in rows}
    row = found["aday sarli def3a 7a2 beyd la hadit hala2?"]
    assert row["messages"][1]["content"] == _stored(row["labels"]["from_spec"])["row"]["messages"][1]["content"]
    assert "mn awal hal shaher la hadit halla2, sho seret saref?" in found  # her line, with "sho" (2026-11-23)


def test_the_sarle_questions_come_first_and_none_says_a_ruled_out_form(tmp_path):
    _, rows = _built(tmp_path)
    questions = [read_prompt(r["messages"][0]["content"]).question for r in rows]
    sarle = [bool(until_now.SARLE.search(q)) for q in questions]
    assert sarle == sorted(sarle, reverse=True) and sum(sarle) == 15
    for q in questions:
        assert fixed_question(q) == q and not re.search(r"(?<!\w)sarfet(?!\w)", q)


def test_every_candidate_has_the_question_fixes_so_a_batch2_sarfet_line_comes_fixed():
    found = until_now.candidates()
    assert all(fixed_question(c["question"]) == c["question"] for c in found)
    fixed = [c for c in found if c["stored"] != c["question"]]
    assert fixed
    assert any(re.search(r"(?<!\w)sarfet(?!\w)", c["stored"]) and "sarafet" in c["question"] for c in fixed)
