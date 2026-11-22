"""Batch 5: "the pharmacy" when the user has two (pharmacies.py, fixes.pharmacy_reply), her rulings and lines of
2026-11-22. Do not change an expected value to make a test pass. These tests read the saved jobs."""

import json

from app.domain.assistant.prompt import Gender
from research.dataset import pharmacies
from research.dataset.fixes import pharmacy_reply
from research.dataset.genders import for_gender
from research.dataset.rerender import read_prompt

JOBS = {j["job_id"]: j for j in map(json.loads, pharmacies.JOBS_FILE.read_text(encoding="utf-8").splitlines())}
BOTH_SQL = "SELECT 1 FROM receipts WHERE vendor IN ('Pharmacie Mazloum', 'Pharmacie Nassar')"
TWO = ["Spinneys", "Pharmacie Nassar", "Pharmacie Mazloum"]


def test_every_line_is_hers_and_every_query_has_an_answer(tmp_path):
    assert pharmacies.replay(out_dir=tmp_path) == {"train": 16, "validation": 2, "empty answers": []}
    assert all(j["rows"] for j in JOBS.values() if not j["reply"].startswith("CLARIFY"))


def test_her_four_ways_of_saying_both_are_answered_with_both_pharmacies():
    both = {j["question"]: j["reply"] for j in JOBS.values() if j["template"] == "PH2"}
    for word in ("tnayneton", "tnainetin", "el tnen", "l tnayn"):
        assert "vendor IN ('Pharmacie Mazloum', 'Pharmacie Nassar')" in both[word], word
    assert "vendor = 'Pharmacie Mazloum'" in both["Mazloum"] and "vendor = 'Pharmacie Nassar'" in both["Nassar"]


def test_a_chat_has_the_question_back_before_the_answer(tmp_path):
    pharmacies.replay(out_dir=tmp_path)
    rows = [json.loads(x) for x in (tmp_path / "pharmacies_train.jsonl").read_text(encoding="utf-8").splitlines()]
    chat = next(r for r in rows if r["labels"]["spec"] == "ph-t-6")
    parts = read_prompt(chat["messages"][0]["content"])
    assert parts.question == "tnayneton" and parts.history[0].question == "adesh sarafet bel saydaliye hal shaher?"
    assert parts.history[0].reply == "CLARIFY: azdak Pharmacie Mazloum aw Pharmacie Nassar?"


def test_the_question_back_takes_her_gender_forms():
    reply = pharmacies.ask()
    assert for_gender(reply, Gender.MAN) == "CLARIFY: azdak Pharmacie Mazloum aw Pharmacie Nassar?"
    assert for_gender(reply, Gender.WOMAN) == "CLARIFY: azdik Pharmacie Mazloum aw Pharmacie Nassar?"
    assert for_gender(reply, Gender.NOT_GIVEN) == "CLARIFY: Pharmacie Mazloum aw Pharmacie Nassar?"


def test_the_plural_adds_both_and_one_pharmacy_needs_no_question():
    for job in JOBS.values():
        if job["template"] == "PH3":
            assert "vendor IN ('Pharmacie Mazloum', 'Pharmacie Nassar')" in job["reply"]
        if job["template"] == "PH4":
            assert job["reply"].startswith("SELECT") and "vendor = 'Pharmacie Mazloum'" in job["reply"]
            assert [v for v in job["names"]["vendors"] if v.startswith("Pharmacie")] == ["Pharmacie Mazloum"]


def test_the_one_period_changed_from_her_line_is_marked():
    """Her line said "ekher shaher"; no train user with both pharmacies went to one last month."""
    assert JOBS["ph-t-9"]["question"] == "l tnayn" and JOBS["ph-t-9"]["earlier"] == "aday dafa3et bel saydaliye hal sene?"


# --- the stored lines (fixes.pharmacy_reply) ---


def test_the_pharmacy_with_no_name_and_two_pharmacies_now_asks_which():
    for q in ("aymata ro7t aal pharmacie men awal el sene la hala2?", "aymta rehet 3al pharmacy since the start of the year?",
              "3edele emta rehet 3al pharmacie mn awalt el sene"):
        assert pharmacy_reply(BOTH_SQL, q, TWO) == "CLARIFY: azdak Pharmacie Mazloum aw Pharmacie Nassar?"
    assert pharmacy_reply(BOTH_SQL, "When did I go to the pharmacy this year?", TWO, english=True) == \
        "CLARIFY: Pharmacie Mazloum or Pharmacie Nassar?"  # fmt: skip


def test_a_named_pharmacy_the_plural_a_pharmacy_or_one_pharmacy_are_left_as_they_are():
    for q in ("aday sarafet bi saydaliyet Mazloum?", "kam marra rehet 3al saydaliyet hal shaher?",
              "When did I visit a pharmacy this year?", "How often am I at Nassar pharmacy?", "How much at pharmacies?"):
        assert pharmacy_reply(BOTH_SQL, q, TWO) == BOTH_SQL, q
    one = "SELECT 1 FROM receipts WHERE vendor IN ('Pharmacie Mazloum')"
    assert pharmacy_reply(one, "emta rehet 3al pharmacie?", ["Pharmacie Mazloum"]) == one


STORED = ("aymta rehet 3al pharmacie mn awal el sene?", "aymata ro7t aal pharmacie men awal el sene la hala2?",
          "3edele emta rehet 3al pharmacie mn awalt el sene", "aymta rehet 3al pharmacy since the start of the year?",
          "When did I go to the pharmacy since the start of the year?")  # fmt: skip


def test_in_the_mix_the_five_stored_lines_ask_which_naming_two_pharmacies_of_the_users_list():
    import re

    from research.dataset import mix

    found = 0
    for line in (mix.DATA_DIR / "mix" / "train.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["labels"]["kind"] == "answer":
            continue
        parts = read_prompt(row["messages"][0]["content"])
        if parts.question not in STORED:
            continue
        found += 1
        reply = row["messages"][1]["content"]
        named = re.fullmatch(r"CLARIFY: (?:azdak |azdik )?(Pharmacie .+?) (?:aw|or) (Pharmacie .+?)\?", reply)
        assert named and set(named.groups()) <= set(parts.names.vendors), reply
        assert ("azdak" in reply) == (row["labels"]["gender"] == "man") or parts.question.startswith("When")
    assert found >= 5


def test_the_rebuild_turns_a_stored_pharmacy_line_into_her_question_back():
    from datetime import date

    from app.domain.assistant.prompt import UserNames, build_prompt
    from research.dataset.rerender import rerender

    names = UserNames(items=["bandages"], vendors=["Pharmacie Mazloum", "Spinneys", "Pharmacie Nassar"], categories=["Health"])
    question = "aymata ro7t aal pharmacie men awal el sene la hala2?"
    stored = {"messages": [{"role": "user", "content": build_prompt(question, names, date(2026, 5, 3), (), gender=Gender.WOMAN)},
                           {"role": "assistant", "content": BOTH_SQL}],
              "labels": {"kind": "sql", "user": 46, "language": "arabizi", "template": "B11"}}  # fmt: skip
    assert rerender(stored)["messages"][1]["content"] == "CLARIFY: azdik Pharmacie Mazloum aw Pharmacie Nassar?"
