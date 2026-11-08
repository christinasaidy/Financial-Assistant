"""The generator prompt, the checks, the writers and the build (decisions approved by the user on 2026-11-05/07).
Do not change an expected value to make a test pass."""

import json
import random
import tempfile
from datetime import date
from pathlib import Path

import httpx
import pytest
from app.domain.assistant.prompt import INSTRUCTIONS
from sqlalchemy import create_engine, text

from research.dataset import build as build_module
from research.dataset.catalogue import load_catalogue
from research.dataset.checks import (
    UnreadableReply,
    Version,
    contains,
    near_duplicate,
    problems,
    read_versions,
)
from research.dataset.generator_prompt import (
    LANGUAGES,
    build_generator_prompt,
    load_seeds,
    seed_section,
    versions_schema,
)
from research.dataset.templates import Spec, UserData, make_specs
from research.dataset.users import make_user
from research.dataset.wiring import QwenWriter, StandInWriter

CATALOGUE = load_catalogue()
SEEDS = load_seeds()
TODAY = date(2027, 2, 10)


def specs_of(number, count=40):
    data = UserData(make_user(CATALOGUE, number), CATALOGUE)
    return data, make_specs(data, count, f"test/{number}")


def first(template, numbers=range(1, 31)):
    for number in numbers:
        data, specs = specs_of(number)
        found = next((s for s in specs if s.template == template), None)
        if found:
            return data, found
    raise AssertionError(f"no {template} spec")


# --- The seeds and the generator prompt ---


def test_every_kind_of_question_has_seeds_and_the_money_words_are_read():
    for section in [f"T{n}" for n in range(1, 18)] + ["F", "C", "U", "R"]:
        assert len(SEEDS.questions[section]) >= 10, section
    keys = {line.split(":")[0] for line in SEEDS.vocabulary}
    assert {"money", "how much", "I spent", "kilo", "week", "Friday"} <= keys


def test_new_templates_learn_from_the_nearest_seeds():
    assert [seed_section(Spec(t, "sql", "", "")) for t in ("T3g", "T11k", "T12k", "T18", "T19", "T20", "T9")] == [
        "T3", "T11", "T12", "T15", "T17", "T17", "T9"]
    assert seed_section(Spec("C4", "clarify", "", None)) == "C"
    assert seed_section(Spec("F1", "sql", "", "", base=Spec("T9", "sql", "", ""))) == "F"


def test_the_prompt_describes_the_question_and_never_shows_the_sql():
    data, spec = first("T9")
    prompt = build_generator_prompt(spec, CATALOGUE, SEEDS, data.today, random.Random(1))
    assert spec.description in prompt and "SELECT" not in prompt and spec.target not in prompt
    item = CATALOGUE.item(spec.labels["item"])
    assert f'"{item.name}"' in prompt and all(word in prompt for word in item.words)
    assert "3 in Lebanese Arabizi" in prompt and "1 mixing Arabizi and English" in prompt and "2 in English" in prompt
    examples = [line[2:] for line in prompt.split("Examples of how people ask this kind of question:\n")[1]
                .split("\n\n")[0].splitlines()]  # fmt: skip
    assert len(examples) == 10 and set(examples) <= set(SEEDS.questions["T9"])  # 10 seeds (changed 2026-11-08)


def test_the_seeds_shown_change_from_call_to_call():
    data, spec = first("T9")
    rng = random.Random(1)
    prompts = {build_generator_prompt(spec, CATALOGUE, SEEDS, data.today, rng) for _ in range(5)}
    assert len(prompts) == 5


def test_clarify_and_follow_ups_ask_for_their_extra_fields():
    data, clarify = first("C1")
    prompt = build_generator_prompt(clarify, CATALOGUE, SEEDS, data.today, random.Random(1))
    assert '"reply": "CLARIFY: ' in prompt and clarify.reply_hint in prompt
    data, follow = first("F3")
    prompt = build_generator_prompt(follow, CATALOGUE, SEEDS, data.today, random.Random(1))
    assert '"first": "<the earlier question>"' in prompt and follow.base.description in prompt


def test_weekday_spellings_only_when_the_question_names_that_day():
    friday = Spec("T9", "sql", "How much the user spent on bread, on Friday (the most recent Friday).", "")
    week = Spec("T9", "sql", "How much the user spent on bread, this week (Monday to Sunday).", "")
    assert "- Friday:" in build_generator_prompt(friday, CATALOGUE, SEEDS, TODAY, random.Random(1))
    assert "- Monday:" not in build_generator_prompt(week, CATALOGUE, SEEDS, TODAY, random.Random(1))


# --- Reading the reply and the checks ---


