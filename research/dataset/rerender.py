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

from research.dataset.fixes import fixed_reply
from research.dataset.genders import for_gender, question_for_gender
from research.dataset.users import gender_of

NEW_RULE = ("\n- In a chat, what the new question says replaces the earlier item, shop, period or measure; what it "
            "leaves out\n  comes from the earlier question.")  # fmt: skip
_TODAY = "\n\nToday: "
# Rules changed in batch 5 (approved by Christina on 2026-11-19): (as batches 1-4 wrote it, as it reads now).
CHANGED_RULES = ((
    '- A price change ("did the price go up, by how much, in percent"): the latest purchase against the one before\n'
    "  it, per kilo or litre when it has a size in g or ml, otherwise by unit price; return both prices, their dates\n"
    "  and the percent change. \"The average price went down\" compares this month's average with last month's.",
    '- A price change ("did the price go up, by how much, in percent"): the latest purchase against the one before\n'
    "  it in the same currency, per kilo or litre when it has a size in g or ml, otherwise by unit price; return the\n"
    "  currency, both prices, their dates and the percent change. \"The average price went down\" compares this month's\n"
    "  average with last month's."), (
    '- "The shop I went to most" counts visits, COUNT(DISTINCT receipt_id) per vendor, most first; "the shop I spent\n'
    '  most at" adds up money.',
    '- "The shop I went to most" counts visits, COUNT(DISTINCT receipt_id) per vendor, most first; "the shop I spent\n'
    "  most at\" adds up money. Bills and subscriptions are not visits: leave out category = 'Utilities' and the\n"
    "  user's Netflix, Shahid, Anghami or Spotify, e.g. FROM category_spending WHERE category <> 'Utilities' AND\n"
    "  vendor NOT IN ('Anghami')."),
)  # fmt: skip


# Part 4's rules (approved by Christina on 2026-11-22), after "List what I bought / spent".
PART4_RULES = """
- "Which shops / restaurants did I go to" (aya mata3em, 3edele el mahalet): every vendor with its total, most first.
  "The most" (aktar shi) is the top one only. "The places I went to most" (top matare7): every vendor by visits.
- "What did I buy at <shop>": that vendor's purchases, with receipt_date, item_name, currency and line_total, by date.
- "Which items did I spend the most on": items by their USD total, most first; 3 when no number is given.
- The priciest or cheapest things I bought (aghla / arkhas osas, ghrad): items by price per unit in USD,
  MAX or MIN(line_total_usd / quantity) per item_name; 1 when one is asked, otherwise the number asked or 3.
- "The biggest receipt" (aghla fatoura): the receipt with the highest total_usd, with its date, vendor and total.
- "How much do I usually pay per visit at <shop>": the average receipt total per currency, with the number of visits.
- "How many different shops / places": COUNT(DISTINCT vendor), leaving out bills and subscriptions as for visits.
- "My last receipt from <shop>" (ekher fatoura): the latest receipt from that vendor, with its date and total."""
PART4_PERIOD_RULE = """
  "The end of the month" is its 21st to its last day: this month (bi ekher heda el shaher), a named month
  (b ekher shaher teshreen) or the one just asked about (bi ekher hedek el shaher); reply CLARIFY for
  "bi ekher el shaher" alone."""


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
    """The prompt as batches 1-4 wrote it: no gender line, no new rules, the changed rules as they were."""
    for line in GENDER_LINES.values():
        prompt = prompt.replace(f"\n{line}\n", "\n", 1)
    for before, now in CHANGED_RULES:
        prompt = prompt.replace(now, before, 1)
    return prompt.replace(NEW_RULE, "", 1).replace(PART4_RULES, "", 1).replace(PART4_PERIOD_RULE, "", 1)


def rerender(example: dict) -> dict:
    """The example with today's prompt, the user's gender and replies in its form; labels gain "gender"."""
    labels = example["labels"]
    gender = gender_of(labels["user"])
    old_prompt, old_reply = example["messages"][0]["content"], example["messages"][1]["content"]
    parts = read_prompt(old_prompt)
    history = tuple(Exchange(question_for_gender(e.question, gender), for_gender(fixed_reply(e.reply, parts.names.vendors), gender, e.question))
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
    rebuilt["messages"][1]["content"] = for_gender(fixed_reply(old_reply, parts.names.vendors), gender, parts.question)
    rebuilt["labels"]["gender"] = gender.value
    return rebuilt
