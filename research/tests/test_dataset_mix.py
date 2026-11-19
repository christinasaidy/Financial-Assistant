"""The training mix and its coverage check (approved by the user on 2026-11-15, after the research critique showed the
batch-2 mix had dropped batch 1's Arabizi). Do not change a threshold or an expected value to make a test pass."""

import json
from datetime import date

import pytest

from app.domain.assistant.prompt import Gender, UserNames, build_prompt
from research.dataset import mix
from research.dataset.genders import PERIOD_QUESTIONS, UnformedReply
from research.dataset.rerender import rerender, without_batch5_lines


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


_specs = iter(range(10**6))


def stored(row, user=1):
    """The row as batches 1-4 stored it, with a real prompt (no gender line, no batch-5 rule), its user and its own
    spec: what build_mix rebuilds since batch 5."""
    question = row["messages"][0]["content"].rsplit("Question: ", 1)[-1]
    prompt = without_batch5_lines(build_prompt(question, UserNames(["x"], ["y"], ["Groceries"]), date(2026, 11, 3),
                                               gender=Gender.MAN))  # fmt: skip
    return {"messages": [{"role": "user", "content": prompt}, row["messages"][1]],
            "labels": {"spec": f"b4-{user}-{next(_specs)}", **row["labels"], "user": user}}


def test_the_mix_takes_every_batch_and_refuses_a_failing_one(tmp_path):
    """Changed with batch 5 (2026-11-18): the mix holds every line rebuilt with today's prompt (it used to hold the
    lines exactly as stored)."""
    data = tmp_path / "data"
    for folder in (data, data / "batch2", data / "batch3", data / "batch4", data / "batch5"):  # batch 5: 2026-11-19
        folder.mkdir(parents=True, exist_ok=True)
    for split in ("train", "validation"):  # batch 5 empty here: these tests are about batches 1-4
        (data / "batch5" / f"{split}.jsonl").write_text("", encoding="utf-8")
    rows = [stored(r) for r in balanced() + batch4_balanced()]
    boundary = [r for r in rows if r["labels"]["kind"] in ("clarify", "unsupported")]  # batch 3 holds these
    rest = [r for r in rows if r not in boundary]
    sources = {data / "train.jsonl": rest[:100], data / "batch2" / "train.jsonl": rest[100:200],
               data / "batch2" / "extras_train.jsonl": rest[200:300], data / "batch3" / "train.jsonl": boundary,
               data / "batch4" / "train.jsonl": rest[300:]}
    for path, part in sources.items():
        path.write_text("".join(json.dumps(r) + "\n" for r in part), encoding="utf-8")
    for path in (data / "validation.jsonl", data / "batch2" / "validation.jsonl", data / "batch2" / "extras_validation.jsonl",
                 data / "batch3" / "validation.jsonl", data / "batch4" / "validation.jsonl"):
        path.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    counts = mix.build_mix(data, data / "mix")
    assert counts["train"] == len(rows) and counts["validation"] == 5
    assert sorted((data / "mix" / "train.jsonl").read_text(encoding="utf-8").splitlines()) == sorted(
        json.dumps(rerender(r), ensure_ascii=False) for r in rows)
    (data / "batch3" / "train.jsonl").write_text("", encoding="utf-8")  # lose batch 3's clarify questions
    with pytest.raises(mix.CoverageError):
        mix.build_mix(data, data / "mix")


# --- batch 4's minimums (approved 2026-11-16): the user's spellings and the new kinds ---


def batch4_balanced():
    rows = []
    for words, n in (("jebet", 40), ("shtrit", 40), ("aal", 60), ("aa", 40), ("shefle", 30)):
        rows += [example(f"kam mara {words} x {i}") for i in range(n)]
    rows += [example(f"aday jebet x {i}", template="T15", answer="SELECT SUM(quantity)") for i in range(30)]
    rows += [example(f"bi aday jebet el x {i}", template="T12") for i in range(15)]
    rows += [example(f"aymta ekher mara {i}", template="B11", answer="SELECT MAX(receipt_date)") for i in range(30)]
    return rows


def test_batch4_minimums_pass_when_met():
    assert mix.batch4_failures(mix.coverage(batch4_balanced())) == []


@pytest.mark.parametrize(("dropped", "message"), [
    ("jebet", "jebet"), ("shtrit", "shtrit"), ("aal", "aal"), ("shefle", "shefle")])  # fmt: skip
def test_a_missing_spelling_fails(dropped, message):
    rows = [r for r in batch4_balanced() if f" {dropped} " not in mix._question(r)]
    assert any(message in f for f in mix.batch4_failures(mix.coverage(rows)))


