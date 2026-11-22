"""Batch 5 part 5: everyday words (matra7, abel mbereh). The plan and the written versions were approved by Christina on
2026-11-20 (raw/batch5/words/); do not change an expected value to make a test pass. These tests read the stored
batch 2-4 data and the approved jobs and versions."""

import json
import shutil
from collections import Counter
from datetime import date

import pytest

from research.dataset import words
from research.dataset.checks import Version, problems
from research.dataset.rerender import read_prompt, rerender
from research.dataset.users import gender_of
from research.dataset.words import WordsError, replay

JOBS = {j["job_id"]: j for j in map(json.loads, words.JOBS_FILE.read_text(encoding="utf-8").splitlines())}
MATRA7 = json.loads(words.MATRA7_FILE.read_text(encoding="utf-8"))
DAY_BEFORE = json.loads(words.DAY_BEFORE_FILE.read_text(encoding="utf-8"))
AAL = json.loads(words.AAL_FILE.read_text(encoding="utf-8"))  # approved 2026-11-22
EVERYDAY = json.loads(words.EVERYDAY_FILE.read_text(encoding="utf-8"))  # her review 2026-11-22


@pytest.fixture(scope="module")
def plan():
    return words.plan()


@pytest.fixture(scope="module")
def stored():
    return words.stored(), words.stored_specs()


def _raw(tmp_path, matra7=MATRA7, day_before=DAY_BEFORE, aal=AAL, everyday=EVERYDAY):
    raw = tmp_path / "raw"
    raw.mkdir()
    shutil.copy(words.JOBS_FILE, raw / words.JOBS_FILE.name)
    (raw / words.MATRA7_FILE.name).write_text(json.dumps(matra7), encoding="utf-8")
    (raw / words.DAY_BEFORE_FILE.name).write_text(json.dumps(day_before), encoding="utf-8")
    (raw / words.AAL_FILE.name).write_text(json.dumps(aal), encoding="utf-8")
    (raw / words.EVERYDAY_FILE.name).write_text(json.dumps(everyday), encoding="utf-8")
    return raw


# --- the plan ---


def test_the_saved_jobs_are_the_plan(plan):
    """The approved versions were written for exactly these jobs: replanning must not move any of them."""
    planned = json.loads(json.dumps([[j["job_id"], j["kind"], j["spec"]] for j in plan]))  # as saved: lists
    assert planned == [[j["job_id"], j["kind"], j["spec"]] for j in JOBS.values()]


def test_each_kind_is_asked_on_a_day_with_receipts_and_three_empty_days_are_planned():  # approved 2026-11-20
    assert Counter(j["kind"] for j in JOBS.values()) == {"total": 4, "visits": 4, "item": 4, "top shop": 3,
                                                         "bought": 3, "category": 3}  # fmt: skip
    empty = {j["job_id"]: j["kind"] for j in JOBS.values() if j["rows"] == 0}
    assert empty == {"w-1": "total", "w-3": "visits", "w-4": "item"}
    assert {j["spec"]["labels"]["period"] for j in JOBS.values()} == {"day_before_yesterday"}
    assert all("CURRENT_DATE - 2" in j["spec"]["target"] for j in JOBS.values())
    assert Counter(j["split"] for j in JOBS.values()) == {"train": 16, "validation": 5}


def test_a_category_counts_a_lines_own_category_first(plan):
    """Bread at Wooden Bakery is Groceries in category_spending, not the shop's Dining (found 2026-11-20: asking
    Dining gave an empty result)."""
    job = next(j for j in plan if j["job_id"] == "w-14")
    assert job["kind"] == "category" and job["spec"]["labels"]["category"] == "Groceries"
    assert JOBS["w-14"]["rows"] == 1


# --- the build of the approved versions ---


