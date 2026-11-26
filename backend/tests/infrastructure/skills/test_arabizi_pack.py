"""The Arabizi skill comes from the owner's generated pack, exactly as reviewed, or Standard does not run (handoff 13A).

After the pack is regenerated, test_the_pack_in_the_repository_is_the_reviewed_one fails and prints the new
fingerprint: review the new pack, then update EXPECTED_FINGERPRINT in app/infrastructure/skills/arabizi_pack.py."""

import shutil

import pytest

from app.infrastructure.skills.arabizi_pack import (
    EXPECTED_FINGERPRINT,
    FILES,
    PACK_DIR,
    ArabiziPackUnavailable,
    fingerprint,
    load_arabizi_pack,
)


def test_the_pack_in_the_repository_is_the_reviewed_one():
    found = fingerprint()
    assert found == EXPECTED_FINGERPRINT, f"The Arabizi pack changed; after review set EXPECTED_FINGERPRINT = {found!r}"


def test_the_skill_holds_her_rulings_forms_and_examples_and_the_checked_words():
    pack = load_arabizi_pack()
    text = pack.skill.text
    style_guide = (PACK_DIR / "style_guide.md").read_text(encoding="utf-8").split("-->", 1)[1].strip()
    assert style_guide in text  # word for word
    assert "### Reply forms and spellings (forms.json)" in text and "### Approved examples (examples.jsonl)" in text
    assert '"reply":"Zero kilo: ma jebet ma3moul bel 3 iyem el ekhrin."' in text  # the first approved example
    assert "do not edit by hand" not in text  # the generator's notes are not instructions for the model
    assert pack.skill.version == f"arabizi-pack-generator-1-{EXPECTED_FINGERPRINT[:12]}"
    assert {"sakin", "kallefetne"} <= pack.words.rejected
    assert "sarafet" in pack.words.man_only and "sarafte" in pack.words.woman_only


def test_the_skill_is_the_same_text_every_time_it_is_loaded():
    """It is part of the cached prefix: any difference would be a cache miss."""
    assert load_arabizi_pack().skill == load_arabizi_pack().skill


def _copy(tmp_path):
    for name in FILES:
        shutil.copy(PACK_DIR / name, tmp_path / name)
    return tmp_path


def test_a_pack_edited_by_hand_is_refused(tmp_path):
    pack = _copy(tmp_path)
    (pack / "style_guide.md").write_text("Say whatever you like.", encoding="utf-8")
    with pytest.raises(ArabiziPackUnavailable, match="not the reviewed one"):
        load_arabizi_pack(pack)


def test_a_missing_file_is_refused(tmp_path):
    pack = _copy(tmp_path)
    (pack / "forms.json").unlink()
    with pytest.raises(ArabiziPackUnavailable, match="could not be read"):
        load_arabizi_pack(pack)


def test_an_unreadable_pack_with_a_matching_fingerprint_is_refused(tmp_path):
    pack = _copy(tmp_path)
    (pack / "forms.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ArabiziPackUnavailable):
        load_arabizi_pack(pack, expected=fingerprint(pack))
