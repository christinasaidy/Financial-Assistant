"""The Lebanese Arabizi pack (research/dataset/arabizi_pack.py -> backend/app/assistant_assets/arabizi/): current,
exported from the code exactly, her notes copied verbatim, and examples that keep her rulings. The forms and rulings
are Christina's; do not change an expected value to make a test pass."""

import json
import re

import pytest

from research.dataset import answers_build, arabizi_pack, batch5_build, build, checks, genders, months
from research.dataset.arabizi_pack import HEADER, PACK_DIR, PackError, quote_date

SOURCES_HERE = all(p.exists() for p in (arabizi_pack.NOTES_FILE, arabizi_pack.PHRASING_FILE, arabizi_pack.ANSWERS_FILE))
needs_sources = pytest.mark.skipif(not SOURCES_HERE, reason="her memory notes or data/batch5 answers are not here")


def _tracked(name: str) -> str:
    return (PACK_DIR / name).read_text(encoding="utf-8").replace("\r\n", "\n")


@pytest.fixture(scope="module")
def built():
    """The pack built once from the sources, only where they are."""
    if not SOURCES_HERE:
        pytest.skip("her memory notes or data/batch5 answers are not here")
    return arabizi_pack.pack()


@pytest.fixture(scope="module")
def forms():
    return json.loads(_tracked("forms.json"))


@pytest.fixture(scope="module")
def examples():
    lines = [json.loads(line) for line in _tracked("examples.jsonl").splitlines()]
    assert lines[0]["_generated"] == HEADER and lines[0]["count"] == len(lines) - 1
    return lines[1:]


@needs_sources
def test_the_tracked_pack_is_what_the_sources_give_now(built):
    assert arabizi_pack.differences(built) == []


@needs_sources
def test_check_reports_a_changed_missing_or_extra_file(built, tmp_path):
    arabizi_pack.write(built, tmp_path)
    assert arabizi_pack.differences(built, tmp_path) == []
    (tmp_path / "forms.json").write_text("{}", encoding="utf-8")
    (tmp_path / "VERSION").unlink()
    (tmp_path / arabizi_pack.WORD_LIST).write_text("x", encoding="utf-8")
    found = arabizi_pack.differences(built, tmp_path)
    assert {line.split(":")[0] for line in found} == {"forms.json", "VERSION", arabizi_pack.WORD_LIST}
    arabizi_pack.write(built, tmp_path)  # write puts every file right, the word list included
    assert arabizi_pack.differences(built, tmp_path) == [] and (tmp_path / arabizi_pack.WORD_LIST).exists()


def test_every_file_is_there_with_the_generated_header():
    for name in arabizi_pack.FILES:
        text = _tracked(name)
        if name.endswith(".json"):
            head = json.loads(text)["_generated"]
        elif name.endswith(".jsonl"):
            head = json.loads(text.splitlines()[0])["_generated"]
        else:
            head = text[:200]
        assert HEADER in head, name
    assert not list(PACK_DIR.glob("*.py")), "the backend reads plain files: no code in the pack"


def _three(item: dict) -> tuple:
    return item["man"], item["woman"], item["neutral"]


def _of(forms: genders.Forms) -> tuple:
    return forms.man, forms.woman, forms.not_given


