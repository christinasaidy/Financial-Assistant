"""Batch 5 part 2: small talk. The kinds, replies, question edits and new questions were approved by Christina on
2026-11-20 (raw/batch5/smalltalk_*_review.md, raw/batch5/smalltalk/); do not change an expected value to make a test
pass. These tests read the stored batch 1-4 data and the approved files."""

import json
import shutil
from collections import Counter

import pytest

from app.domain.assistant.prompt import Gender
from research.dataset import genders, smalltalk
from research.dataset.genders import SMALLTALK
from research.dataset.rerender import read_prompt, rerender
from research.dataset.smalltalk import REPLIES, SmalltalkError, build_smalltalk, reply_for
from research.dataset.users import gender_of

RAW = smalltalk.RAW_DIR
STORED = smalltalk.stored_rows()


def _load(name):
    return json.loads((RAW / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("smalltalk")
    report = build_smalltalk(out_dir=out)
    rows = [json.loads(line) for split in ("train", "validation")
            for line in (out / f"smalltalk_{split}.jsonl").read_text(encoding="utf-8").splitlines()]  # fmt: skip
    return report, rows


def _raw(tmp_path, **changed):
    raw = tmp_path / "raw"
    raw.mkdir()
    for name in ("kinds.json", "edits.json", "new.json", "greetings.json"):
        shutil.copy(RAW / name, raw / name)
    for name, value in changed.items():
        (raw / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return raw


def _questions(rows, kind=None):
    return [read_prompt(r["messages"][0]["content"]).question for r in rows
            if kind is None or r["labels"]["smalltalk"] == kind]  # fmt: skip


# --- the approved build ---


def test_every_approved_line_becomes_one_example(built):
    report, rows = built
    assert (report["train"], report["validation"], report["near test questions, dropped"]) == (406, 93, 0)
    assert report["kinds"] == {
        "thanks": 72, "acknowledgement": 17, "what can you do": 75, "complaint": 31, "surprise": 31, "how are you": 75,
        "good wish": 5, "greeting": 32, "greeting (sabah)": 33, "greeting (bonjour)": 6, "who are you": 23,
        "are you there": 19, "joke": 4, "bye": 32, "not well": 12, "greeting + question": 30, "compliment": 2}
    stored = [r for r in rows if not r["labels"]["spec"].startswith("s2-new") and r["labels"]["smalltalk"] != "greeting + question"]
    assert len(stored) == len(STORED) == 374  # every stored small-talk example, once
    assert {r["labels"]["part"] for r in rows} == {"smalltalk"}


def test_a_how_are_you_never_gets_a_laugh(built):
    """The bug that started part 2: every Arabizi chit-chat line got 'hahaha, fie se3dak b shi tene?'."""
    _, rows = built
    allowed = {f.man for f in REPLIES["how are you"]} | {"REPLY: " + e for e in smalltalk.ENGLISH["how are you"]}
    how = [r for r in rows if r["labels"]["smalltalk"] == "how are you"]
    assert how and all(r["messages"][1]["content"] in allowed for r in how)
    assert len({r["messages"][1]["content"] for r in how if r["labels"]["language"] != "english"}) == 5  # rotated


def test_a_greeting_is_answered_in_kind():
    assert reply_for("greeting (sabah)", "arabizi", "sabah el kheir", "x") == SMALLTALK[3].man  # sabah el nour
    assert reply_for("greeting (bonjour)", "arabizi", "bonjour", "x") == SMALLTALK[4].man
    assert reply_for("good wish", "arabizi", "nharak sa3id", "x") == SMALLTALK[29].man  # "W nharak!"
    assert reply_for("good wish", "arabizi", "ya3tik el 3afye", "x") == SMALLTALK[30].man


def test_an_english_kind_without_a_reviewed_set_keeps_its_stored_reply():
    stored = "REPLY: Hi! Yes, I'm here. How can I help with your receipts?"
    assert reply_for("are you there", "english", "Hi, are you there?", "x", stored) == stored
    with pytest.raises(SmalltalkError, match="no English reply"):
        reply_for("are you there", "english", "Hi, are you there?", "x")


def test_no_small_talk_reply_states_a_number(built):
    _, rows = built
    assert not any(smalltalk._NUMBER.search(r["messages"][1]["content"]) for r in rows
                   if r["messages"][1]["content"].startswith("REPLY:"))  # fmt: skip


# --- her edits to the stored questions ---


def test_her_edits_are_applied_example_by_example(built):
    _, rows = built
    questions = Counter(_questions(rows))
    assert sum(n for q, n in questions.items() if "shlonak" in q) == 5  # decision 4: keep about 5
    assert questions["wow ma kent mwa2a3a"] == 8 and questions["wow ma kent metwa23a"] == 3
    assert not any("b7al hada" in q or "bhal hada" in q for q in questions)  # not Lebanese
    assert questions["shu be2dar es2alak 3an fawatire"] == 9 and questions["khay, that is what I wanted"] == 3
    assert questions["kifak ya 3omri"] == 1 and questions["eh hek tamem, teslam"] == 2


def test_a_man_says_mwa2a3_and_a_woman_mwa2a3a(built):
    _, rows = built
    for r in rows:
        question = read_prompt(rerender(r)["messages"][0]["content"]).question
        if "ma kent mwa2a3" in question or "ma kent metwa" in question:
            man = gender_of(r["labels"]["user"]) is Gender.MAN
            assert ("mwa2a3a" not in question and "metwa23a" not in question) == man, question
    assert genders.question_for_gender("wow ma kent mwa2a3a", Gender.MAN) == "wow ma kent mwa2a3"


@pytest.mark.parametrize(("changed", "message"), [
    ({"edits": {**_load("edits.json"), "arabizi|shlonak": [None, "kifak"]}}, "2 edits for 10 examples"),
    ({"edits": {**_load("edits.json"), "arabizi|never asked": "x"}}, "not stored"),
    ({"kinds": {k: v for k, v in _load("kinds.json").items() if k != "arabizi|marhaba"}}, "no kind"),
])  # fmt: skip
def test_a_question_edit_or_kind_that_does_not_match_the_stored_data_refuses(tmp_path, changed, message):
    with pytest.raises(SmalltalkError, match=message):
        build_smalltalk(raw_dir=_raw(tmp_path, **changed), out_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


# --- the new questions ---


def test_a_gendered_new_question_goes_to_a_user_of_its_gender(built):
    _, rows = built
    new = {q["question"]: q["gender"] for q in _load("new.json") if q["gender"]}
    placed = [(r, new[q]) for r, q in zip(rows, _questions(rows)) if r["labels"]["spec"].startswith("s2-new") and q in new]
    assert len(placed) == 8
    assert all(gender_of(r["labels"]["user"]).value == gender for r, gender in placed)


def test_a_greeting_in_front_of_a_question_keeps_its_sql(built):
    _, rows = built
    greeted = [r for r in rows if r["labels"]["smalltalk"] == "greeting + question"]
    assert len(greeted) == 30 and all(r["messages"][1]["content"].startswith("SELECT") for r in greeted)
    assert "marhaba, aday sar masroufe 3al 3adas la hadit hala2" in _questions(greeted)  # her spelling, accepted


def test_a_greeting_version_missing_its_questions_words_refuses(tmp_path):
    versions = [dict(v, question="marhaba, aday sar masroufe 3al 3adas la halla") if v["spec"] == "b3-36-8" else v
                for v in _load("greetings.json")]  # fmt: skip
    with pytest.raises(SmalltalkError, match="sarle"):
        build_smalltalk(raw_dir=_raw(tmp_path, greetings=versions), out_dir=tmp_path / "out")


def test_hi_kifak_is_kept_but_any_other_line_near_a_test_question_is_dropped(tmp_path):
    """Her decision (2026-11-20): "hi kifak" is the most common greeting, kept although near a test question."""
    report = build_smalltalk(raw_dir=_raw(tmp_path), out_dir=tmp_path / "out", held_out=("hi kifak", "yalla bye"))
    assert report["near test questions, dropped"] == sum(q == "yalla bye" for q in _questions(
        [json.loads(line) for split in ("train", "validation") for line in
         (smalltalk.DATA_DIR / f"smalltalk_{split}.jsonl").read_text(encoding="utf-8").splitlines()]))
    kept = _questions([json.loads(line) for split in ("train", "validation") for line in
                       (tmp_path / "out" / f"smalltalk_{split}.jsonl").read_text(encoding="utf-8").splitlines()])
    assert "hi kifak" in kept and "yalla bye" not in kept


@pytest.mark.parametrize(("question", "reply", "message"), [
    ("aday sarafet?", "REPLY: you spent 5 dollars", "states a number"),
    ("el 3elka adday kallefetne?", "REPLY: Walaw", "rejected spelling"),
    ("مرحبا", "REPLY: Walaw", "Arabic script"),
])  # fmt: skip
def test_a_line_that_fails_a_check_is_refused(question, reply, message):
    with pytest.raises(SmalltalkError, match=message):
        smalltalk._check_line("x", "arabizi", question, reply)
    smalltalk._check_line("x", "arabizi", "merci", "REPLY: Walaw")  # a good line passes
