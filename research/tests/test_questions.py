"""The pilot questions file (approved by the user on 2026-11-05) and the test set (2026-11-08). Nothing here
touches a database."""

import json
from datetime import date

import pytest

from app.infrastructure.sql.query_rules import SqlGlotQueryRules
from app.infrastructure.sql.sql_guard import SqlGlotGuard
from research.evaluation.questions import (QUESTIONS_FILE, TEST_QUESTIONS_FILE, data_user, expand, load_questions,
                                          seed_names)

TODAY, QUESTIONS = load_questions()
NAMES = seed_names()


def test_the_pilot_set_is_as_approved():
    assert TODAY == date(2026, 11, 3)
    assert len(QUESTIONS) == 47
    assert sum(q.language == "arabizi" for q in QUESTIONS) == 19
    groups = {}
    for q in QUESTIONS:
        if q.group:
            groups.setdefault(q.group, []).append(q.id)
    assert groups == {"last month": ["P03", "P03b"], "rice": ["P30", "P30b", "P30c"], "manakish": ["P32", "P32b"],
                      "greeting": ["P40", "P40b", "P40c"]}  # fmt: skip


def test_spellings_of_the_same_question_expect_the_same_answer():
    by_group = {}
    for q in QUESTIONS:
        if q.group:
            by_group.setdefault(q.group, set()).add(q.accept)
    assert all(len(answers) == 1 for answers in by_group.values())


def test_p37_djej_accepts_the_raw_chicken_or_a_clarifying_question():
    djej = next(q for q in QUESTIONS if q.id == "P37")
    assert "item_name = 'chicken'" in djej.accept[0].sql and djej.accept[1].reply.value == "clarify"


@pytest.mark.parametrize("sql", [a.sql for q in QUESTIONS for a in q.accept if a.sql]
                         + [turn.reply for q in QUESTIONS for turn in q.history])  # fmt: skip
def test_every_expected_query_passes_the_guard_and_the_answering_rules(sql):
    SqlGlotQueryRules().prepare(SqlGlotGuard().check(sql), NAMES, TODAY)


def test_placeholders_are_expanded_and_unknown_ones_refused():
    assert "{" not in "".join(a.sql for q in QUESTIONS for a in q.accept if a.sql)
    assert "date_trunc('week', CURRENT_DATE)" in expand("{LAST_WEEK}")
    with pytest.raises(ValueError):
        expand("{NEXT_YEAR}")


def test_a_file_with_a_repeated_id_is_refused(tmp_path):
    entry = {"id": "P01", "language": "en", "type": "total", "question": "q", "accept": [{"reply": "REPLY"}]}
    path = tmp_path / "questions.json"
    path.write_text(json.dumps({"today": "2026-11-03", "questions": [entry, {**entry, "question": "r"}]}))
    with pytest.raises(ValueError, match="unique"):
        load_questions(path)


# --- the test set (decided with the user on 2026-11-08) ---

TEST_TODAY, TEST_QUESTIONS = load_questions(TEST_QUESTIONS_FILE)
TEST_ENTRIES = json.loads(TEST_QUESTIONS_FILE.read_text(encoding="utf-8"))["questions"]
SECTIONS = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12", "T13", "T14", "T15", "T16",
            "T17", "F", "C", "U", "R"]  # fmt: skip


def test_the_test_set_is_a_third_of_each_seed_section_asked_as_user_31():
    from research.dataset.catalogue import load_catalogue
    from research.dataset.users import make_user

    counts = [6, 6, 9, 6, 5, 7, 7, 6, 6, 9, 7, 7, 11, 7, 11, 7, 7, 9, 7, 7, 8]
    assert [sum(e["template"] == s for e in TEST_ENTRIES) for s in SECTIONS] == counts and len(TEST_QUESTIONS) == 155
    assert data_user(TEST_QUESTIONS_FILE) == 31 and data_user(QUESTIONS_FILE) is None
    assert TEST_TODAY == make_user(load_catalogue(), 31).today == date(2028, 1, 12)


def test_no_test_question_is_left_among_the_seeds_the_generator_sees():
    from research.dataset.generator_prompt import load_seeds

    seen = {question for questions in load_seeds().questions.values() for question in questions}
    asked = [e["seed"] for e in TEST_ENTRIES] + [q.question for q in TEST_QUESTIONS]
    asked += [turn.question for q in TEST_QUESTIONS for turn in q.history]
    assert [question for question in asked if question in seen] == []
    assert sum(len(questions) for questions in load_seeds().questions.values()) == 465 - 155


def test_the_test_questions_are_unique_and_the_changed_ones_are_kept_with_their_seed():
    assert len({q.question for q in TEST_QUESTIONS}) == 155  # the expected-answers model looks them up by text
    starbucks = next(e for e in TEST_ENTRIES if e["seed"].startswith("kel yom Starbucks"))
    assert starbucks["question"] == "kel yom Furn el Hara, adde sarle def3a 3andon hal jemaa"
    tasli7 = next(e for e in TEST_ENTRIES if "tasli7" in e["seed"])
    assert tasli7["question"] == tasli7["seed"] and tasli7["accept"] == [{"reply": "CLARIFY"}]
