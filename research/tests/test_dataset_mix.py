"""The training mix and its coverage check (approved by the user on 2026-11-15, after the research critique showed the
batch-2 mix had dropped batch 1's Arabizi). Do not change a threshold or an expected value to make a test pass."""

import json

import pytest

from research.dataset import mix


def example(question, template="T9", kind="sql", language="arabizi", period="none", answer="SELECT 1", **labels):
    return {"messages": [{"role": "user", "content": f"rules...\nQuestion: {question}"},
                         {"role": "assistant", "content": answer}],
            "labels": {"template": template, "kind": kind, "language": language, "period": period, **labels}}


def balanced():
    """A small set that meets every threshold."""
    rows = []
    for words in ("el shaher li ata3", "sarle", "la halla2", "bel miyye", "bala ma t2elle", "men nhar el tanayn",
                  "mbere7", "3adatan"):
        rows += [example(f"adde sarafet {words} {i}") for i in range(20)]
    for template in ("T1", "T6", "T7", "T16"):
        for period in ("this_month", "last_month", "yesterday"):
            rows += [example(f"{template} {period} {i}", template=template, period=period) for i in range(5)]
    per_100 = "SELECT vendor, ROUND(AVG(x / size_amount * 100), 2) FROM purchases WHERE size_unit IN ('g', 'ml') GROUP BY vendor"
    rows += [example(f"wen arkhas {i}", template="T13", answer=per_100) for i in range(6)]
    rows += [example(f"wen arkhas la kel 100 gram {i}", template="T13", answer=per_100) for i in range(4)]
    rows += [example(f"x {i}", template="C3", kind="clarify", answer="CLARIFY: shu?") for i in range(60)]
    rows += [example(f"y {i}", template="U2", kind="unsupported", answer="UNSUPPORTED") for i in range(40)]
    rows += [example(f"How much {i}", language="english", template="C3", kind="sql") for i in range(50)]
    return rows


def test_a_balanced_set_passes():
    assert mix.failures(mix.coverage(balanced())) == []


def test_too_few_clarifying_and_unsupported_questions_fail():
    rows = [r for r in balanced() if r["labels"]["kind"] != "clarify"]
    assert any(f.startswith("CLARIFY + UNSUPPORTED") for f in mix.failures(mix.coverage(rows)))


def test_an_expression_used_fewer_than_20_times_fails():  # the batch-2 mix had none of these
    rows = [r for r in balanced() if "sarle" not in r["messages"][0]["content"]]
    assert "sarle (so far): 0 < 20" in mix.failures(mix.coverage(rows))


def test_english_questions_do_not_count_for_an_expression():
    rows = [r for r in balanced() if "sarle" not in r["messages"][0]["content"]]
    rows += [example(f"sarle {i}", language="english") for i in range(25)]
    assert "sarle (so far): 0 < 20" in mix.failures(mix.coverage(rows))


def test_a_common_question_missing_a_common_period_fails():  # batch 2 had no Arabizi totals for this month
    rows = [r for r in balanced() if not (r["labels"]["template"] == "T1" and r["labels"]["period"] == "this_month")]
    assert "T1 (total) for this_month: 0 < 5" in mix.failures(mix.coverage(rows))


def test_per_100_comparisons_that_all_say_100_fail():  # batch 2: 75 of 75 said "100"
    rows = [r for r in balanced() if not r["messages"][0]["content"].split("Question: ")[1].startswith("wen arkhas ")
            or "100" in r["messages"][0]["content"]]
    assert any(f.startswith("per-100 comparisons that do not say 100") for f in mix.failures(mix.coverage(rows)))


def test_the_mix_takes_every_batch_and_refuses_a_failing_one(tmp_path):
    data = tmp_path / "data"
    for folder in (data, data / "batch2", data / "batch3"):
        folder.mkdir(parents=True, exist_ok=True)
    rows = balanced()
    boundary = [r for r in rows if r["labels"]["kind"] in ("clarify", "unsupported")]  # batch 3 holds these
    rest = [r for r in rows if r not in boundary]
    sources = {data / "train.jsonl": rest[:100], data / "batch2" / "train.jsonl": rest[100:200],
               data / "batch2" / "extras_train.jsonl": rest[200:], data / "batch3" / "train.jsonl": boundary}
    for path, part in sources.items():
        path.write_text("".join(json.dumps(r) + "\n" for r in part), encoding="utf-8")
    for path in (data / "validation.jsonl", data / "batch2" / "validation.jsonl", data / "batch2" / "extras_validation.jsonl",
                 data / "batch3" / "validation.jsonl"):
        path.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    counts = mix.build_mix(data, data / "mix")
    assert counts["train"] == len(rows) and counts["validation"] == 4
    assert sorted((data / "mix" / "train.jsonl").read_text(encoding="utf-8").splitlines()) == sorted(
        json.dumps(r) for r in rows)
    (data / "batch3" / "train.jsonl").write_text("", encoding="utf-8")  # lose batch 3's clarify questions
    with pytest.raises(mix.CoverageError):
        mix.build_mix(data, data / "mix")
