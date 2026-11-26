"""Batch 5 part 2: small talk (decided with Christina on 2026-11-20; agent_documentation/PROGRESS.md).

    python -m research.dataset.smalltalk   # -> data/batch5/smalltalk_{train,validation}.jsonl

Every stored small-talk example of batches 1-4 (templates R1-R5) used to get one fixed reply whatever was said
("hahaha, fie se3dak b shi tene?" to "kifak?"). Here each is rebuilt:

- its question is sorted into a kind (raw/batch5/smalltalk/kinds.json, her review of smalltalk_sorted_review.md) and
  gets a reply of that kind, picked by the question so the replies rotate; Arabizi and mixed replies are the man's form
  of genders.SMALLTALK (table F), which the mix turns into the user's form; English ones come from ENGLISH, or stay
  as stored for the kinds without an English set;
- her edits to the questions (raw/batch5/smalltalk/edits.json) are applied example by example: a list gives each
  occurrence its own text (None keeps it), as for shlonak and "ma kent metwa23a";
- new questions (new.json: bye, how are you, who are you, complaints, not feeling well, and her 4 additions) go on a
  stored small-talk example's user, of the question's gender when it has one;
- greeting versions (greetings.json): a greeting in front of a stored, approved question; they keep its SQL.

The mix then takes these instead of the stored R1-R5 examples. Nothing is written unless every kind, edit and
version is accounted for and every line passes its checks; a line near a test question is dropped and counted.
"""

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from app.domain.assistant.prompt import build_prompt

from research.dataset import answers_build, build, words
from research.dataset.checks import _ARABIC, _NUMBER, Version, near_duplicate, problems
from research.dataset.genders import FORMS, SMALLTALK, Forms
from research.dataset.rerender import read_prompt
from research.dataset.users import gender_of

RAW_DIR = build.RAW_DIR / "batch5" / "smalltalk"
DATA_DIR = build.DATA_DIR / "batch5"
SOURCES = ("{split}.jsonl", "batch2/{split}.jsonl", "batch2/extras_{split}.jsonl", "batch3/{split}.jsonl",
           "batch4/{split}.jsonl")  # fmt: skip
TEMPLATES = ("R1", "R2", "R3", "R4", "R5")
_HERE = next(f for f in FORMS if f.man == "REPLY: eh hon, fiye se3dak?")  # table B #12

# Each kind's replies, by their number in table F (the review file); "are you there" also takes table B #12.
REPLIES: dict[str, tuple[Forms, ...]] = {
    "greeting": tuple(SMALLTALK[n] for n in (1, 2, 4, 5, 6)),
    "greeting (sabah)": (SMALLTALK[3],),  # sabah el kheir -> sabah el nour only
    "greeting (bonjour)": (SMALLTALK[4],),  # bonjour -> bonjour only
    "are you there": (_HERE, SMALLTALK[6]),
    "how are you": tuple(SMALLTALK[n] for n in range(7, 12)),
    "thanks": tuple(SMALLTALK[n] for n in range(12, 19)),
    "acknowledgement": (SMALLTALK[15], SMALLTALK[17]),  # the thanks that offer more help
    "what can you do": tuple(SMALLTALK[n] for n in range(19, 23)),
    "joke": (SMALLTALK[23], SMALLTALK[24]),
    "surprise": (SMALLTALK[25], SMALLTALK[26]),
    "complaint": (SMALLTALK[27], SMALLTALK[28]),
    "good wish": (SMALLTALK[30],),  # nharak sa3id takes #29 (WISH_29)
    "compliment": (SMALLTALK[30],),
    "bye": tuple(SMALLTALK[n] for n in range(31, 36)),
    "who are you": tuple(SMALLTALK[n] for n in range(36, 39)),
    "not well": tuple(SMALLTALK[n] for n in range(39, 42)),
}
WISH_29 = re.compile(r"\bnhar(ak|ik)\b", re.IGNORECASE)
ENGLISH = {  # the review file's English replies; a kind missing here keeps its stored English reply
    "greeting": ("Hi! How can I help with your receipts?", "Hello! What would you like to know about your spending?"),
    "greeting (sabah)": ("Good morning! What can I look up for you?",),
    "how are you": ("I'm good, thanks! What can I help you with?",
                    "Doing well, thanks for asking! Anything about your receipts?"),
    "thanks": ("You're welcome!", "Anytime!", "Glad I could help!", "My pleasure!"),
    "acknowledgement": ("Glad I could help!", "Anytime!"),
    "what can you do": ("I answer questions about your own receipts: totals, categories, shops, items, prices and "
                        "comparisons.", "I can tell you how much you spent, on what and where, and compare prices "
                        "between shops, all from your receipts."),
    "joke": ("Ha! Anything else I can look up?",),
    "surprise": ("Ha! Anything else I can look up?", "Glad that helped! Anything else?"),
    "complaint": ("I hear you, prices are high! Want to see where most of your money went?",),
    "good wish": ("Thanks, you too! Anything I can help with?",),
    "bye": ("Bye! I'm here whenever you need me.", "Take care! Come back anytime."),
    "who are you": ("I'm Fatourati, I answer questions about your own receipts.",
                    "I'm an assistant that answers questions about your spending from your receipts."),
    "not well": ("Sorry to hear that, I hope things get better. Anything I can help with?",),
}  # fmt: skip
NEW_TEMPLATES = {"bye": "R5", "how are you": "R4", "who are you": "R3", "complaint": "R4", "not well": "R4",
                 "thanks": "R2", "what can you do": "R3"}  # fmt: skip


