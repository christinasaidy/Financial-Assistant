"""A shop-name lookup prototype, and its test (decided with Christina on 2026-11-22; PROGRESS.md "name resolution").

    python -m research.name_lookup.lookup    # runs the test on raw/batch5/names_test/*.md

Python's standard library only. The design and both cut-offs are fixed here BEFORE the first run; the first run's
numbers are the result (no tuning on the test lines afterwards).

How a question is matched to the user's shops:
- every word is folded: lower case, accents dropped, Arabizi digits (7 -> h, 5 -> kh, 3 and 2 dropped), ch -> sh,
  ou / oo -> u, ee / ei -> i, y -> i, q / c -> k, ph -> f, double letters single, a final h after a vowel dropped;
- articles and little words (el, al, 3and, mn, bi, 3a, ...) are dropped from both sides;
- kind words (furn, boulangerie, saydaliyet, pharmacie, dekkene, mini market, la77am, boucherie, masbagha, pressing,
  ...) are taken out of both sides; what is left of the shop's name is its distinctive part;
- each run of 1-3 words left in the question is compared with each shop's distinctive part (difflib's ratio, on the
  folded words and on their consonants), the best run counting; a kind word the question shares with the shop adds
  0.05, a different kind takes 0.05 off.
Cut-offs (fixed before running): a shop is a candidate at 0.75 or more (the 5 best are kept); a strong match is 0.9.

The test (pass mark fixed in raw/batch5/names_test/her_questions.md, 2026-11-22):
- part 1 (shops the user has): the right shop among the candidates for at least 90% of the questions;
- part 2 (look-alikes the user does not have): a strong match for fewer than 25%. The two pairs she did not judge
  (boutique laura / Boutique Lara, saydaliyet salibi / Pharmacie Saliba) are counted apart.
The user's list: every part-1 printed name and the training catalogue's 82 shops (about 115 names); the part-2 shops
are not in it.
"""

import difflib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "research" / "dataset" / "raw" / "batch5" / "names_test"
CATALOGUES = [ROOT / "research" / "dataset" / "data" / f for f in ("catalogue.json", "catalogue_batch3.json",
                                                                    "catalogue_batch4.json")]  # fmt: skip
CANDIDATE, STRONG, TOP = 0.75, 0.9, 5
UNJUDGED_LOOKALIKES = ("boutique laura", "saydaliyet salibi")

KINDS = {
    "bakery": "furn forn boulangerie bakery patisserie",
    "pharmacy": "saydaliye saydaliyet saydalie saydaliyye pharmacie pharmacy",
    "grocery": "dekkene dekkenet dekene dekenet dikkene mini market minimarket supermarket superette epicerie",
    "butcher": "la77am lahham la7am boucherie butcher",
    "laundry": "masbagha masbaghit masbaghet pressing laundry",
    "food": "snack mat3am restaurant resto ahwe 2ahwe cafe coffee",
    "hair": "coiffeur coiffure salon",
    "sweets": "halawiyat 7alawiyat sweets 7elwayet",
    "clothes": "boutique",
    "electronics": "electro electronics mobile phone",
    "garage": "garage mechanic",
    "books": "librairie maktabe maktabet",
}
KIND_OF = {word: kind for kind, words in KINDS.items() for word in words.split()}
LITTLE = set("el al l le la the 3and 3end aand eend 3nd mn men min bi b bel bil 3a aa 3al aal at from in to w and of "
             "de du des".split())  # fmt: skip


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def fold(word: str) -> str:
    w = _plain(word).replace("5", "kh").replace("7", "h").replace("3", "").replace("2", "")
    for old, new in (("ch", "sh"), ("ph", "f"), ("ou", "u"), ("oo", "u"), ("ee", "i"), ("ei", "i"), ("y", "i"),
                     ("q", "k"), ("c", "k")):  # fmt: skip
        w = w.replace(old, new)
    w = re.sub(r"(.)\1+", r"\1", w)
    return re.sub(r"(?<=[aeiou])h$", "", w)


def consonants(folded: str) -> str:
    return folded[:1] + re.sub(r"[aeiou]", "", folded[1:])


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", _plain(text).replace("'", ""))


def split_name(name: str) -> tuple[set[str], list[str]]:
    """A name's kinds and its distinctive words (folded)."""
    words = [w for w in _words(name) if w not in LITTLE]
    return {KIND_OF[w] for w in words if w in KIND_OF}, [fold(w) for w in words if w not in KIND_OF]