def test_forms_json_holds_genders_py_tables_exactly(forms):
    tables = forms["reply_forms"]
    assert [_three(f) for f in tables["FORMS"]] == [_of(f) for f in genders.FORMS]
    assert {int(k): _three(f) for k, f in tables["SMALLTALK"].items()} == {k: _of(f) for k, f in genders.SMALLTALK.items()}
    assert {k: [_three(f) for f in v] for k, v in tables["DECIDING"].items()} == {
        k: [_of(f) for f in v] for k, v in genders.DECIDING.items()}
    assert {k: _three(f) for k, f in tables["PRICES"].items()} == {k: _of(f) for k, f in genders.PRICES.items()}
    assert _three(tables["PHARMACIES"]) == _of(genders.PHARMACIES)
    for name in ("PERIOD_QUESTIONS", "PLACE_QUESTIONS", "THING_QUESTIONS"):
        assert [_three(f) for f in tables[name]] == [_of(f) for f in getattr(genders, name)], name
    assert _three(tables["REFERS_TO_PRICE"]) == _of(genders.REFERS_TO_PRICE)
    assert _three(tables["LAST_ONE_QUESTION"]) == _of(genders.LAST_ONE_QUESTION)
    assert tables["NO_RECEIPT_AT"]["openings"] == list(genders.NO_RECEIPT_AT)
    assert tables["NO_RECEIPT_AT"]["suggestion"] == {g.value: t for g, t in genders._SUGGESTION.items()}
    assert forms["masculine_words"] == list(genders.MASCULINE_WORDS)
    assert [(p["woman"], p["man"]) for p in forms["speaker_words"]] == list(genders.SPEAKER_WORDS)
    assert forms["answer_words"] == {"man_only": list(answers_build.MAN_ONLY),
                                     "woman_only": list(answers_build.WOMAN_ONLY)}


def test_accepted_and_rejected_spellings_match_the_code(forms):
    spellings = forms["spellings"]
    assert {k: tuple(v) for k, v in spellings["accepted"].items()} == checks.ALSO_ACCEPTED
    assert spellings["rejected"] == {"batch5_build.REJECTED": list(batch5_build.REJECTED),
                                     "answers_build.REJECTED": list(answers_build.REJECTED),
                                     "months._ALSO_REJECTED": list(months._ALSO_REJECTED)}
    union = {*batch5_build.REJECTED, *answers_build.REJECTED, *months._ALSO_REJECTED}
    assert spellings["rejected_all"] == sorted(union)
    assert "eshhor" not in union  # her reversal, 2026-11-23


def test_number_words_and_fixes_match_the_code(forms):
    from research.dataset import fixes

    assert forms["fixes"]["numbers_in_words"] == fixes._IN_WORDS
    assert forms["fixes"]["single_letters"] == fixes.SINGLE_LETTERS
    assert [(f["pattern"], f["replacement"]) for f in forms["fixes"]["question_words"]] == [
        (p.pattern, r) for p, r in fixes.QUESTION_WORDS]


def test_never_used_forms_are_quoted_from_her_notes(forms):
    notes = _tracked("rulings_source.md")
    for entry in forms["spellings"]["never_in_rulings"]:
        assert entry["quote"] in notes, entry
        assert entry["form"].lower() in entry["quote"].lower(), entry


@needs_sources
def test_her_notes_are_copied_verbatim():
    for name, source in (("rulings_source.md", arabizi_pack.NOTES_FILE), ("phrasing_source.md", arabizi_pack.PHRASING_FILE)):
        copy = _tracked(name)
        assert copy.startswith("<!-- " + HEADER)
        assert copy.split("-->\n\n", 1)[1] == source.read_text(encoding="utf-8").replace("\r\n", "\n"), name


def test_the_style_guide_quotes_her_notes_word_for_word_with_their_dates():
    guide = _tracked("style_guide.md")
    sources = {arabizi_pack.N: _tracked("rulings_source.md"), arabizi_pack.P: _tracked("phrasing_source.md")}
    headings = re.findall(r"^## \d+\. (.+)$", guide, re.MULTILINE)
    assert headings == [heading for heading, _, _ in arabizi_pack.SECTIONS]
    for _, _, quotes in arabizi_pack.SECTIONS:
        for source, quote, _ in quotes:
            date = quote_date(quote, sources[source])
            assert f"({date}{'' if source == arabizi_pack.N else ' (phrasing)'}) {quote}" in guide, quote