# Kept although near a test question: Christina's decision (2026-11-20, "the most common greeting ever"). The test
# set's greeting is then no longer unseen; every other line near a test question is still dropped.
NEAR_TEST_ALLOWED = frozenset({"hi kifak", "hi kifak?", "hi kifik"})


class SmalltalkError(ValueError):
    """A stored question, edit or new line that does not match what was approved, or fails a check."""


def _pick(options: tuple, key: str):
    return options[int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) % len(options)]


def reply_for(kind: str, language: str, question: str, key: str, stored: str | None = None) -> str:
    """The reply of the kind: Arabizi and mixed get table F's man form (the mix gives each user theirs), English
    the review's English, or the stored English reply for a kind with no English set."""
    if kind not in REPLIES:
        raise SmalltalkError(f"no replies for the kind {kind!r}")
    if language == "english":
        if kind not in ENGLISH:
            if stored is None:
                raise SmalltalkError(f"{question!r}: no English reply for {kind!r}")
            return stored
        return "REPLY: " + _pick(ENGLISH[kind], key)
    if kind == "good wish" and WISH_29.search(question):
        return SMALLTALK[29].man
    return _pick(REPLIES[kind], key).man


def _question(row: dict) -> str:
    return read_prompt(row["messages"][0]["content"]).question


def stored_rows(data_dir: Path = build.DATA_DIR) -> list[dict]:
    """Every stored small-talk example of batches 1-4, in source order."""
    return [row for split in ("train", "validation") for source in SOURCES
            for row in map(json.loads, (data_dir / source.format(split=split)).read_text(encoding="utf-8").splitlines())
            if row["labels"]["template"] in TEMPLATES]  # fmt: skip