def test_the_reply_is_read_with_or_without_a_json_fence():
    reply = '{"versions": [{"language": "arabizi", "question": "adde sarafet 3al may?"}]}'
    assert read_versions(reply) == read_versions(f"```json\n{reply}\n```") == [
        Version("arabizi", "adde sarafet 3al may?")]
    for bad in ("not json", '{"questions": []}', '{"versions": [{"language": "english"}]}'):
        with pytest.raises(UnreadableReply):
            read_versions(bad)


def spec_with(mentions, template="T9", kind="sql", labels=None, base=None):
    return Spec(template, kind, "", "SELECT 1", mentions, labels=labels or {"item": "water"}, base=base)


def test_a_question_must_contain_one_word_of_each_group_as_a_whole_word():
    spec = spec_with((("water", "may", "mayy"), ("this month", "hal shaher")))
    assert problems(Version("arabizi", "adde sarafet 3al may hal shaher?"), spec, CATALOGUE) == []
    assert problems(Version("english", "How much on water this month?"), spec, CATALOGUE) == []
    assert problems(Version("arabizi", "adde sarafet 3al mayonnaise hal shaher?"), spec, CATALOGUE) == [
        "does not mention any of: water, may, mayy"]  # "may" inside a longer word does not count
    assert contains("ab", "ab") and not contains("abou jihad", "ab")
    assert contains("adde sarafet bel $", "$") and not contains("adde sarafet bel dollar", "$")


def test_a_t9_question_naming_its_items_brand_is_dropped():
    spec = spec_with((("water", "may"),))
    assert problems(Version("english", "How much on Rim water?"), spec, CATALOGUE) == [
        "a T9 question names a brand: rim"]
    tissues = spec_with((("tissues", "kleenex"),), labels={"item": "tissues"})
    assert problems(Version("english", "How much on tissues? fine, all of them"), tissues, CATALOGUE) == [
        "a T9 question names a brand: fine"]  # its own brand, even when it reads like a word
    other = spec_with((("bread",),), labels={"item": "bread"})
    assert problems(Version("english", "fine, how much on bread?"), other, CATALOGUE) == []  # not bread's brand


def test_arabic_script_blank_and_long_questions_are_dropped():
    spec = spec_with(())
    assert problems(Version("arabizi", "adde sarafet 3al مي"), spec, CATALOGUE) == ["Arabic script"]
    assert problems(Version("english", ""), spec, CATALOGUE) == ["blank or too long"]
    assert problems(Version("english", "x" * 301), spec, CATALOGUE) == ["blank or too long"]
    assert problems(Version("french", "combien?"), spec, CATALOGUE) == ["unknown language 'french'"]


def test_replies_must_start_right_and_a_reply_never_states_a_number():
    clarify = spec_with((), kind="clarify")
    assert problems(Version("english", "the last one?", "CLARIFY: Which one?"), clarify, CATALOGUE) == []
    assert problems(Version("english", "the last one?", "Which one?"), clarify, CATALOGUE) == [
        "the reply does not start with CLARIFY:"]
    reply = spec_with((), kind="reply")
    assert problems(Version("english", "hi", "REPLY: Hi! Ask me about your receipts."), reply, CATALOGUE) == []
    assert problems(Version("english", "hi", "REPLY: Hi! You spent 20 dollars."), reply, CATALOGUE) == [
        "a REPLY states a number"]


def test_a_follow_up_needs_its_earlier_question():
    follow = spec_with((), template="F1", base=spec_with(()))
    assert problems(Version("english", "and last month?"), follow, CATALOGUE) == [
        "a follow-up without its earlier question"]
    assert problems(Version("english", "and last month?", first="How much on water?"), follow, CATALOGUE) == []


def test_near_duplicates_of_test_questions_are_dropped():
    tests = ("How much did I spend on laban?",)
    assert near_duplicate("how much did i spend on laban", tests) == tests[0]
    assert near_duplicate("adde sarafet 3al laban hal shaher?", tests) is None
    found = problems(Version("english", "How much did I spend on laban??"), spec_with(()), CATALOGUE, tests)
    assert found == ["near-duplicate of a test question: How much did I spend on laban?"]


# --- The writers ---


def test_the_stand_in_writes_six_versions_that_pass_the_checks():
    for number in (1, 15, 30):
        _, specs = specs_of(number)
        for spec in specs:
            versions = read_versions(StandInWriter().write(spec, "", seed=0))
            assert [v.language for v in versions] == list(LANGUAGES)
            assert all(problems(v, spec, CATALOGUE) == [] for v in versions), spec.template


