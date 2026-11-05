"""The pilot questions file (approved by the user on 2026-11-05). Nothing here touches a database."""

import json
from datetime import date

import pytest

from app.infrastructure.sql.query_rules import SqlGlotQueryRules
from app.infrastructure.sql.sql_guard import SqlGlotGuard
from research.evaluation.questions import expand, load_questions, seed_names

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
