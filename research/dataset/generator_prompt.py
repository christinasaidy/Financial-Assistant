"""What the question writer (Qwen) is sent for one thing to ask (decisions approved by the user on 2026-11-05/07).

It gets a plain description of the question (never the SQL), the names and spellings to use, today's date, and
up to twenty of the user's seed questions for that kind of question, in a new order each call, which the Arabizi
versions must imitate (decided 2026-11-08, after the first full run sounded nothing like the seeds). It returns JSON: six versions, three in Arabizi, one
mixing Arabizi and English, two in English. For CLARIFY and REPLY each version carries its own reply, in the
question's language; for a follow-up, each version also carries the earlier question it follows.
"""

import random
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from research.dataset.catalogue import Catalogue
from research.dataset.templates import Spec

SEED_FILE = Path(__file__).parent / "seed_questions.md"
LANGUAGES = ("arabizi", "arabizi", "arabizi", "mixed", "english", "english")
SEEDS_PER_CALL = 20  # the Arabizi imitates them (5, then 10, until 2026-11-08)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# The seed section each template learns its style from: new templates use the nearest one.
SEED_SECTION = {"T3g": "T3", "T11k": "T11", "T12k": "T12", "T18": "T15", "T19": "T17", "T20": "T17"}
VOCABULARY_SECTIONS = ("Money and receipt vocabulary", "Quantities and units", "Days and periods")


@dataclass(frozen=True)
class Seeds:
    questions: dict[str, tuple[str, ...]]  # section (T1 ... T17, F, C, U, R) -> the user's example questions
    vocabulary: tuple[str, ...]  # the money, unit and period lines of the word list, as written


def load_seeds(path: Path = SEED_FILE) -> Seeds:
    questions: dict[str, list[str]] = {}
    vocabulary: list[str] = []
    section: str | None = None
    word_section: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            heading = line[3:]
            section = heading.split()[0] if heading != "Arabizi words" else None
            word_section = None
            continue
        if section is None and line in VOCABULARY_SECTIONS + ("Food and drinks", "Household and personal care",
                                                              "Clothes, electronics, and other items",
                                                              "Category wording and related search terms",
                                                              "Tobacco product names"):  # fmt: skip
            word_section = line
            continue
        if section and re.match(r"^\d+\.\s+\S", line):
            questions.setdefault(section, []).append(re.sub(r"^\d+\.\s+", "", line))
        elif word_section in VOCABULARY_SECTIONS and line.startswith("- "):
            vocabulary.append(line[2:].rstrip(", "))
    return Seeds({name: tuple(found) for name, found in questions.items()}, tuple(vocabulary))


def seed_section(spec: Spec) -> str:
    if spec.base is not None:
        return "F"
    return SEED_SECTION.get(spec.template, spec.template if spec.template.startswith("T") else spec.template[0])


def build_generator_prompt(spec: Spec, catalogue: Catalogue, seeds: Seeds, today: date, rng: random.Random) -> str:
    examples = list(seeds.questions.get(seed_section(spec), ()))
    rng.shuffle(examples)
    parts = [
        ("You write the questions people in Lebanon type into an expense app's assistant, about their own shop "
         "receipts. Write like a real person texting: short or long, casual, sometimes with a reason or a joke."),
        "",
    ]
    if spec.base is not None:
        parts += [f"First comes an earlier question: {spec.base.description}",
                  f"Then the user sends a short follow-up that only makes sense after it: {spec.description}",
                  ("The follow-up must not repeat what stays the same (it leaves out the item, shop or period it "
                   "does not change).")]  # fmt: skip
    else:
        parts.append(f"The question asks exactly this: {spec.description}")
    must = _must_mention(spec)
    if must:
        parts.append("It must mention " + "; and ".join(must) + ".")
    parts.append(f"Today is {WEEKDAYS[today.weekday()]} {today.isoformat()}. Never write a year for a month.")
    if spec.reply_hint and spec.kind == "clarify":
        parts.append(f"The assistant cannot answer it and asks back. Its reply: {spec.reply_hint}")
    elif spec.reply_hint:
        parts.append(f"The assistant's reply: {spec.reply_hint}")
    parts += [
        "",
        "Write 6 versions, each a different way of asking it:",
        "- 3 in Lebanese Arabizi (Lebanese Arabic in Latin letters, with 2 3 5 7 for the Arabic sounds);",
        "- 1 mixing Arabizi and English in the same sentence;",
        "- 2 in English.",
        # Imitate, not just be inspired by, the user's examples (approved by the user on 2026-11-08).
        ("Write the 3 Arabizi versions, and the Arabizi words of the mixed one, in the same style as the examples "
         "below: reuse their words, spellings and sentence shapes, and change only what this question is about. "
         "The English versions can be worded freely. Use only Latin letters, never Arabic script."),
        ("Write the way people in Lebanon text: 2 for the qaf and hamza, never q (abel, 2abel, ta2sod); Lebanese "
         "words, not Gulf or formal ones (shu, adde, hayda, mnih, not eish, elay, hatha); 7a2 means price."),
        "",
        "Examples of how people ask this kind of question:",
        *[f"- {example}" for example in examples[:SEEDS_PER_CALL]],
        "",
        "Reply with JSON only, in this form:",
        _json_form(spec),
    ]
    return "\n".join(parts)


def _must_mention(spec: Spec) -> list[str]:
    """Each group of words the question must use one of, said plainly."""
    phrases = []
    for words in spec.mentions:
        main, *others = words
        phrases.append(f'"{main}"' + (f" (or one of: {', '.join(others)})" if others else ""))
    return phrases


def _json_form(spec: Spec) -> str:
    fields = '"language": "arabizi", '
    if spec.base is not None:
        fields += '"first": "<the earlier question>", '
    fields += '"question": "<the question>"'
    if spec.kind in ("clarify", "reply"):
        start = "CLARIFY" if spec.kind == "clarify" else "REPLY"
        fields += f', "reply": "{start}: <the reply, in the language of the question>"'
    languages = ", ".join(f'"{language}"' for language in dict.fromkeys(LANGUAGES))
    return f'{{"versions": [{{{fields}}}, ...]}}  (6 versions; language is one of {languages})'


def versions_schema(spec: Spec) -> dict:
    """The exact JSON the writer must return, for vLLM's guided decoding: six versions, each with a known language,
    the question, and the fields this kind of question needs (the earlier question of a follow-up, the reply of a
    CLARIFY or REPLY). Nothing else is allowed, so no paid call is lost to a malformed reply."""
    properties: dict = {"language": {"type": "string", "enum": list(dict.fromkeys(LANGUAGES))}}
    required = ["language"]
    if spec.base is not None:
        properties["first"] = {"type": "string"}
        required.append("first")
    properties["question"] = {"type": "string"}
    required.append("question")
    if spec.kind in ("clarify", "reply"):
        properties["reply"] = {"type": "string"}
        required.append("reply")
    version = {"type": "object", "properties": properties, "required": required, "additionalProperties": False}
    return {"type": "object", "additionalProperties": False, "required": ["versions"], "properties": {
        "versions": {"type": "array", "minItems": len(LANGUAGES), "maxItems": len(LANGUAGES), "items": version}}}
