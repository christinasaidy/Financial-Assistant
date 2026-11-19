"""Batch 5 part 1: earlier exchanges in front of stored questions. The rules were approved by Christina on
2026-11-17/18 (agent_documentation/PROGRESS.md); do not change a threshold or an expected value to make a test
pass."""

from collections import Counter
from datetime import date

import pytest

from app.domain.assistant.prompt import Exchange, Gender, UserNames, build_prompt
from research.dataset import history
from research.dataset.history import HistoryError, Turn, add_history, as_exchanges, follows_well
from research.dataset.rerender import read_prompt, without_batch5_lines

NAMES = UserNames(["sushi", "yoga mat", "socks"], ["O&C", "Sushi Co"], ["Dining", "Groceries"])
TODAY = date(2026, 12, 9)
SUSHI_TIMES = ("SELECT COUNT(DISTINCT receipt_id) AS times FROM purchases WHERE item_name = 'sushi' AND receipt_date "
               ">= date_trunc('month', CURRENT_DATE)")  # fmt: skip
OC_LAST = "SELECT MAX(receipt_date) AS last_time FROM receipts WHERE vendor = 'O&C'"
TOTAL_MONTH = "SELECT currency, SUM(total) AS total_spent FROM receipts WHERE receipt_date >= date_trunc('month', CURRENT_DATE) GROUP BY currency"  # noqa: E501
TOTAL_EVER = "SELECT currency, SUM(total) AS total_spent FROM receipts GROUP BY currency"
SOCKS_EVER = "SELECT currency, SUM(line_total) AS total_spent FROM purchases WHERE item_name = 'socks' GROUP BY currency"


def turn(spec, template="T9", kind="sql", reply="SELECT 1", period=True, what=frozenset({("item_name", "'x'")}),
         group="arabizi", reviewed=True, question="q?"):  # fmt: skip
    return Turn(0, question, reply, template, kind, group, spec, reviewed, period, what)


SUSHI = turn("b4-46-7", template="T15", reply=SUSHI_TIMES, what=frozenset({("item_name", "'sushi'")}))
THANKS = turn("b4-46-20", template="R2", kind="reply", reply="REPLY: Walaw", period=None, what=None)
GREETING = turn("b4-46-21", template="R1", kind="reply", reply="REPLY: Marhaba", period=None, what=None)


# --- What may follow what (the approved prompt line: what a question leaves out comes from the earlier one) ---


def test_her_example_e1_a_new_question_that_states_its_shop_follows_anything():
    last_visit = turn("b4-46-14", template="B11", reply=OC_LAST, period=False, what=frozenset({("vendor", "'O&C'")}))
    assert follows_well(last_visit, [SUSHI])


def test_a_question_with_no_period_never_follows_one_with_a_period():
    socks = turn("b4-46-3", template="T9", reply=SOCKS_EVER, period=False, what=frozenset({("item_name", "'socks'")}))
    assert not follows_well(socks, [SUSHI])  # "this month" would carry over, but its answer is all-time
    assert not follows_well(socks, [SUSHI, THANKS])  # thanks says nothing, so sushi's period still applies


@pytest.mark.parametrize("template", sorted(history.NO_PERIOD_KINDS))
def test_kinds_that_take_no_period_follow_a_period(template):
    assert follows_well(turn("b4-46-9", template=template, period=False), [SUSHI])


def test_a_question_with_no_item_or_shop_never_follows_one_with_one():
    total = turn("b4-46-4", template="T1", reply=TOTAL_MONTH, what=frozenset())
    assert not follows_well(total, [SUSHI])  # it would mean sushi this month
    receipts_ever = turn("b4-46-5", template="T16", reply="SELECT COUNT(*) FROM receipts", period=False, what=frozenset())
    assert follows_well(total, [receipts_ever])
    # the same measure with only the period changed is a follow-up, not a new question (approved rule)
    assert not follows_well(total, [turn("b4-46-2", template="T1", reply=TOTAL_EVER, period=False, what=frozenset())])
    item_missing = turn("b4-46-6", template="C1", kind="clarify", reply="CLARIFY: ma edert le2e fatoura 3an gifts",
                        period=False, what=frozenset({("asked", "C1")}))  # fmt: skip
    assert not follows_well(total, [item_missing])


def test_the_same_question_reworded_never_follows_itself():
    again = turn("b4-46-8", template="T15", reply=SUSHI_TIMES, what=frozenset({("item_name", "'sushi'")}))
    assert not follows_well(again, [SUSHI])
    assert not follows_well(SUSHI, [SUSHI])


def test_refusals_replies_and_clarifications_follow_anything():
    for template, kind in (("U2", "unsupported"), ("R2", "reply"), ("C1", "clarify"), ("C6", "clarify")):
        assert follows_well(turn("b4-46-30", template=template, kind=kind, period=None, what=None), [SUSHI])


