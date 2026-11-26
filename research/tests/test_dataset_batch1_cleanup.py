"""The batch-1 cleanup rules. Every expected value is a before / after sample Christina approved on 2026-11-21
(raw/batch5/batch1_audit/rules_review.md) or one of her rulings; do not change one to make a test pass."""

import pytest

from research.dataset import batch1_cleanup as bc


@pytest.mark.parametrize(("before", "after", "rule"), [
    ("adde sarfet 3and Hibou this month", "adde sarafet 3and Hibou this month", "sarfet"),
    ("adde sarfet 3a el khobez men awal ayyar la a7er el shaher",
     "adde sarafet 3al khobez men awal ayyar la a7er el shaher", "articles"),
    ("7seble li dafa3to bi el fasl", "7seble li dafa3to bel fasl", "articles"),
    ("shu average se3er el kilo fosto2 bi fawatire", "shu average se3er kilo el fosto2 bi fawatire", "articles"),
    ("shu ken se3er el liter benzin bi ekher fetoura", "shu ken se3er liter el benzin bi ekher fetoura", "articles"),
    ("bas adde 3al kaml fi adar?", "bas adde 3al kaml bi adar?", "period"),
    ("adde donut jebt el sayf li mara2", "adde donut jebt bel sayf li mara2", "period"),
    ("shu tole3 majmou3 fawatire men Carrefour bi osbou3 li mara2",
     "shu tole3 majmou3 fawatire men Carrefour el jem3a li mar2it", "period"),
    ("which shop did I spend the most at hal 2 jem3a", "which shop did I spend the most at hal jem3ten", "dual"),
    ("adde pizza shtarayt bi tneen shhour", "adde pizza shtarayt bi shahrain", "dual"),
    ("kam dafa3et 3al fries hal shaher?", "aday dafa3et 3al fries hal shaher?", "kam_money"),
    ("el soda adde 3am ykallefne bel motawassit", "el soda adde 3am ykallefne bel moyenne", "rejected_word"),
    ("adde ra7 men jaybte 3a pads Private hal sene", "aday sarafet 3a pads Private hal sene", "jaybte"),
    ("w el fetoura li ablo?", "w el fatoura li abla?", "li_ablo"),
])  # fmt: skip
def test_an_approved_sample(before, after, rule):
    new, fired = bc.cleaned(before)
    assert new == after and rule in fired


def test_kam_for_money_only_and_kam_dollar_stays():  # her rule: kam only counts; "kam dollar" is fine
    assert bc.cleaned("kam sarfet bi el maintenance")[0] == "aday sarafet bel maintenance"
    for q in ("kam marra rehet 3a Spinneys?", "kam fatoura 3ande?", "kam dollar sarafet bi kanoun l awal"):
        assert bc.cleaned(q) == (q, [])


def test_sa7abit_becomes_one_of_her_forms():
    new, _ = bc.cleaned("aya 3 categories sa7abit menne aktar masari el wikend")
    assert "sa7abit" not in new and new.startswith("aya 3 categories ") and new.endswith(" aktar shi el wikend")
    assert any(f in new for f in ("sarafet aalayon", "kalafoune", "kalafuni"))


def test_el_marra_li_ablo_becomes_li_abla_or_el_abla():  # marra is feminine
    assert bc.cleaned("w el marra li ablo?")[0] in ("w el marra li abla?", "w el marra el abla?")
    assert bc.cleaned("w el shaher li ablo?") == ("w el shaher li ablo?", [])  # masculine: stays


def test_a_bare_li_mara2_gets_el_shaher_but_not_after_a_time_word():
    assert bc.cleaned("baddi 7seble adde ra7 men jaybte 3a Dove shower gel li mara2")[0] == (
        "baddi 7seble aday sarafet 3a Dove shower gel el shaher li mara2")
    for q in ("w el jem3a li mara2?", "adde sarafet el khamis li mara2", "w el sene li mara2"):
        assert bc.cleaned(q) == (q, [])


def test_the_period_rule_runs_before_the_articles_rule():
    """Otherwise "bi osbou3 li mara2" becomes "bi el jem3a li mar2it" (found 2026-11-21)."""
    names = [name for name, _ in bc.RULES]
    assert names.index("period") < names.index("articles")


def test_emta_bekhlas_lines_are_dropped():  # her ruling: never
    assert bc.DROP.search("iza dallet hek, emta bekhlas ma3ashe")
    assert bc.DROP.search("adde bkhallas next month")
    assert not bc.DROP.search("adde sarafet hal shaher?")


def test_a_fine_line_is_left_alone():
    for q in ("shu tole3 majmou3 fawatire men Ogero hal shaher?", "2arenle masroufe hal shaher 3an el shaher li mara2",
              "ekher marra jebt shawarma, b adde ken?"):  # fmt: skip
        assert bc.cleaned(q) == (q, [])


# --- the rewrites of 2026-11-22 (raw/batch5/batch1_rewrites_review.md, approved with her edits) ---

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from research.dataset.rerender import read_prompt  # noqa: E402

DATA = Path(bc.__file__).parent / "data"


def _batch1_questions() -> set[str]:
    return {read_prompt(json.loads(line)["messages"][0]["content"]).question
            for split in ("train", "validation")
            for line in (DATA / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()}  # fmt: skip


@pytest.mark.parametrize(("old", "new"), [
    ("adde dafa3et bi falafel", "adeysh dafa3et 3al falafel?"),
    ("ma fhemet el jawab, fik tshra7a abssat?", "ma fhemet el jaweb, wade7le aktar"),
    ("baddi total masroufe el fasl hada", "baddi majmou3 masroufe hal fasel"),  # her spelling, accepted by the checks
    ("adde dafa3et bi hadeye", "adday dafa3et 3al hdeye?"),
    ("check el budget, amra over limit?", "check el budget, sert defe3 aktar mn el limit?"),
])  # fmt: skip
def test_an_approved_rewrite_replaces_its_question_in_batch1(old, new):
    questions = _batch1_questions()
    assert new in questions and old not in questions


def test_the_rewrite_groups_sql_lines_are_dropped_by_her_plan():
    drops = json.loads((Path(bc.__file__).parent / "review_drops.json").read_text(encoding="utf-8"))
    planned = [d for d in drops if d["why"].startswith("batch-1 audit: needs a native rewrite")]
    assert len(planned) == 420 and len({d["question"] for d in planned}) == 412
    questions = _batch1_questions()
    assert not any(d["question"] in questions for d in planned)