def test_every_approved_version_becomes_one_example_and_none_is_near_a_test_question(tmp_path):
    report = replay(out_dir=tmp_path)
    assert report == {"train": 90, "validation": 16, "near test questions, dropped": 0,  # + her 10 aal and 56
                      "words": {"matra7": 19, "aal": 10, "everyday": 56, "abel mbereh": 21}}  # everyday, 2026-11-22
    rows = [json.loads(line) for split in ("train", "validation")
            for line in (tmp_path / f"words_{split}.jsonl").read_text(encoding="utf-8").splitlines()]  # fmt: skip
    assert {r["labels"]["part"] for r in rows} == {"words"}
    assert all(r["labels"]["split"] == split for split in ("train", "validation")
               for r in map(json.loads, (tmp_path / f"words_{split}.jsonl").read_text(encoding="utf-8").splitlines()))


def test_a_matra7_version_keeps_its_stored_questions_reply_names_today_and_gender(stored):
    rows, specs = stored
    version = MATRA7[0]  # "aya matra7 sarafet fi aktar shi el jem3a li mar2it?"
    example = words.matra7_examples([version], rows, specs)[0]
    row = rows[version["spec"]]
    assert example["messages"][1]["content"] == row["messages"][1]["content"]
    mine, theirs = read_prompt(example["messages"][0]["content"]), read_prompt(rerender(row)["messages"][0]["content"])
    assert mine.question == version["question"]
    assert (mine.names, mine.today, mine.history) == (theirs.names, theirs.today, ())
    assert example["messages"][0]["content"] == rerender(row)["messages"][0]["content"].replace(
        theirs.question, version["question"])  # fmt: skip
    assert example["labels"]["word"] == "matra7" and example["labels"]["spec"] == "b2-6-27"


def test_a_validation_specs_matra7_version_stays_in_validation(stored):
    version = next(v for v in MATRA7 if v["spec"] == "b3-40-6")
    assert words.matra7_examples([version], *stored)[0]["labels"]["split"] == "validation"


def test_an_abel_mbereh_version_answers_with_its_target_on_its_users_day():
    job = JOBS["w-8"]  # "aya matra7 sarafet fi aktar shi abel mbereh?"
    example = words.day_before_examples([job], {"w-8": DAY_BEFORE["w-8"]})[0]
    parts = read_prompt(example["messages"][0]["content"])
    assert parts.question == "aya matra7 sarafet fi aktar shi abel mbereh?"
    assert example["messages"][1]["content"] == job["spec"]["target"]
    assert parts.today == date.fromisoformat(job["today"]) and parts.history == ()
    assert f"The user is a {gender_of(job['user']).value}." in example["messages"][0]["content"]
    assert (example["labels"]["template"], example["labels"]["result_rows"]) == ("T7", 1)


def test_abl_mbereh_counts_as_the_day_before_yesterday():  # approved 2026-11-20
    spec = words._spec(JOBS["w-9"]["spec"])
    assert problems(Version("arabizi", "shu jebt abl mbereh?"), spec, words._catalogue(9)) == []
    assert problems(Version("arabizi", "shu jebt mbereh?"), spec, words._catalogue(9)) == [
        "does not mention any of: day before yesterday, abel mbereh, abel mbere7, awalt mbereh"]


@pytest.mark.parametrize(("version", "message"), [
    ({"spec": "b4-49-2", "language": "arabizi", "question": "aya matra7 sarafet fi aktar shi hal shaher?"}, "wafir"),
    ({"spec": "b3-34-2", "language": "arabizi", "question": "sabghit el sha3er, b aya matrah kenet arkhas shi?"},
     "hair dye"),
    ({"spec": "b2-20-14", "language": "arabizi", "question": "ekher marra jebt beyd, aday kallefetne?"}, "rejected"),
])  # fmt: skip
def test_a_matra7_version_that_fails_a_check_is_refused(stored, version, message):
    with pytest.raises(WordsError, match=message):
        words.matra7_examples([version], *stored)