def test_aday_as_a_count_needs_a_count_answer():  # "aday jebet X" answered with money does not count
    rows = [r for r in batch4_balanced() if r["labels"]["template"] != "T15"]
    rows += [example(f"aday jebet x {i}", template="T9", answer="SELECT SUM(line_total)") for i in range(30)]
    assert any("aday as a count" in f for f in mix.batch4_failures(mix.coverage(rows)))


def test_english_does_not_count_for_batch4_minimums():
    rows = [dict(r, labels={**r["labels"], "language": "english"}) for r in batch4_balanced()]
    assert len(mix.batch4_failures(mix.coverage(rows))) == 8


def test_each_batch4_minimum_is_exactly_its_approved_number():
    for name, (_, least, _, _) in mix.BATCH4_MINIMUMS.items():
        report = mix.coverage(batch4_balanced())
        report["batch4"][name] = least
        assert name not in " ".join(mix.batch4_failures(report)), name
        report["batch4"][name] = least - 1
        assert any(f.startswith(f"{name}:") for f in mix.batch4_failures(report)), name
    assert {n: m[1] for n, m in mix.BATCH4_MINIMUMS.items()} == {
        "jebet": 40, "shtrit": 40, "aal": 60, "aa": 40, "shefle": 30, "aday as a count": 30,
        "bi aday (the price)": 15, "the last time": 30}  # fmt: skip


def test_a_count_needs_both_the_count_template_and_a_count_answer():
    rows = [r for r in batch4_balanced() if r["labels"]["template"] not in ("T15", "B11")]
    wrong_answer = [example(f"aday jebet x {i}", template="T15", answer="SELECT SUM(line_total)") for i in range(30)]
    wrong_template = [example(f"aymta ekher mara {i}", template="T8", answer="SELECT MAX(receipt_date)")
                      for i in range(30)]  # fmt: skip
    found = mix.batch4_failures(mix.coverage(rows + wrong_answer + wrong_template))
    assert any("aday as a count" in f for f in found) and any("the last time" in f for f in found)