def test_a_greeting_comes_only_first_and_thanks_only_right_after_an_answer():
    question = turn("b4-46-40", template="U2", kind="unsupported", period=None, what=None)
    assert follows_well(question, [GREETING, SUSHI, THANKS])
    assert not follows_well(question, [SUSHI, GREETING])
    assert not follows_well(question, [THANKS, SUSHI])
    assert not follows_well(question, [GREETING, THANKS])


@pytest.mark.parametrize(("template", "kind", "period", "given", "earlier"), [
    ("C3", "clarify", None, False, False),  # "how much did I pay there?" is clear once something is earlier
    ("R1", "reply", None, False, True),  # a greeting starts a chat
    ("R5", "reply", None, True, False),  # a sign-off ends one
    ("C6", "clarify", None, True, False),  # "ma fhemet" after a real answer is fine, but not as an earlier turn
    ("C4", "clarify", "hal fatra", False, False),
    ("C4", "clarify", "kanoun", True, False),
    ("T9", "follow_up", "last_month", False, False),
    ("T9", "sql", "this_month", True, True),
])  # fmt: skip
def test_which_questions_get_history_and_which_can_be_earlier(template, kind, period, given, earlier):
    row = {"labels": {"period": period}}
    t = turn("b4-46-50", template=template, kind=kind)
    assert history.can_be_given(t, row) is given
    assert history.can_be_earlier(t) is earlier


def test_only_reviewed_arabizi_and_any_english_take_part():
    unreviewed = turn("12-3", reviewed=False)
    assert not history.can_be_given(unreviewed, {"labels": {}}) and not history.can_be_earlier(unreviewed)


# --- The history is exactly what the app would send ---


def test_earlier_replies_reach_the_prompt_as_the_app_sends_them_with_their_prefix():
    pairs = [("kam mara akalet sushi hal shaher?", SUSHI_TIMES),
             ("aday dafa3et 3al yoga mat?", "CLARIFY: ma edert le2e fatoura 3an yoga mat"),
             ("aday saraf khaye?", "UNSUPPORTED"), ("merci", "REPLY: Walaw")]  # fmt: skip
    assert as_exchanges(pairs) == [Exchange(q, r) for q, r in pairs]


def test_at_most_six_exchanges_and_6000_characters_the_oldest_dropped_first():
    pairs = [(f"q{n}", f"SELECT {n}") for n in range(8)]
    assert [e.question for e in as_exchanges(pairs)] == ["q2", "q3", "q4", "q5", "q6", "q7"]
    long = [("a" * 3000, "SELECT 1"), ("b" * 2500, "SELECT 2"), ("c" * 900, "SELECT 3")]  # 6,424 characters
    assert [e.question[0] for e in as_exchanges(long)] == ["b", "c"]


# --- The whole builder, on a small made-up dataset ---


def row(user, spec, question, reply, template="T9", kind="sql", language="arabizi", period="this_month", base=None):
    earlier = (Exchange(*base),) if base else ()
    prompt = without_batch5_lines(build_prompt(question, NAMES, TODAY, earlier, gender=Gender.MAN))
    return {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": reply}],
            "labels": {"user": user, "spec": spec, "template": template, "kind": kind, "language": language,
                       "period": period}}  # fmt: skip


def dataset():
    """Two users (46 is a woman, 45 a man), each with reviewed questions in 3 versions and a few follow-ups."""
    rows = []
    for user in (46, 45):
        for n in range(30):
            item = ("sushi", "socks", "yoga mat")[n % 3]
            sql = f"SELECT SUM(line_total) FROM purchases WHERE item_name = '{item}' AND receipt_date >= date_trunc('month', CURRENT_DATE)"  # noqa: E501
            for version, language in enumerate(("arabizi", "arabizi", "english")):
                rows.append(row(user, f"b4-{user}-{n}", f"aday {item} {n} v{version}?", sql, language=language))
        for n in range(4):
            rows.append(row(user, f"b4-{user}-f{n}", f"w ekher shaher {n}?", "SELECT 2", kind="follow_up",
                            language="english", period="last_month", base=("aday sushi?", "SELECT 1")))  # fmt: skip
    from research.dataset.rerender import rerender

    return [rerender(r) for r in rows]