def test_a_wrongly_written_abel_mbereh_version_is_refused_and_nothing_is_written(tmp_path):
    wrong = {**DAY_BEFORE, "w-9": [{"language": "arabizi", "question": "shu jebt mbereh?"}]}
    with pytest.raises(WordsError, match="w-9"):
        replay(raw_dir=_raw(tmp_path, day_before=wrong), out_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_a_job_without_its_versions_refuses_the_whole_set(tmp_path):
    missing = {k: v for k, v in DAY_BEFORE.items() if k != "w-51"}
    with pytest.raises(WordsError, match="planned"):
        replay(raw_dir=_raw(tmp_path, day_before=missing), out_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_a_version_near_a_held_out_question_is_dropped(tmp_path):
    report = replay(raw_dir=_raw(tmp_path), out_dir=tmp_path / "out", held_out=(DAY_BEFORE["w-25"][0]["question"],))
    assert report["near test questions, dropped"] >= 1
    assert report["train"] + report["validation"] == 106 - report["near test questions, dropped"]


# --- aal (to the, before an unnamed thing), approved 2026-11-22 ---


def test_an_aal_version_keeps_its_stored_questions_reply_and_needs_no_lead_in(stored):
    rows, specs = stored
    version = next(v for v in AAL if v["spec"] == "b4-47-1")  # stored: "emme aletle eno ktir 3am jib khebez, ..."
    assert version["question"] == "adesh sarafet aal khebez ekher shaher?"
    example = words.matra7_examples([version], rows, specs, "aal")[0]
    assert example["messages"][1]["content"] == rows["b4-47-1"]["messages"][1]["content"]
    assert read_prompt(example["messages"][0]["content"]).question == version["question"]
    assert example["labels"]["word"] == "aal"


def test_every_aal_version_says_aal():
    assert len(AAL) == 10 and all(" aal " in f" {v['question']} " for v in AAL)


def test_an_aal_version_without_its_item_is_refused(stored):
    version = {"spec": "b4-47-1", "language": "arabizi", "question": "adesh sarafet aal akel ekher shaher?"}
    with pytest.raises(WordsError, match="does not mention"):
        words.matra7_examples([version], *stored, "aal")



# --- the everyday words from her list (her review 2026-11-22) ---


@pytest.fixture(scope="module")
def everyday(stored):
    return {read_prompt(e["messages"][0]["content"]).question: e for e in words.everyday_examples(EVERYDAY, *stored)}


def test_an_everyday_version_keeps_its_stored_answer(everyday, stored):
    rows, _ = stored
    example = everyday["khaberne 3and aya ma7al sarafet aktar shi ekher shaher"]  # her fix: khaberne, single letters
    assert example["messages"][1]["content"] == rows["b3-38-7"]["messages"][1]["content"]
    assert example["labels"]["word"] == "everyday"


def test_a_question_back_echoes_her_spelling(everyday):
    assert everyday["shefle addesh dafa3et 3al 7amed"]["messages"][1]["content"].startswith(
        "CLARIFY: ma edert le2e fatoura 3an 7amed")


@pytest.mark.parametrize(("question", "template"), [
    ("shil hal fatoura, sajalta ghalat", "U9"),  # an action the assistant cannot do
    ("adeysh ra7 osrof bokra w ba3d bokra?", "U2"),  # a prediction
    ("adde 2abadet retib hal shaher?", "U5"),  # income
])  # fmt: skip
def test_an_everyday_refusal(everyday, question, template):
    example = everyday[question]
    assert example["messages"][1]["content"] == "UNSUPPORTED" and example["labels"]["template"] == template


def test_her_rejected_list_words_are_not_used():
    text = json.dumps(EVERYDAY)
    assert "fershet sean" not in text and "shteret" not in text and "khabberne" not in text


def test_her_list_spellings_count_as_the_period_and_item_words():
    from research.dataset.checks import mentions

    assert mentions("adesh sarafet el shaher li ra7?", ("li mara2",))
    assert mentions("shefle addesh dafa3et 3al 7amed", ("7amod",))


def test_a_version_said_by_the_wrong_gender_is_refused(stored):
    version = {"spec": "b4-47-17", "language": "mixed", "question": "quick question, how much def3a 3al lahme mafroume?",
               "gender": "woman"}  # user 47 is a man
    with pytest.raises(WordsError, match="said by a woman"):
        words.matra7_examples([version], *stored, "everyday")