def test_a_quote_must_be_on_exactly_one_line_and_takes_its_date():
    text = "Notes (2026-11-14):\n- first rule\n- (2026-11-20) second rule\n**Why:** a reason\n- (2026-11-21) second rule"
    assert quote_date("first rule", text) == "2026-11-14"
    assert quote_date("a reason", text) == "undated"
    with pytest.raises(PackError):
        quote_date("second rule", text)
    with pytest.raises(PackError):
        quote_date("not hers", text)


def test_about_a_hundred_examples_arabizi_and_mixed_first(examples):
    assert 90 <= len(examples) <= 110
    languages = [e["language"] for e in examples]
    assert languages == sorted(languages, key=["arabizi", "mixed", "english"].index)
    assert languages.count("arabizi") + languages.count("mixed") >= 0.8 * len(examples)
    assert len({e["result_kind"] for e in examples}) >= 20
    assert len({e["question"] for e in examples}) == len(examples)
    for e in examples:
        assert set(e) >= {"question", "result", "reply", "language", "gender"}
        assert e["gender"] in ("man", "woman", "not given")


def _words(text: str, words) -> list[str]:
    return [w for w in words if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text, re.IGNORECASE)]


def test_no_example_uses_a_rejected_spelling(examples, forms):
    never = [entry["form"] for entry in forms["spellings"]["never_in_rulings"]]
    for e in examples:
        assert not _words(e["question"] + "\n" + e["reply"], [*forms["spellings"]["rejected_all"], *never]), e


@pytest.mark.skipif(not build.TEST_QUESTIONS_FILE.exists(), reason="no test set")
def test_no_example_is_a_test_or_pilot_question(examples):
    tests = build.test_questions(None)
    normalized = {checks.normalized(q) for q in tests}
    for e in examples:
        assert checks.normalized(e["question"]) not in normalized, e["question"]
        assert checks.near_duplicate(e["question"], tests) is None, e["question"]


def test_every_arabizi_reply_is_in_the_users_gender(examples):
    man = (*answers_build.MAN_ONLY, *genders.MASCULINE_WORDS)
    other = {"woman": man, "man": answers_build.WOMAN_ONLY, "not given": (*man, *answers_build.WOMAN_ONLY)}
    for e in [e for e in examples if e["language"] != "english"]:
        assert not _words(e["reply"], other[e["gender"]]), e
    assert {e["gender"] for e in examples if e["language"] != "english"} == {"man", "woman", "not given"}


def test_a_mans_question_never_says_a_womans_i_word(examples):
    for e in examples:
        if e["gender"] == "man":
            assert not _words(e["question"], [w for w, _ in genders.SPEAKER_WORDS]), e
        if e["gender"] == "woman":
            assert not _words(e["question"], [m for _, m in genders.SPEAKER_WORDS]), e


def test_the_gender_filter_drops_the_other_genders_words():
    assert arabizi_pack.wrong_gender("Sarafte $5 hal shaher.", "man") == ["sarafte"]
    assert arabizi_pack.wrong_gender("Sarafet $5 hal shaher.", "woman") == ["sarafet"]
    assert arabizi_pack.wrong_gender("El masruf hal shaher: $5.", "not given") == []
    assert arabizi_pack.wrong_speaker("aday def3a 3al sushi", "man") == ["def3a"]


def test_the_word_list_is_in_by_default():  # her OK of 2026-11-23 to track it in git
    assert (PACK_DIR / arabizi_pack.WORD_LIST).exists()
    assert "word_list" in _tracked("VERSION")
    assert "word_list" in arabizi_pack.sources()
    assert "word_list" not in arabizi_pack.sources(with_word_list=False)


@needs_sources
def test_the_built_pack_has_the_word_list_unless_told_not_to(built):
    assert set(built) == set(arabizi_pack.FILES) | {arabizi_pack.WORD_LIST}
    assert arabizi_pack.WORD_LIST not in arabizi_pack.pack(with_word_list=False)


@needs_sources
def test_the_picks_are_the_same_every_run(built):
    assert arabizi_pack.pack()["examples.jsonl"] == built["examples.jsonl"]
