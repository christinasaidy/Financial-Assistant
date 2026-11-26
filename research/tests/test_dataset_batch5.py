"""Batch 5 part 1: the chat jobs and their build. The plan's rules and the written versions were approved by Christina on
2026-11-17/19 (8 review chunks, raw/batch5/review_chunk*.md); do not change an expected value to make a test pass.
These tests read the stored batch-3/4 data and the approved jobs and versions (raw/batch5/)."""

import json
import re
from collections import Counter
from datetime import date

import pytest

from app.domain.assistant.prompt import Exchange
from research.dataset import batch5, batch5_build
from research.dataset.batch5_build import AuthoredError, check_versions, load_authored, replay
from research.dataset.rerender import read_prompt
from research.dataset.users import gender_of

JOBS = {j["job_id"]: j for j in map(json.loads, batch5_build.JOBS_FILE.read_text(encoding="utf-8").splitlines())}
AUTHORED = load_authored()


@pytest.fixture(scope="module")
def plan():
    return batch5.plan()


@pytest.fixture(scope="module")
def stored():
    return batch5_build.stored_rows()


# --- the plan ---


def test_the_plan_has_the_approved_jobs_per_kind_and_split(plan):
    counts = Counter((job.split, job.kind) for job in plan)
    assert counts == {(split, kind): n for split, kinds in batch5.COUNTS.items() for kind, n in kinds.items()}
    assert len({job.job_id for job in plan}) == 160


def test_the_saved_jobs_are_the_plan(plan):
    """The approved versions were written for exactly these jobs: replanning must not move any of them."""
    for job in plan:
        saved = JOBS[job.job_id]
        assert (saved["first_spec"], saved["kind"], saved["sub"]) == (job.first_spec, job.kind, job.sub)
        assert [t["target"] for t in saved["turns"]] == [t.target for t in job.turns]


def test_a_first_question_starts_at_most_two_chats_outside_answered_clarifications(plan):
    uses = Counter(job.first_spec for job in plan if job.kind != "B")
    assert max(uses.values()) <= 2


def test_bills_and_subscriptions_are_never_counted(plan):
    data = {}
    for job in plan:
        for turn in job.turns:
            name = turn.labels.get("other") or turn.labels.get("named")
            if name and "COUNT(DISTINCT" in turn.target:
                user = data.setdefault(job.user, batch5.user_data(job.user))
                assert not batch5._is_bill(user, name), (job.job_id, name)


def test_a_correction_names_something_the_user_could_have_meant(plan):
    stored = {s.spec: s for specs in batch5.load_stored().values() for s in specs}
    catalogue = batch5.user_data(32).catalogue
    for job in plan:
        if job.sub != "correction":
            continue
        meant, first = job.turns[-1].labels["other"], stored[job.first_spec]
        asked = batch5._item_name(first.what) or batch5._shop_name(first.what)
        if job.turns[-1].labels["correction"] == "item":
            group = catalogue.item(asked).group
            close = set().union(*(s for s in batch5.CONFUSED if asked in s))
            assert meant in close or (group and catalogue.item(meant).group == group), (asked, meant)
        else:
            data = batch5.user_data(job.user)
            assert data.shop(meant).kind == data.shop(asked).kind, (asked, meant)


def test_the_first_questions_period_is_kept_exactly_when_the_new_turn_leaves_it_out(plan):
    stored = {s.spec: s for specs in batch5.load_stored().values() for s in specs}
    for job in plan:
        first = stored[job.first_spec]
        if job.sub in ("measure", "correction") and "MAX(receipt_date)" not in job.turns[-1].target:
            assert first.period in job.turns[-1].target
        if job.sub == "carried period":
            assert first.period and first.period in job.turns[0].target
        if job.sub == "removed filter" and job.turns[-1].labels["removed"] == "shop":
            assert first.period in job.turns[-1].target and "vendor" not in job.turns[-1].target


def test_a_topic_change_names_its_own_item_or_shop_and_period(plan):
    stored = {s.spec: s for specs in batch5.load_stored().values() for s in specs}
    for job in plan:
        if job.kind != "A":
            continue
        target = job.turns[-1].target
        assert "receipt_date" in target and re.search(r"(item_name|vendor) = '", target)
        assert stored[job.first_spec].what not in target or not stored[job.first_spec].what


# --- the build of the approved versions ---


