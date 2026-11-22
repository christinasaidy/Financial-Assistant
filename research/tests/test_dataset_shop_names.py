"""Made-up shop names and padded lists in the mix ("Light", decided with Christina on 2026-11-22; shop_names.py).
Do not change an expected value to make a test pass. Some tests read the built mix."""

import json
import re
from datetime import date

from app.domain.assistant.prompt import UserNames, build_prompt
from research.dataset import mix, shop_names
from research.dataset import templates as t
from research.dataset.rerender import read_prompt
from research.dataset.users import gender_of

USER = 45
NAMES = UserNames(items=["bread", "milk"], vendors=["Spinneys", "Pharmacie Mazloum", "Total"],
                  categories=["Groceries", "Dining"])  # fmt: skip


def _row(question: str, reply: str, vendors=None) -> dict:
    names = UserNames(items=NAMES.items, vendors=vendors or NAMES.vendors, categories=NAMES.categories)
    prompt = build_prompt(question, names, date(2026, 5, 3), (), gender=gender_of(USER))
    kind = "clarify" if reply.startswith("CLARIFY") else "sql"
    return {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": reply}],
            "labels": {"kind": kind, "user": USER, "template": "T1", "language": "arabizi"}}


def _mix_rows(split="train"):
    return [json.loads(line) for line in (mix.DATA_DIR / "mix" / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()]


def test_the_held_out_names_are_never_in_a_training_pool():
    surnames, firsts = shop_names.HELD_OUT
    assert len(surnames) >= 15 and len(firsts) >= 4
    for kind, names in shop_names.POOLS.items():
        for name in names:
            words = set(re.findall(r"[A-Za-z]+", name))
            assert not words & ({w for s in surnames for w in s.split("-")} - shop_names.PARTICLES) and not words & firsts, name
    assert shop_names.pool("bakery", held_out=True) and not set(shop_names.pool("bakery", held_out=True)) & set(
        shop_names.POOLS["bakery"])


def test_a_made_up_name_keeps_the_shops_kind_and_is_never_a_catalogue_shop():
    assert all(n.startswith("Pharmacie ") for n in shop_names.POOLS["pharmacy"])
    assert all(n.startswith(("Boulangerie ", "Furn ", "Pâtisserie ")) for n in shop_names.POOLS["bakery"])
    assert not set().union(*shop_names.POOLS.values()) & set(shop_names.SHOPS)


def test_an_ask_back_only_shop_is_always_swapped_in_the_question_and_the_reply():
    row = _row("kam marra akalet 3and macdo hal shaher?", "CLARIFY: ma la2ayt fatoura mn McDonald's hal shaher")
    new = shop_names.Swapper("train").swapped(row, 0)
    made_up = new["labels"]["shop_swap"]["McDonald's"]
    parts = read_prompt(new["messages"][0]["content"])
    assert parts.question == f"kam marra akalet 3and {made_up} hal shaher?"
    assert new["messages"][1]["content"] == f"CLARIFY: ma la2ayt fatoura mn {made_up} hal shaher"
    assert made_up not in parts.names.vendors and made_up in shop_names.POOLS["fast_food"]
    assert "McDonald" not in new["messages"][0]["content"] + new["messages"][1]["content"]


def test_a_swapped_shop_changes_in_the_list_the_question_and_the_sql_together(monkeypatch):
    monkeypatch.setattr(shop_names, "SWAP_SHARE", 1.0)
    monkeypatch.setattr(shop_names, "LOWER_SHARE", 0.0)  # lower case has its own test
    sql = f"SELECT SUM(total) AS total_spent FROM receipts WHERE vendor = {t.quoted('Spinneys')}"
    new = shop_names.Swapper("train").swapped(_row("adesh sarafet total 3a spinis hal shaher?", sql), 0)
    made_up = new["labels"]["shop_swap"]["Spinneys"]
    parts = read_prompt(new["messages"][0]["content"])
    assert parts.question == f"adesh sarafet total 3a {made_up} hal shaher?"  # "total" is a word here, not the shop
    assert new["messages"][1]["content"] == sql.replace("'Spinneys'", t.quoted(made_up))
    assert made_up in parts.names.vendors and "Spinneys" not in parts.names.vendors


def test_the_shop_total_is_swapped_only_where_it_is_written_as_the_shop(monkeypatch):
    monkeypatch.setattr(shop_names, "SWAP_SHARE", 1.0)
    monkeypatch.setattr(shop_names, "LOWER_SHARE", 0.0)  # lower case has its own test
    sql = f"SELECT SUM(total) AS total_spent FROM receipts WHERE vendor = {t.quoted('Total')}"
    new = shop_names.Swapper("train").swapped(_row("total masroufe 3and Total hal shaher?", sql), 0)
    made_up = new["labels"]["shop_swap"]["Total"]
    assert read_prompt(new["messages"][0]["content"]).question == f"total masroufe 3and {made_up} hal shaher?"
    assert "SUM(total) AS total_spent" in new["messages"][1]["content"]


def test_the_list_is_padded_to_20_100_never_with_a_pharmacy_or_a_kind_the_example_names():
    for index in range(30):
        new = shop_names.Swapper("train").swapped(_row("aday sarafet 3and Spinneys?", "SELECT 1 WHERE vendor = 'Spinneys'"), index)
        vendors = read_prompt(new["messages"][0]["content"]).names.vendors
        added = [v for v in vendors if v not in NAMES.vendors and v not in new["labels"]["shop_swap"].values()]
        assert 20 <= len(vendors) <= 100 and len(added) == new["labels"]["padded"]
        assert not any(v.startswith("Pharmacie") for v in added)
        assert not set(added) & set(shop_names.POOLS["supermarket"])  # the kind the question names


def test_answers_and_unreadable_rows_are_left_as_they_are():
    answer = {"messages": [{"role": "user", "content": "You write the answer..."}, {"role": "assistant", "content": "x"}],
              "labels": {"kind": "answer", "user": USER}}
    assert shop_names.Swapper("train").swapped(answer, 0) is answer


# --- the built mix ---


def test_in_the_mix_every_list_is_20_to_100_and_every_sql_shop_is_in_its_list():
    for row in _mix_rows():
        if row["labels"]["kind"] == "answer":
            continue
        parts = read_prompt(row["messages"][0]["content"])
        assert 20 <= len(parts.names.vendors) <= 100
        for shop in re.findall(r"vendor = '((?:[^']|'')*)'", row["messages"][1]["content"]):
            assert shop.replace("''", "'") in parts.names.vendors, (shop, row["labels"].get("spec"))


def test_in_the_mix_no_ask_back_only_shop_is_left_and_no_held_out_name_is_used():
    surnames, firsts = shop_names.HELD_OUT
    held = ({w for s in surnames for w in s.split("-")} - shop_names.PARTICLES) | firsts
    for split in ("train", "validation"):
        for row in _mix_rows(split):
            if row["labels"]["kind"] == "answer":
                continue
            reply = row["messages"][1]["content"]
            assert not any(t.quoted(s) in reply or (reply.startswith("CLARIFY") and s in reply)
                           for s in shop_names.ASK_BACK_ONLY), reply  # fmt: skip
            for made_up in row["labels"]["shop_swap"].values():
                assert not set(re.findall(r"[A-Za-z]+", made_up)) & held, made_up


def test_in_the_mix_about_30_percent_of_shop_examples_are_swapped_and_no_name_answers_more_than_3_times():
    rows = [r for r in _mix_rows() if r["labels"]["kind"] != "answer"]
    swapped = [r for r in rows if r["labels"]["shop_swap"]]
    uses = {}
    for r in swapped:
        for made_up in r["labels"]["shop_swap"].values():
            uses[made_up] = uses.get(made_up, 0) + 1
    assert max(uses.values()) <= 3 and len(uses) > 500
    naming = [r for r in rows if r["labels"]["shop_swap"] or any(
        t.quoted(s) in r["messages"][1]["content"] for s in shop_names.SHOPS if shop_names.SHOPS[s]["kind"] in shop_names.PRINTED)]
    assert 0.25 < len(swapped) / len(naming) < 0.5


def test_the_real_mix_is_the_batch_mix_with_only_shops_swapped_and_lists_padded(tmp_path):
    """Built from the mix tests' balanced batches: with the swap on, a row without a swap is the plain row with
    made-up names added to its list (nothing else); a swapped row no longer names its old shop."""
    from research.tests.test_dataset_mix import balanced, batch4_balanced, part5_balanced, stored, write_batches

    data = tmp_path / "data"
    rows = [stored(r) for r in balanced() + batch4_balanced() + part5_balanced()]
    write_batches(data, rows, rows[0])
    mix.build_mix(data, data / "plain", swap_shops=False)
    mix.build_mix(data, data / "real")
    plain = set((data / "plain" / "train.jsonl").read_text(encoding="utf-8").splitlines())
    real = [json.loads(line) for line in (data / "real" / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(real) == len(plain)
    made_up = set().union(*shop_names.POOLS.values())
    kept = 0
    for row in real:
        labels = dict(row["labels"])
        mapping, padded = labels.pop("shop_swap"), labels.pop("padded")
        if mapping:
            labels.pop("lower_case")
        parts = read_prompt(row["messages"][0]["content"])
        if mapping:
            assert not any(t.quoted(shop) in row["messages"][1]["content"] for shop in mapping)
            continue
        vendors = [v for v in parts.names.vendors if v not in made_up]
        assert len(parts.names.vendors) - len(vendors) == padded
        question = parts.question
        for name in labels.pop("lower_case"):
            question = re.sub(rf"(?<![\w']){re.escape(name.lower())}(?![\w'])", lambda _, n=name: n, question)
        names = UserNames(items=parts.names.items, vendors=vendors, categories=parts.names.categories)
        prompt = build_prompt(question, names, parts.today, parts.history, gender=gender_of(labels["user"]))
        restored = {**row, "messages": [{**row["messages"][0], "content": prompt}, row["messages"][1]], "labels": labels}
        assert json.dumps(restored, ensure_ascii=False) in plain
        kept += 1
    assert kept > len(real) // 2


def test_about_30_percent_of_shop_rows_are_swapped():
    swapper = shop_names.Swapper("train")
    rows = [swapper.swapped(_row("aday sarafet 3and Spinneys?", "SELECT 1 WHERE vendor = 'Spinneys'"), i) for i in range(400)]
    share = sum(bool(r["labels"]["shop_swap"]) for r in rows) / len(rows)
    assert 0.24 < share < 0.36


def test_a_made_up_name_is_the_answer_at_most_3_times(monkeypatch):
    monkeypatch.setattr(shop_names, "SWAP_SHARE", 1.0)
    swapper = shop_names.Swapper("train")
    sql = "SELECT 1 WHERE vendor = 'Pharmacie Mazloum'"
    names = [swapper.swapped(_row("aday 3and saydaliyet mazloum?", sql), i)["labels"]["shop_swap"]["Pharmacie Mazloum"]
             for i in range(250)]  # fmt: skip
    assert max(names.count(n) for n in set(names)) <= 3


def test_an_ask_back_only_shop_is_swapped_every_time_not_only_in_the_30_percent():
    swapper = shop_names.Swapper("train")
    row = _row("kam marra akalet 3and macdo hal shaher?", "CLARIFY: ma la2ayt fatoura mn McDonald's hal shaher")
    assert all("McDonald's" in swapper.swapped(row, i)["labels"]["shop_swap"] for i in range(40))


def test_no_held_out_name_appears_anywhere_in_training():
    from research.dataset import deciding

    assert "Fadi" not in shop_names.FIRST_NAMES and "Fadi" in deciding.LANDLORD
    held = ({w for s in shop_names.HELD_OUT[0] for w in s.split("-")} - shop_names.PARTICLES) | shop_names.HELD_OUT[1]
    for split in ("train", "validation"):
        for row in _mix_rows(split):
            text = row["messages"][0]["content"].split("Today:")[-1] + " " + row["messages"][1]["content"]
            assert not any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text) for w in held), row["labels"].get("spec")



def test_a_quarter_of_questions_type_a_listed_shop_in_lower_case_and_the_sql_keeps_its_name(monkeypatch):
    monkeypatch.setattr(shop_names, "SWAP_SHARE", 0.0)
    swapper = shop_names.Swapper("train")
    sql = "SELECT 1 FROM receipts WHERE vendor = 'Spinneys'"
    rows = [swapper.swapped(_row("aday sarafet 3and Spinneys?", sql), i) for i in range(400)]
    lowered = [r for r in rows if r["labels"]["lower_case"]]
    assert 0.18 < len(lowered) / len(rows) < 0.32
    for r in lowered:
        assert read_prompt(r["messages"][0]["content"]).question == "aday sarafet 3and spinneys?"
        assert r["messages"][1]["content"] == sql and "Spinneys" in read_prompt(r["messages"][0]["content"]).names.vendors


def test_a_shop_name_that_is_also_a_word_is_never_lower_cased(monkeypatch):
    monkeypatch.setattr(shop_names, "SWAP_SHARE", 0.0)
    monkeypatch.setattr(shop_names, "LOWER_SHARE", 1.0)
    row = _row("total masroufe 3and Total?", "SELECT 1 FROM receipts WHERE vendor = 'Total'")
    assert read_prompt(shop_names.Swapper("train").swapped(row, 0)["messages"][0]["content"]).question == "total masroufe 3and Total?"