def test_the_mix_refuses_when_batch4_misses_a_minimum(tmp_path):
    data = tmp_path / "data"
    for folder in (data, data / "batch2", data / "batch3", data / "batch4", data / "batch5"):
        folder.mkdir(parents=True, exist_ok=True)
    for split in ("train", "validation"):
        (data / "batch5" / f"{split}.jsonl").write_text("", encoding="utf-8")
    rows = [stored(r) for r in balanced()]
    for name in ("train.jsonl", "batch2/train.jsonl", "batch2/extras_train.jsonl", "batch4/train.jsonl",
                 "validation.jsonl", "batch2/validation.jsonl", "batch2/extras_validation.jsonl",
                 "batch3/validation.jsonl", "batch4/validation.jsonl"):
        (data / name).write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    (data / "batch3" / "train.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    with pytest.raises(mix.CoverageError, match="jebet"):  # batch 3's thresholds pass, batch 4's do not
        mix.build_mix(data, data / "mix")


# --- batch 5 (2026-11-18): every line rebuilt with today's prompt ---


def write_batches(data, train_rows, validation_row):
    for folder in (data, data / "batch2", data / "batch3", data / "batch4", data / "batch5"):
        folder.mkdir(parents=True, exist_ok=True)
    for split in ("train", "validation"):
        (data / "batch5" / f"{split}.jsonl").write_text("", encoding="utf-8")
    for source in mix.SOURCES:
        (data / source.format(split="train")).write_text("", encoding="utf-8")
        (data / source.format(split="validation")).write_text(json.dumps(validation_row) + "\n", encoding="utf-8")
    (data / "batch3" / "train.jsonl").write_text("".join(json.dumps(r) + "\n" for r in train_rows), encoding="utf-8")


def test_the_mix_states_each_users_gender_and_gives_a_woman_her_form(tmp_path):
    data = tmp_path / "data"
    rows = [stored(r, user=3) for r in balanced() + batch4_balanced()]  # user 3 is a woman
    rows.append(stored(example("aday sarafet hal fatra?", template="C4", kind="clarify",
                               answer="CLARIFY: azdak mn emta la emta?"), user=3))  # fmt: skip
    write_batches(data, rows, rows[0])
    mix.build_mix(data, data / "mix")
    built = [json.loads(line) for line in (data / "mix" / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all("\nThe user is a woman.\n" in r["messages"][0]["content"] for r in built)
    assert all(r["labels"]["gender"] == "woman" for r in built)
    answers = [r["messages"][1]["content"] for r in built]
    # Changed 2026-11-19: the period question rotates among her forms; a woman gets a woman's form, never a man's.
    assert any(a in {f.woman for f in PERIOD_QUESTIONS} for a in answers)
    assert not any(a in {f.man for f in PERIOD_QUESTIONS} for a in answers)


def test_the_mix_refuses_a_masculine_reply_with_no_approved_forms_and_writes_nothing(tmp_path):
    data = tmp_path / "data"
    rows = [stored(r) for r in balanced() + batch4_balanced()]
    rows.append(stored(example("shu?", template="C6", kind="clarify", answer="CLARIFY: shu baddak?")))
    write_batches(data, rows, rows[0])
    with pytest.raises(UnformedReply):
        mix.build_mix(data, data / "mix")
    assert not (data / "mix").exists()


def test_the_mix_puts_earlier_exchanges_in_front_so_that_70_percent_of_chats_ignore_them(tmp_path):
    data = tmp_path / "data"
    rows = [stored(r, user=46) for r in balanced() + batch4_balanced()]
    for n, r in enumerate(rows):
        r["labels"]["spec"] = f"b4-46-{n // 3}"  # three versions per question, as the batches write them
    follow_ups = [stored(example(f"w ekher shaher {n}?", kind="follow_up", language="english"), user=46)
                  for n in range(20)]  # fmt: skip
    for n, r in enumerate(follow_ups):
        r["labels"]["spec"] = f"b4-46-f{n}"
    write_batches(data, rows + follow_ups, rows[0])
    mix.build_mix(data, data / "mix")
    built = [json.loads(line) for line in (data / "mix" / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    independent = [r for r in built if r["labels"].get("history_role") == "independent"]
    assert len(independent) == 47  # 20 follow-ups x 0.7 / 0.3
    assert all("Earlier in this chat:" in r["messages"][0]["content"] for r in independent)


# --- batch 5 part 1's minimums (decision 11, approved 2026-11-17, plus follow-up-looking topic changes) ---


def test_each_part1_minimum_is_exactly_its_approved_number():
    assert mix.PART1_MINIMUMS == {"topic changes": 300, "after a CLARIFY, UNSUPPORTED or REPLY": 150,
                                  "3 or more earlier exchanges": 150, "follow-ups after older turns": 150,
                                  "answered CLARIFYs": 100, "thanks or ma fhemet with history": 60,
                                  "follow-up-looking topic changes": 60}  # fmt: skip
    for name, least in mix.PART1_MINIMUMS.items():
        report = {n: 10**6 for n in mix.PART1_MINIMUMS}
        report[name] = least
        assert mix.part1_failures(report) == []
        report[name] = least - 1
        assert mix.part1_failures(report) == [f"{name}: {least - 1} < {least}"]


def test_the_part1_counts_read_the_chats():
    from app.domain.assistant.prompt import Exchange

    def chat(history, template="P1A", role="independent", kind="sql", **labels):
        prompt = build_prompt("q?", UserNames(["x"], ["y"], ["Groceries"]), date(2026, 11, 3), history,
                              gender=Gender.MAN)  # fmt: skip
        return {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": "SELECT 1"}],
                "labels": {"template": template, "kind": kind, "history": len(history), "history_role": role, **labels}}

    rows = [chat((Exchange("a?", "SELECT 1"),)),
            chat((Exchange("a?", "CLARIFY: shu?"), Exchange("b?", "SELECT 1"), Exchange("c?", "SELECT 2")),
                 template="P1B", role="dependent"),
            chat((Exchange("a?", "SELECT 1"), Exchange("b?", "SELECT 2")), template="P1D", role="dependent",
                 kind="reply", carried="accepted")]  # fmt: skip
    assert mix.part1_report(rows) == {"topic changes": 1, "after a CLARIFY, UNSUPPORTED or REPLY": 1,
                                      "3 or more earlier exchanges": 1, "follow-ups after older turns": 2,
                                      "answered CLARIFYs": 1, "thanks or ma fhemet with history": 1,
                                      "follow-up-looking topic changes": 1}  # fmt: skip


def test_the_mix_refuses_a_batch5_build_missing_a_part1_minimum(tmp_path, monkeypatch):
    data = tmp_path / "data"
    rows = [stored(r) for r in balanced() + batch4_balanced()]
    chat = stored(example("w kam mara?", template="P1A"))
    chat["labels"].update({"history": 1, "history_role": "independent", "spec": "b5-1-0"})
    write_batches(data, rows, rows[0])
    (data / "batch5" / "train.jsonl").write_text(json.dumps(chat) + "\n", encoding="utf-8")
    monkeypatch.setattr(mix, "add_history", lambda rows, split: (rows, {}))  # only the part-1 check is tested here
    with pytest.raises(mix.CoverageError, match="topic changes: 1 < 300"):
        mix.build_mix(data, data / "mix")
    assert not (data / "mix").exists()
