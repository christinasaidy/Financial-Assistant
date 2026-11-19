"""Every stored example, rebuilt with today's prompt (batch 5, 2026-11-18).

Batches 1-4 were written before the prompt stated the user's gender and before the rule that a new question replaces
what it names. The model is trained on exactly what the app sends, so each stored example is read back into its
parts (`read_prompt`) and built again with the app's own `build_prompt`, the user's gender (`gender_of`), the
assistant's replies in the form for that gender (`for_gender`) and the user's own "I" words in their gender's form
(`question_for_gender`, 2026-11-19). Nothing else may change: `rerender` refuses an example whose prompt, rebuilt
from its parts without those swaps and without the two batch-5 lines, is not its old prompt.
"""

import copy
from dataclasses import dataclass
from datetime import date

from app.domain.assistant.prompt import GENDER_LINES, INSTRUCTIONS, Exchange, UserNames, build_prompt

from research.dataset.genders import for_gender, question_for_gender
from research.dataset.users import gender_of

NEW_RULE = ("\n- In a chat, what the new question says replaces the earlier item, shop, period or measure; what it "
            "leaves out\n  comes from the earlier question.")  # fmt: skip
_TODAY = "\n\nToday: "


class UnreadablePrompt(ValueError):
    """A stored prompt that is not in the form build_prompt writes."""


@dataclass(frozen=True)
class PromptParts:
    question: str
    names: UserNames
    today: date
    history: tuple[Exchange, ...]


def read_prompt(prompt: str) -> PromptParts:
    """The parts a prompt was built from (with or without the gender line)."""
    if _TODAY not in prompt:
        raise UnreadablePrompt("no Today line")
    lines = prompt.split(_TODAY, 1)[1].split("\n")
    try:
        today = date.fromisoformat(lines.pop(0).split(" ", 1)[0])
        if lines[0] in GENDER_LINES.values():
            lines.pop(0)
        names = UserNames(*(_names(lines.pop(0), label) for label in ("items", "vendors", "categories")))
        if lines.pop(0) != "":
            raise UnreadablePrompt("no blank line after the names")
        history = []
        if lines[0] == "Earlier in this chat:":
            lines.pop(0)
            while lines[0] != "":
                question, reply = lines.pop(0), lines.pop(0)
                if not question.startswith("Question: ") or not reply.startswith("Reply: "):
                    raise UnreadablePrompt(f"not an exchange: {question!r} / {reply!r}")
                history.append(Exchange(question[len("Question: "):], reply[len("Reply: "):]))
            lines.pop(0)
        question = lines.pop(0)
        if not question.startswith("Question: ") or lines != ["Reply:"]:
            raise UnreadablePrompt("the prompt does not end with the question and Reply:")
    except IndexError as exc:
        raise UnreadablePrompt("the prompt ends early") from exc
    return PromptParts(question[len("Question: "):], names, today, tuple(history))


def _names(line: str, label: str) -> list[str]:
    start = f"The user's {label}: "
    if not line.startswith(start):
        raise UnreadablePrompt(f"no {label} line: {line[:60]!r}")
    listed = line[len(start):]
    if listed == "(none yet)":
        return []
    if not (listed.startswith('"') and listed.endswith('"')):
        raise UnreadablePrompt(f"the {label} are not quoted")
    return listed[1:-1].split('", "')


def without_batch5_lines(prompt: str) -> str:
    """The prompt as batches 1-4 wrote it: no gender line and no new rule."""
    for line in GENDER_LINES.values():
        prompt = prompt.replace(f"\n{line}\n", "\n", 1)
    return prompt.replace(NEW_RULE, "", 1)


def rerender(example: dict) -> dict:
    """The example with today's prompt, the user's gender and replies in its form; labels gain "gender"."""
    labels = example["labels"]
    gender = gender_of(labels["user"])
    old_prompt, old_reply = example["messages"][0]["content"], example["messages"][1]["content"]
    parts = read_prompt(old_prompt)
    history = tuple(Exchange(question_for_gender(e.question, gender), for_gender(e.reply, gender, e.question))
                    for e in parts.history)  # fmt: skip
    prompt = build_prompt(question_for_gender(parts.question, gender), parts.names, parts.today, history,
                          gender=gender)  # fmt: skip

    unchanged = build_prompt(parts.question, parts.names, parts.today, parts.history, gender=gender)
    if without_batch5_lines(unchanged) != without_batch5_lines(old_prompt):
        raise UnreadablePrompt(f"rebuilding changed more than the batch-5 lines ({labels.get('spec')})")
    if INSTRUCTIONS not in prompt:
        raise UnreadablePrompt("the new prompt lacks the current instructions")

    rebuilt = copy.deepcopy(example)
    rebuilt["messages"][0]["content"] = prompt
    rebuilt["messages"][1]["content"] = for_gender(old_reply, gender, parts.question)
    rebuilt["labels"]["gender"] = gender.value
    return rebuilt