def test_the_builder_keeps_70_percent_of_chats_ignoring_their_history_and_every_rule():
    rows = dataset()
    out, report = add_history(rows, "train")
    assert report["independent_share"] == pytest.approx(0.70, abs=0.05)
    assert report["with_history"] == 8 + report["independent"]
    for before, after in zip(rows, out):
        assert after["messages"][1] == before["messages"][1]  # the gold reply never changes
        parts, old = read_prompt(after["messages"][0]["content"]), read_prompt(before["messages"][0]["content"])
        assert parts.question == old.question and parts.today == old.today
        if after["labels"].get("history_role") == "independent":
            specs = after["labels"]["history_specs"]
            assert all(s.startswith(f"b4-{after['labels']['user']}-") for s in specs)  # the same user only
            assert after["labels"]["spec"] not in specs and len(parts.history) == len(specs) <= 6
    per_spec = Counter(r["labels"]["spec"] for r in out if r["labels"].get("history_role") == "independent")
    assert max(per_spec.values()) <= 1  # 3 versions: at most a third
    for spec in per_spec:
        arabizi = [r for r in out if r["labels"]["spec"] == spec and r["labels"]["language"] == "arabizi"]
        assert any(not r["labels"].get("history") for r in arabizi)


def test_each_chat_is_the_apps_prompt_for_the_users_gender():
    out, _ = add_history(dataset(), "train")
    chats = [r for r in out if r["labels"].get("history_role") == "independent"]
    assert chats
    for r in chats:
        parts = read_prompt(r["messages"][0]["content"])
        gender = Gender.WOMAN if r["labels"]["user"] == 46 else Gender.MAN
        assert r["messages"][0]["content"] == build_prompt(parts.question, parts.names, parts.today, parts.history,
                                                           gender=gender)  # fmt: skip


def test_the_same_data_gives_the_same_chats():
    assert add_history(dataset(), "train")[0] == add_history(dataset(), "train")[0]


def test_too_few_questions_to_balance_the_follow_ups_is_refused():
    rows = [r for r in dataset() if r["labels"]["kind"] == "follow_up" or r["labels"]["spec"].endswith(("-1", "-2"))]
    with pytest.raises(HistoryError, match="ignore their history"):
        add_history(rows, "train")


def test_a_question_is_never_its_own_earlier_exchange():
    reworded = turn("b4-46-7", template="T9", reply="SELECT 9", what=frozenset({("item_name", "'socks'")}))
    assert not follows_well(reworded, [SUSHI])  # the same spec as SUSHI, though it looks different


def test_a_question_with_one_arabizi_version_keeps_it_standalone():
    rows = []
    for n in range(30):
        sql = f"SELECT SUM(line_total) FROM purchases WHERE item_name = 'item{n}' AND receipt_date >= CURRENT_DATE - 7"
        for version, language in enumerate(("arabizi", "english", "english")):
            rows.append(row(46, f"b4-46-{n}", f"aday item{n} v{version}?", sql, language=language))
    rows += [row(46, f"b4-46-f{n}", f"and last month {n}?", "SELECT 2", kind="follow_up", language="english",
                 period="last_month", base=("aday sushi?", "SELECT 1")) for n in range(6)]  # fmt: skip
    from research.dataset.rerender import rerender

    out, report = add_history([rerender(r) for r in rows], "train")
    assert report["independent"] == 14
    assert not any(r["labels"].get("history") for r in out if r["labels"]["language"] == "arabizi")


def big_dataset():
    """One woman (46) with 210 questions in 3 versions (a third of them refusals) and 90 English follow-ups."""
    rows = []
    for n in range(210):
        for version, language in enumerate(("arabizi", "arabizi", "english")):
            question = f"q{n} v{version} {language}?"
            if n % 3 == 0:
                rows.append(row(46, f"b4-46-{n}", question, "UNSUPPORTED", template="U2", kind="unsupported",
                                language=language, period="none"))  # fmt: skip
            else:
                sql = f"SELECT SUM(line_total) FROM purchases WHERE item_name = 'item{n}' AND receipt_date >= CURRENT_DATE - 7"
                rows.append(row(46, f"b4-46-{n}", question, sql, language=language))
    rows += [row(46, f"b4-46-f{n}", f"and last month {n}?", "SELECT 2", kind="follow_up", language="english",
                 period="last_month", base=(f"base {n}?", "SELECT 1")) for n in range(90)]  # fmt: skip
    from research.dataset.rerender import rerender

    return [rerender(r) for r in rows]


@pytest.fixture(scope="module")
def big():
    rows = big_dataset()
    return rows, add_history(rows, "train")[0]


def test_about_80_percent_of_earlier_exchanges_share_the_questions_language_and_70_percent_are_sql(big):
    rows, out = big
    language = {read_prompt(r["messages"][0]["content"]).question: r["labels"]["language"] for r in rows}
    same, sql, total = 0, 0, 0
    for r in out:
        if r["labels"].get("history_role") != "independent":
            continue
        english = r["labels"]["language"] == "english"
        for exchange in read_prompt(r["messages"][0]["content"]).history:
            total += 1
            same += (language[exchange.question] == "english") == english
            sql += exchange.reply.startswith("SELECT")
    assert 0.72 <= same / total <= 0.88
    assert 0.62 <= sql / total <= 0.78