def test_every_approved_version_becomes_one_chat_and_none_is_near_a_test_question(tmp_path):
    report = replay(out_dir=tmp_path)
    assert (report["train"], report["validation"], report["near test questions, dropped"]) == (560, 80, 0)
    rows = [json.loads(line) for line in (tmp_path / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(r["labels"]["history_role"] in ("independent", "dependent") for r in rows)
    assert {r["labels"]["history_role"] for r in rows if r["labels"]["template"] == "P1A"} == {"independent"}


def test_a_carried_chat_is_the_first_question_then_the_carried_turn_then_the_thanks(stored):
    job, version = JOBS["b5-46-5"], AUTHORED["b5-46-5"][0]
    example = batch5_build.chat_example(job, version, stored)
    parts = read_prompt(example["messages"][0]["content"])
    language, first_question = job["first_versions"][version["first"]]
    first = stored[(job["first_spec"], first_question)]
    assert parts.history == (Exchange(first_question, first["messages"][1]["content"]),
                             Exchange(version["lines"][0], job["turns"][0]["target"]))  # fmt: skip
    assert parts.question == version["lines"][1]
    assert example["messages"][1]["content"] == job["turns"][1]["target"]
    assert example["messages"][1]["content"].removeprefix("REPLY: ") in batch5.THANKS_REPLIES
    assert parts.today == date.fromisoformat(job["today"])
    assert f"The user is a {gender_of(job['user']).value}." in example["messages"][0]["content"]


def test_the_english_version_of_a_thanks_gets_the_english_reply(stored):
    job = JOBS["b5-46-5"]
    english = next(v for v in AUTHORED["b5-46-5"] if job["first_versions"][v["first"]][0] == "english")
    example = batch5_build.chat_example(job, english, stored)
    assert example["messages"][1]["content"] == job["turns"][1]["english_target"]


def test_a_clarified_question_is_answered_with_the_option_its_version_names(stored):
    job = JOBS["b5-32-2"]
    for version in AUTHORED["b5-32-2"]:
        example = batch5_build.chat_example(job, version, stored)
        assert example["messages"][1]["content"] == job["turns"][-1]["options"][version["target"]]
        assert read_prompt(example["messages"][0]["content"]).history[0].reply.startswith("CLARIFY:")


@pytest.mark.parametrize(("change", "message"), [
    (lambda vs: vs[:3], "needs 4 versions"),
    (lambda vs: [vs[0], vs[0], vs[1], vs[2]], "needs 4 versions"),
    (lambda vs: [dict(v, lines=v["lines"] + ["extra"]) for v in vs], "lines for"),
    (lambda vs: [dict(v, lines=["tab w kam mara jebet sushi ekher 3 jem3at?"]) for v in vs], "rejected spelling"),
    (lambda vs: [dict(v, lines=["bas aday sarafet bel yomein li fetou?"]) for v in vs], "rejected spelling"),
])  # fmt: skip
def test_a_wrongly_written_job_is_refused(change, message):
    job = JOBS["b5-32-0"]
    with pytest.raises(AuthoredError, match=message):
        check_versions(job, change(AUTHORED["b5-32-0"]))


def test_a_job_needs_exactly_one_english_version():
    job, version = JOBS["b5-33-0"], AUTHORED["b5-33-0"][0]  # its first question has 4 Arabizi/mixed, 2 English
    english = [i for i, (language, _) in enumerate(job["first_versions"]) if language == "english"]
    others = [i for i, (language, _) in enumerate(job["first_versions"]) if language != "english"]
    assert len(english) == 2 and len(others) == 4
    for firsts in (others[:2] + english, others):  # two English versions; none
        with pytest.raises(AuthoredError, match="exactly one of them English"):
            check_versions(job, [dict(version, first=i) for i in firsts])
    check_versions(job, [dict(version, first=i) for i in others[:3] + english[:1]])  # one: accepted


def test_a_clarified_answer_without_its_option_is_refused():
    job = JOBS["b5-32-2"]
    versions = [{k: v for k, v in version.items() if k != "target"} for version in AUTHORED["b5-32-2"]]
    with pytest.raises(AuthoredError, match="options"):
        check_versions(job, versions)


def test_a_job_missing_its_versions_refuses_the_whole_batch(tmp_path):
    authored = tmp_path / "authored"
    authored.mkdir()
    (authored / "chunk-000.json").write_text(json.dumps({k: AUTHORED[k] for k in list(AUTHORED)[:5]}),
                                             encoding="utf-8")  # fmt: skip
    with pytest.raises(AuthoredError, match="missing"):
        replay(authored_dir=authored, out_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_a_line_near_a_held_out_question_drops_its_version(tmp_path):
    line = AUTHORED["b5-32-0"][0]["lines"][0]
    report = replay(out_dir=tmp_path, held_out=(line,))
    assert report["near test questions, dropped"] >= 1
    assert report["train"] + report["validation"] == 640 - report["near test questions, dropped"]
