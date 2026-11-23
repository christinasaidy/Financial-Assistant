"""Phase 4 in the Standard loop, with a scripted model (no database, no provider): the skills in the fixed
instructions, the memories and reply forms in the turn's context, the Arabizi checks with one retry, and "Saved" only
after a memory tool succeeded (AC-11, plus section 13A of the handoff). The model's replies are set by each test."""

from datetime import UTC, date, datetime

from app.application.assistant.dtos import TextPart, TurnRequest
from app.application.assistant.standard_prompt import SYSTEM_PROMPT
from app.application.assistant.standard_skills import BUDGETS, PRICE_COMPARISONS, Skill, instructions
from app.application.assistant.standard_tools import SPECS, ToolOutcome
from app.application.assistant.standard_workflow import StandardWorkflow
from app.domain.assistant import answer as answers
from app.domain.assistant.arabizi import Address, ArabiziWords
from app.domain.assistant.conversation import AnswerKind
from app.domain.assistant.memory import Memory, MemoryKind
from app.domain.assistant.names import NameKind
from tests.fakes import ScriptedChatModel, calls, says

TODAY = date(2026, 11, 23)
WHEN = datetime(2026, 11, 1, tzinfo=UTC)
ARABIZI = Skill("lebanese_arabizi", "arabizi-pack-test", "her rulings")
WORDS = ArabiziWords(frozenset({"sakin", "li fet"}), frozenset({"sarafet", "baddak"}), frozenset({"sarafte", "baddik"}))
SHORT = Memory(3, MemoryKind.PREFERENCE, "Keep your answers short.", WHEN, WHEN)
ZWZ = Memory(5, MemoryKind.ALIAS, '"zwz" means the shop "Zaatar w Zeit"', WHEN, WHEN, "zwz", NameKind.VENDOR,
             "Zaatar w Zeit", 12)  # fmt: skip


class StubTools:
    specs = SPECS

    def __init__(self, outcome=None):
        self.outcome = outcome or ToolOutcome('{"saved": true}', False, (), (), None, {}, memory_written=True)
        self.contexts = []

    def run(self, user_id, call, context):
        self.contexts.append(context)
        return self.outcome


def _request(question="hi", address=Address.NEUTRAL, memories=(), history=()) -> TurnRequest:
    return TurnRequest(11, 5, 3, question, tuple(history), 0, 41, address, tuple(memories))


def _workflow(model, tools=None, skills=(ARABIZI,), words=WORDS):
    ticks = iter(range(10_000))
    return StandardWorkflow(model, tools or StubTools(), lambda: TODAY, clock=lambda: next(ticks) * 0.001,
                            skills=skills, arabizi_words=words)  # fmt: skip


def test_every_skill_is_in_the_fixed_instructions_in_a_fixed_order_and_its_version_is_saved():
    model = ScriptedChatModel(says("Hi!"))
    answer = _workflow(model, skills=(ARABIZI, BUDGETS, PRICE_COMPARISONS)).answer(_request())
    system = model.requests[0].system
    assert system == instructions(SYSTEM_PROMPT, [PRICE_COMPARISONS, BUDGETS, ARABIZI])
    assert system.index("## Skill: price_comparisons") < system.index("## Skill: budgets") < system.index(
        "## Skill: lebanese_arabizi")
    assert "Today is" not in system and "Saved memories" not in system  # nothing per user or day in the cached part
    assert answer.execution["skills"] == {"lebanese_arabizi": "arabizi-pack-test", "budgets": BUDGETS.version,
                                          "price_comparisons": PRICE_COMPARISONS.version}  # fmt: skip


def test_the_memories_and_reply_forms_go_with_the_question_only():
    model = ScriptedChatModel(says("Hi!"))
    _workflow(model).answer(_request(address=Address.WOMAN, memories=[SHORT, ZWZ]))
    context = model.requests[0].messages[-1].parts[0].text
    assert "Arabizi reply forms: the woman forms." in context
    assert "- memory 3 (preference): Keep your answers short." in context
    assert '- memory 5 (alias): "zwz" means the shop "Zaatar w Zeit"' in context