def test_qwen_is_called_with_thinking_off_qwens_sampling_the_json_schema_and_a_seed():
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"versions": []}'}}]})

    writer = QwenWriter("http://pod/v1", "key-123", "Qwen/Qwen3.8-27B", client=httpx.Client(
        transport=httpx.MockTransport(handler)))  # fmt: skip
    assert writer.write(spec_with(()), "the prompt", seed=4017) == '{"versions": []}'
    body = json.loads(sent[0].content)
    assert str(sent[0].url) == "http://pod/v1/chat/completions"
    assert sent[0].headers["Authorization"] == "Bearer key-123"
    # Qwen's recommended non-thinking sampling, and the exact JSON shape enforced (decided 2026-11-08)
    assert body == {"model": "Qwen/Qwen3.8-27B", "messages": [{"role": "user", "content": "the prompt"}],
                    "temperature": 0.7, "top_p": 0.8, "top_k": 20, "seed": 4017,
                    "response_format": {"type": "json_schema", "json_schema": {
                        "name": "versions", "strict": True, "schema": versions_schema(spec_with(()))}},
                    "chat_template_kwargs": {"enable_thinking": False}}  # fmt: skip


def test_qwen_is_tried_once_more_after_a_temporary_failure():
    answers = [httpx.Response(503), httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})]
    writer = QwenWriter("http://pod/v1", "k", "m", client=httpx.Client(
        transport=httpx.MockTransport(lambda request: answers.pop(0))), wait=0)  # fmt: skip
    assert writer.write(spec_with(()), "p", seed=1) == "ok"
    failing = QwenWriter("http://pod/v1", "k", "m", client=httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))), wait=0)  # fmt: skip
    with pytest.raises(httpx.HTTPStatusError):
        failing.write(spec_with(()), "p", seed=1)


# --- The build ---


def test_a_real_model_needs_yes_before_any_call(capsys, monkeypatch):
    monkeypatch.setattr(build_module, "build", lambda *a, **k: pytest.fail("no build without --yes"))
    assert build_module.main(["--model", "Qwen/Qwen3.8-27B", "--base-url", "http://pod/v1"]) == 1
    assert "Add --yes to start" in capsys.readouterr().out


def test_the_build_writes_chat_examples_with_the_apps_own_prompt_and_removes_the_user(settings):
    out, raw = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    summary = build_module.build(StandInWriter(), [28], out, raw, specs_per_user=12)
    examples = [json.loads(line) for line in (out / "validation.jsonl").read_text(encoding="utf-8").splitlines()]
    assert (out / "train.jsonl").read_text(encoding="utf-8") == ""  # user 28 is a validation user
    assert len(examples) == summary.examples["validation"] > 0
    for example in examples:
        user, assistant = example["messages"]
        assert user["role"] == "user" and user["content"].startswith(INSTRUCTIONS)
        assert user["content"].endswith("\nReply:") and assistant["role"] == "assistant"
        labels = example["labels"]
        assert labels["user"] == 28 and labels["split"] == "validation"
        if labels["kind"] in ("sql", "follow_up"):
            assert assistant["content"].startswith("SELECT") and "CAST(" not in assistant["content"]
        if labels["kind"] == "follow_up":
            assert "Earlier in this chat:" in user["content"]
        if labels["kind"] == "unsupported":
            assert assistant["content"] == "UNSUPPORTED"
    replies = (raw / "generator_replies.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(replies) == 12
    with create_engine(settings.database_url).connect() as conn:
        left = conn.execute(text("SELECT COUNT(*) FROM users WHERE email LIKE 'dataset-28-%'")).scalar_one()
    assert left == 0


def test_the_json_schema_asks_for_exactly_six_versions_with_the_fields_each_kind_needs():
    sql = versions_schema(spec_with(()))
    assert (sql["properties"]["versions"]["minItems"], sql["properties"]["versions"]["maxItems"]) == (6, 6)
    item = sql["properties"]["versions"]["items"]
    assert item["required"] == ["language", "question"] and item["additionalProperties"] is False
    assert item["properties"]["language"]["enum"] == ["arabizi", "mixed", "english"]
    clarify = versions_schema(spec_with((), kind="clarify"))["properties"]["versions"]["items"]
    assert clarify["required"] == ["language", "question", "reply"]
    follow = versions_schema(spec_with((), template="F1", base=spec_with(())))["properties"]["versions"]["items"]
    assert follow["required"] == ["language", "first", "question"]
    for spec in specs_of(4)[1]:  # the stand-in's replies fit the schema of their spec
        fields = set(versions_schema(spec)["properties"]["versions"]["items"]["properties"])
        for version in json.loads(StandInWriter().write(spec, "", seed=0))["versions"]:
            assert set(version) <= fields and set(versions_schema(spec)["properties"]["versions"]["items"][
                "required"]) <= set(version)  # fmt: skip