def _similar(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    x, y = " ".join(a), " ".join(b)
    cx, cy = " ".join(map(consonants, a)), " ".join(map(consonants, b))
    return max(difflib.SequenceMatcher(None, x, y).ratio(), difflib.SequenceMatcher(None, cx, cy).ratio())


def scores(question: str, names: list[str]) -> list[tuple[float, str]]:
    words = [w for w in _words(question) if w not in LITTLE]
    asked_kinds = {KIND_OF[w] for w in words if w in KIND_OF}
    runs, run = [], []
    for w in words:
        if w in KIND_OF:
            runs.append(run)
            run = []
        else:
            run.append(fold(w))
    runs.append(run)
    windows = [r[i:i + n] for r in runs for n in (1, 2, 3) for i in range(len(r) - n + 1)]
    found = []
    for name in names:
        kinds, distinct = split_name(name)
        best = max((_similar(w, distinct) for w in windows), default=0.0)
        if asked_kinds and kinds:
            best += 0.05 if asked_kinds & kinds else -0.05
        found.append((round(best, 3), name))
    return sorted(found, reverse=True)


def candidates(question: str, names: list[str]) -> list[tuple[float, str]]:
    return [(s, n) for s, n in scores(question, names) if s >= CANDIDATE][:TOP]


def _lines(path: Path) -> dict[str, list[tuple[str, str]]]:
    parts, part = {"1": [], "2": []}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Part"):
            part = line.split()[2].rstrip(":")
        elif part in parts and " | " in line and not re.match(r"^\s*(\d+\.\s*)?$", line.split(" | ")[0]):
            question, name = (s.strip() for s in line.split(" | ", 1))
            parts[part].append((re.sub(r"^\d+\.\s*", "", question), name.removeprefix("looks like:").strip()))
    return parts


def catalogue_names() -> list[str]:
    names = set()
    for path in CATALOGUES:
        data = json.loads(path.read_text(encoding="utf-8"))
        shops = data.get("shops", {})
        names |= set(shops) if isinstance(shops, dict) else {s["name"] if isinstance(s, dict) else s for s in shops}
    return sorted(names)


def run(path: Path) -> dict:
    parts = _lines(path)
    names = sorted({n for _, n in parts["1"]} | set(catalogue_names()))
    hits = [(q, n, candidates(q, names)) for q, n in parts["1"]]
    found = [h for h in hits if any(c == h[1] for _, c in h[2])]
    first = [h for h in hits if h[2] and h[2][0][1] == h[1]]
    lookalikes = [(q, n, [c for c in candidates(q, names) if c[0] >= STRONG]) for q, n in parts["2"]]
    judged = [x for x in lookalikes if not any(u in x[0].lower() for u in UNJUDGED_LOOKALIKES)]
    strong = [x for x in judged if x[2]]
    return {"names in the list": len(names), "part 1": len(hits), "right shop among candidates": len(found),
            "right shop first": len(first), "part 2 judged": len(judged), "part 2 strong match": len(strong),
            "missed": [(q, n, h[:3]) for q, n, h in hits if (q, n, h) not in found],
            "strong look-alikes": [(q, n, s[:2]) for q, n, s in strong],
            "unjudged pairs": [(q, n, s[:2]) for q, n, s in lookalikes if (q, n, s) not in judged]}  # fmt: skip


def main() -> int:
    for name in ("agent_questions.md", "her_questions.md"):
        report = run(TEST_DIR / name)
        if not report["part 1"]:
            print(f"{name}: no lines yet")
            continue
        p1 = report["right shop among candidates"] / report["part 1"]
        p2 = report["part 2 strong match"] / max(1, report["part 2 judged"])
        print(f"\n=== {name} ({report['names in the list']} names in the list)")
        print(f"part 1: right shop among candidates {report['right shop among candidates']}/{report['part 1']} "
              f"= {p1:.0%} (pass >= 90%); first {report['right shop first']}/{report['part 1']}")
        print(f"part 2: strong match {report['part 2 strong match']}/{report['part 2 judged']} = {p2:.0%} "
              f"(pass < 25%)")
        print("PASS" if p1 >= 0.9 and p2 < 0.25 else "FAIL")
        for key in ("missed", "strong look-alikes", "unjudged pairs"):
            print(f"-- {key}:")
            for row in report[key]:
                print("  ", row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