def test_chat_lengths_follow_the_approved_spread(big):
    _, out = big
    lengths = Counter(r["labels"]["history"] for r in out if r["labels"].get("history_role") == "independent")
    total = sum(lengths.values())
    assert total == 210
    for n, share in history.LENGTHS:
        assert abs(lengths[n] / total - share) <= 0.07, (n, lengths)


def test_a_third_of_english_follow_ups_get_older_exchanges_and_keep_their_own_earlier_question_last(big):
    _, out = big
    older = [r for r in out if r["labels"].get("history_role") == "dependent"]
    assert len(older) == 30
    for r in older:
        exchanges = read_prompt(r["messages"][0]["content"]).history
        n = r["labels"]["spec"].rsplit("f", 1)[1]
        assert len(exchanges) >= 2 and exchanges[-1] == Exchange(f"base {n}?", "SELECT 1")


def test_long_chats_where_nothing_goes_wrong_are_there(big):
    """Christina, 2026-11-19: chats of normal questions and answers only were missing."""
    _, out = big
    long_normal = [r for r in out if r["labels"].get("history_role") == "independent" and r["labels"]["history"] >= 3
                   and r["messages"][1]["content"].startswith("SELECT")]  # fmt: skip
    plain = [r for r in long_normal if all(e.reply.startswith("SELECT")
                                           for e in read_prompt(r["messages"][0]["content"]).history)]  # fmt: skip
    assert len(plain) >= 0.4 * len(long_normal) > 0


# --- batch 5's written chats (2026-11-19) ---


def written_chat(user, n, role):
    """English, so that only being a written chat (not the reviewed-Arabizi rule) keeps it out of other chats."""
    base = row(user, f"b5-{user}-{n}", f"and how many times socks {n}?", SOCKS_EVER, template="P1A", language="english",
               base=(f"aday sushi {n}?", "SELECT 1"))  # fmt: skip
    base["labels"].update({"history": 1, "history_role": role})
    return base


def with_written(n_independent=40, n_dependent=40):
    from research.dataset.rerender import rerender

    chats = [rerender(written_chat(46, n, "independent")) for n in range(n_independent)]
    chats += [rerender(written_chat(46, 100 + n, "dependent")) for n in range(n_dependent)]
    return dataset() + chats


def test_written_chats_are_never_earlier_turns_or_given_new_history():
    rows = with_written()
    out, _ = add_history(rows, "train")
    written_questions = {read_prompt(r["messages"][0]["content"]).question for r in rows if r["labels"]["spec"].startswith("b5-")}
    for before, after in zip(rows, out):
        exchanges = read_prompt(after["messages"][0]["content"]).history
        assert not any(e.question in written_questions for e in exchanges)
        if before["labels"]["spec"].startswith("b5-"):
            old = read_prompt(before["messages"][0]["content"]).history
            assert exchanges[-len(old):] == old  # its own earlier turn stays last
            assert after["labels"]["history_role"] == before["labels"]["history_role"]


def test_written_chats_count_towards_the_70_30_balance_and_a_third_get_older_turns():
    rows = with_written(n_independent=40, n_dependent=40)
    out, report = add_history(rows, "train")
    assert report["independent_share"] == pytest.approx(0.70, abs=0.05)
    longer = [r for r in out if r["labels"]["spec"].startswith("b5-") and r["labels"]["history"] >= 2]
    assert len(longer) == round(80 / 3)


def test_the_history_added_is_exactly_what_70_30_needs_once_written_chats_count():
    rows = with_written(n_independent=20, n_dependent=4)
    _, report = add_history(rows, "train")
    # 8 follow-ups + 4 written ones use history: round(12 * 0.7 / 0.3) = 28 ignore it, 20 of them written ones.
    assert report["independent"] == 28 and report["with_history"] == 40


def test_written_chats_are_never_taken_as_questions_to_give_history_to():
    """With only follow-ups and written chats, nothing may be given history, so 70/30 cannot be met: refused, rather
    than replacing a written chat's own earlier turn."""
    from research.dataset.rerender import rerender

    rows = [r for r in dataset() if r["labels"]["kind"] == "follow_up"]
    for n in range(32):  # 4 versions per written job, as batch 5 has
        chat = written_chat(46, 200 + n, "dependent")
        chat["labels"]["spec"] = f"b5-46-{200 + n // 4}"
        rows.append(rerender(chat))
    # greetings can open a chat but are never given history: the only earlier turns there are
    rows += [rerender(row(46, f"b4-46-g{n}", f"hi {n}", "REPLY: Hi!", template="R1", kind="reply", language="english",
                          period="none")) for n in range(10)]  # fmt: skip
    with pytest.raises(HistoryError, match=r"train: 0\.0% of chats ignore"):  # none given, not some written ones
        add_history(rows, "train")