def test_a_memory_tool_gets_the_turns_conversation_and_question_never_the_models():
    tools = StubTools()
    model = ScriptedChatModel(calls(("t", "save_memory", {"kind": "preference", "text": "Keep it short", "alias": "",
                                                          "target_kind": "", "target_name": ""})),
                              says("Saved: I'll keep my answers short."))  # fmt: skip
    answer = _workflow(model, tools).answer(_request("remember to keep it short"))
    assert (tools.contexts[0].conversation_id, tools.contexts[0].question_message_id) == (5, 41)
    assert answer.content == "Saved: I'll keep my answers short."
    assert answer.details.kind is AnswerKind.REPLY  # a memory is not data: no "based on receipts"


def test_saying_saved_without_a_successful_memory_tool_is_sent_back_then_refused():
    model = ScriptedChatModel(says("Saved! I'll remember that."), says("I've saved it."))
    answer = _workflow(model).answer(_request("remember that zwz is zaatar w zeit"))
    assert (answer.details.kind, answer.content) == (AnswerKind.ERROR, answers.FAILURE)
    assert "no memory tool succeeded" in model.requests[1].messages[-1].parts[0].text


def test_saying_saved_after_a_failed_memory_tool_is_refused_too():
    failed = ToolOutcome('{"error": "too many"}', True, (), (), None, {}, memory_written=True)
    model = ScriptedChatModel(calls(("t", "save_memory", {})), says("Saved it."), says("I couldn't save that."))
    answer = _workflow(model, StubTools(failed)).answer(_request("remember this"))
    assert answer.content == "I couldn't save that."


def test_a_rejected_spelling_is_sent_back_once_with_the_finding():
    model = ScriptedChatModel(says("Sakin, ma fi shi."), says("Ma fi shi."))
    answer = _workflow(model).answer(_request("shu jebet?"))
    assert answer.content == "Ma fi shi."
    fix = model.requests[1].messages[-1].parts[0].text
    assert "rejected spelling sakin" in fix and "lebanese_arabizi" in fix
    assert answer.execution["checks"] == ["rejected spelling sakin (follow the lebanese_arabizi skill)"]


def test_an_answer_breaking_the_rulings_twice_becomes_the_fixed_message():
    model = ScriptedChatModel(says("li fet"), says("li fet bas"))
    answer = _workflow(model).answer(_request("shu?"))
    assert (answer.details.kind, answer.content) == (AnswerKind.ERROR, answers.FAILURE)


def test_words_of_the_other_gender_are_refused_and_neutral_allows_neither():
    model = ScriptedChatModel(says("Shu baddak?"), says("Shu el ma2soud?"))
    answer = _workflow(model).answer(_request("eh", address=Address.WOMAN))
    assert answer.content == "Shu el ma2soud?"
    assert "words not for a woman reader: baddak" in model.requests[1].messages[-1].parts[0].text

    for address, reply in [(Address.MAN, "Shu baddak?"), (Address.WOMAN, "Shu baddik?")]:
        assert _workflow(ScriptedChatModel(says(reply))).answer(_request("eh", address=address)).content == reply
    model = ScriptedChatModel(says("Shu baddik?"), says("Shu el ma2soud?"))
    _workflow(model).answer(_request("eh", address=Address.NEUTRAL))
    assert "gender is not given" in model.requests[1].messages[-1].parts[0].text


def test_the_users_own_words_and_names_from_the_data_are_never_held_against_the_answer():
    # The user wrote "sakin" themself; a shop in a tool result is called "Li Fet".
    shop = ToolOutcome('{"rows": [["Li Fet"]]}', False, (), (), True, {})
    model = ScriptedChatModel(calls(("t", "query_receipts", {"sql": "SELECT vendor FROM receipts"})),
                              says("Sakin: your shop is Li Fet."))  # fmt: skip
    answer = _workflow(model, StubTools(shop)).answer(_request("sakin, which shop?"))
    assert answer.content == "Sakin: your shop is Li Fet."


def test_without_skills_the_instructions_are_the_base_prompt():
    model = ScriptedChatModel(says("Hi!"))
    _workflow(model, skills=(), words=None).answer(_request())
    assert model.requests[0].system == SYSTEM_PROMPT
    assert model.requests[0].messages[-1].parts[-1] == TextPart("hi")