def _check_line(where: str, language: str, question: str, reply: str) -> None:
    found = []
    if _ARABIC.search(question) or _ARABIC.search(reply):
        found.append("Arabic script")
    if not question.strip() or len(question) > 300:
        found.append("blank or too long")
    if reply.startswith("REPLY:") and _NUMBER.search(reply):
        found.append("a REPLY states a number")
    found += [f"rejected spelling {w!r}" for w in answers_build.REJECTED
              if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", question, re.IGNORECASE)]  # fmt: skip
    if language not in ("arabizi", "mixed", "english"):
        found.append(f"unknown language {language!r}")
    if found:
        raise SmalltalkError(f"{where}: {question!r}: {'; '.join(found)}")


def _example(question: str, parts, user: int, reply: str, labels: dict) -> dict:
    prompt = build_prompt(question, parts.names, parts.today, (), gender=gender_of(user))
    return {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": reply}],
            "labels": labels}


def rebuilt_stored(rows: list[dict], kinds: dict[str, str], edits: dict) -> list[dict]:
    """The stored examples with their edited question and a reply of their kind."""
    seen, counts = Counter(), Counter(f"{r['labels']['language']}|{_question(r)}" for r in rows)
    for key, edit in edits.items():
        if key not in counts:
            raise SmalltalkError(f"an edit for a question that is not stored: {key!r}")
        if isinstance(edit, list) and len(edit) != counts[key]:
            raise SmalltalkError(f"{key!r}: {len(edit)} edits for {counts[key]} examples")
    out = []
    for row in rows:
        labels, original = row["labels"], _question(row)
        key = f"{labels['language']}|{original}"
        if key not in kinds:
            raise SmalltalkError(f"a stored small-talk question with no kind: {key!r}")
        edit = edits.get(key)
        question = (edit[seen[key]] if isinstance(edit, list) else edit) or original
        seen[key] += 1
        kind = kinds[key]
        reply = reply_for(kind, labels["language"], question, f"{labels['spec']}|{question}", row["messages"][1]["content"])
        _check_line(labels["spec"], labels["language"], question, reply)
        out.append(_example(question, read_prompt(row["messages"][0]["content"]), labels["user"], reply,
                            {**labels, "part": "smalltalk", "smalltalk": kind}))  # fmt: skip
    return out


def new_examples(new: list[dict], rows: list[dict]) -> list[dict]:
    """Each new question on a stored small-talk example's user (its names and day), of its gender when it has one;
    the users are taken in turn so the questions spread over them."""
    pools = defaultdict(list)
    for row in rows:
        pools[gender_of(row["labels"]["user"]).value].append(row)
        pools[None].append(row)
    taken = Counter()
    out = []
    for index, line in enumerate(new):
        pool = pools[line["gender"]]  # None: any user
        if not pool:
            raise SmalltalkError(f"no stored user for {line!r}")
        row = pool[(taken[line["gender"]] * 7) % len(pool)]  # a stride, so neighbours are different users
        taken[line["gender"]] += 1
        spec = f"s2-new-{index}"
        reply = reply_for(line["kind"], line["language"], line["question"], f"{spec}|{line['question']}")
        _check_line(spec, line["language"], line["question"], reply)
        labels = {"template": NEW_TEMPLATES[line["kind"]], "kind": "reply", "language": line["language"],
                  "user": row["labels"]["user"], "split": row["labels"]["split"], "spec": spec, "result_rows": None,
                  "part": "smalltalk", "smalltalk": line["kind"]}  # fmt: skip
        out.append(_example(line["question"], read_prompt(row["messages"][0]["content"]), row["labels"]["user"],
                            reply, labels))  # fmt: skip
    return out


def greeting_examples(versions: list[dict], stored: dict[str, dict], specs: dict) -> list[dict]:
    """A greeting in front of a stored, approved question: its SQL, its user, its day."""
    out = []
    for version in versions:
        if version["spec"] not in stored:
            raise SmalltalkError(f"no stored example for {version['spec']}")
        row = stored[version["spec"]]
        found = problems(Version(version["language"], version["question"]), specs[version["spec"]],
                         words._catalogue(version["spec"]))  # fmt: skip
        if found:
            raise SmalltalkError(f"{version['spec']}: {version['question']!r}: {'; '.join(found)}")
        _check_line(version["spec"], version["language"], version["question"], row["messages"][1]["content"])
        labels = {**row["labels"], "language": version["language"], "part": "smalltalk",
                  "smalltalk": "greeting + question"}  # fmt: skip
        out.append(_example(version["question"], read_prompt(row["messages"][0]["content"]), labels["user"],
                            row["messages"][1]["content"], labels))  # fmt: skip
    return out


def build_smalltalk(raw_dir: Path = RAW_DIR, out_dir: Path = DATA_DIR, data_dir: Path = build.DATA_DIR,
                    stored_raw: Path = build.RAW_DIR, held_out: tuple[str, ...] | None = None) -> dict:  # fmt: skip
    load = lambda name: json.loads((raw_dir / name).read_text(encoding="utf-8"))  # noqa: E731
    rows = stored_rows(data_dir)
    examples = rebuilt_stored(rows, load("kinds.json"), load("edits.json"))
    examples += new_examples(load("new.json"), rows)
    examples += greeting_examples(load("greetings.json"), words.stored(data_dir), words.stored_specs(stored_raw))
    held_out = build.test_questions(None) if held_out is None else held_out
    out, near = {"train": [], "validation": []}, 0
    for example in examples:
        if _question(example) not in NEAR_TEST_ALLOWED and near_duplicate(_question(example), held_out):
            near += 1
            continue
        out[example["labels"]["split"]].append(example)
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, found in out.items():
        (out_dir / f"smalltalk_{split}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in found), encoding="utf-8")
    return {"train": len(out["train"]), "validation": len(out["validation"]), "near test questions, dropped": near,
            "kinds": dict(Counter(e["labels"]["smalltalk"] for found in out.values() for e in found))}


if __name__ == "__main__":
    print(build_smalltalk())
