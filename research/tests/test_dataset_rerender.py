"""Batch 5's gender forms and the rebuilding of every stored example with today's prompt. The forms are Christina's,
approved on 2026-11-18 (research/dataset/raw/batch5/gender_forms_reviewed.md); do not change an expected value to
make a test pass."""

from datetime import date

import pytest

from app.domain.assistant.prompt import Exchange, Gender, UserNames, build_prompt
from research.dataset.genders import PERIOD_QUESTIONS, UnformedReply, for_gender
from research.dataset.rerender import UnreadablePrompt, read_prompt, rerender, without_batch5_lines

NAMES = UserNames(items=["sushi", "yoga mat"], vendors=["O&C", "Sushi Co"], categories=["Dining", "Groceries"])
TODAY = date(2026, 12, 9)
WOMAN, MAN, NOT_GIVEN = 46, 45, 43  # users of batch 4, by gender_of

# Her table A, with names filled in where the reply repeats one: (man, woman, neutral).
TABLE_A = [
    ("CLARIFY: 7a2 shu? fik taati tafasil aktar", "CLARIFY: 7a2 shu? fiki taate tafasil aktar",
     "CLARIFY: 7a2 shu bel zabt? fi tafasil aktar?"),
    ("REPLY: hahaha, fie se3dak b shi tene?", "REPLY: hahaha, fie se3dik b shi tene?",
     "REPLY: hahaha, fi shi tene fie se3ed fi?"),
    ("CLARIFY: shu baddak ta3ref bel zabt?", "CLARIFY: shu baddik ta3rfe bel zabt?", "CLARIFY: shu el ma2soud bel zabt?"),
    ("CLARIFY: azdak mn emta la emta?", "CLARIFY: azdik mn emta la emta?", "CLARIFY: mn emta la emta bel zabt?"),
    ("CLARIFY: azdak kanoun el awal aw kanoun el tene?", "CLARIFY: azdik kanoun el awal aw kanoun el tene?",
     "CLARIFY: kanoun el awal aw kanoun el tene?"),
    ("CLARIFY: azdak ayya ashhor bel zabt?", "CLARIFY: azdik ayya ashhor bel zabt?", "CLARIFY: ayya ashhor bel zabt?"),
    ("CLARIFY: azdak awal 3 oshhor mn el sene?", "CLARIFY: azdik awal 3 oshhor mn el sene?",
     "CLARIFY: awal 3 oshhor mn el sene?"),
    ("CLARIFY: ma fie elak aya wahad ahsan, bas fie shuf aya wahad arkhas?",
     "CLARIFY: ma fie elik aya wahad ahsan, bas fie shuf aya wahad arkhas?",
     "CLARIFY: ma fie 2oul aya wahad ahsan, bas fie shuf aya wahad arkhas?"),
    ("CLARIFY: ma la2ayt fatoura bi Sushi Co, 2asdak Crepaway?", "CLARIFY: ma la2ayt fatoura bi Sushi Co, 2asdik Crepaway?",
     "CLARIFY: ma la2ayt fatoura bi Sushi Co, ya3ne Crepaway?"),
    ("CLARIFY: ma edert le2e fatoura 3an yoga mat, 2asdak tapis?",
     "CLARIFY: ma edert le2e fatoura 3an yoga mat, 2asdik tapis?", "CLARIFY: ma edert le2e fatoura 3an yoga mat, ya3ne tapis?"),
    ("CLARIFY: aya mahal azdak?", "CLARIFY: aya mahal azdik?", "CLARIFY: aya mahal bel zabt?"),
    ("REPLY: eh hon, fiye se3dak?", "REPLY: eh hon, fiye se3dik?", "REPLY: eh hon, shu fiye a3mel?"),  # her row 12
    # Her table C.
    ("REPLY: fie jewbak 3an masroufak men fawatirak: adde sarfet, aa shu, wen",
     "REPLY: fie jewbik 3an masroufik men fawatirik: adde sarafte, aa shu, wen",
     "REPLY: fie jeweb 3an el masruf men el fwatir: adde, aa shu, wen"),
    ("CLARIFY: aymta w mn aya mahal jebto? aw shu fi yekun maktoub 3al fatoura?",
     "CLARIFY: aymta w mn aya mahal jebte? aw shu fi yekun maktoub 3al fatoura?",
     "CLARIFY: aymta w mn aya mahal? aw shu fi yekun maktoub 3al fatoura?"),
    ("CLARIFY: aya mahal? fik taati tafasil aktar", "CLARIFY: aya mahal? fiki taate tafasil aktar",
     "CLARIFY: aya mahal bel zabt?"),
]  # fmt: skip


@pytest.mark.parametrize("man, woman, neutral", TABLE_A)
def test_each_reply_takes_the_form_of_the_users_gender(man, woman, neutral):
    assert for_gender(man, Gender.MAN) == man
    assert for_gender(man, Gender.WOMAN) == woman
    assert for_gender(man, Gender.NOT_GIVEN) == neutral


@pytest.mark.parametrize("reply", ["CLARIFY: ma edert le2e fatoura 3an gifts", "REPLY: Ya Hala", "REPLY: sabah el nour",
                                   "UNSUPPORTED", "SELECT 1", "CLARIFY: Which shop do you mean?",
                                   "CLARIFY: aan aya ma7al aam tehki?"])  # "tehki" is not gendered (Christina) # fmt: skip
def test_a_reply_with_no_gendered_word_stays_as_it_is(reply):
    for gender in Gender:
        assert for_gender(reply, gender) == reply


@pytest.mark.parametrize("reply", ["REPLY: shu baddak?", "CLARIFY: fik t2elle aya mahal?", "REPLY: enta hon?"])  # fmt: skip
def test_a_masculine_reply_with_no_approved_forms_is_refused_even_for_a_man(reply):
    for gender in Gender:
        with pytest.raises(UnformedReply):
            for_gender(reply, gender)


def old_example(user: int, question: str, reply: str, history=(), language="arabizi") -> dict:
    """An example as batches 1-4 stored it: no gender line, no new rule."""
    prompt = without_batch5_lines(build_prompt(question, NAMES, TODAY, history, gender=Gender.MAN))
    return {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": reply}],
            "labels": {"user": user, "language": language, "spec": "b4-x-1"}}  # fmt: skip


def test_a_prompt_reads_back_into_the_parts_it_was_built_from():
    history = (Exchange("kam mara akalet sushi hal shaher?", "SELECT 1"), Exchange("aday?", "CLARIFY: shu?"))
    for names in (NAMES, UserNames([], [], ["Groceries"])):
        for gender in Gender:
            parts = read_prompt(build_prompt("w ekher shaher?", names, TODAY, history, gender=gender))
            assert (parts.question, parts.today, parts.history) == ("w ekher shaher?", TODAY, history)
            assert (list(parts.names.items), list(parts.names.vendors)) == (list(names.items), list(names.vendors))


def test_a_stored_example_gets_the_users_gender_the_new_rule_and_her_reply_form():
    old = old_example(WOMAN, "aday sarafet bi awal el shaher?", "CLARIFY: azdak mn emta la emta?")
    new = rerender(old)
    prompt = new["messages"][0]["content"]
    assert "Today: 2026-12-09 (Wednesday)\nThe user is a woman.\nThe user's items:" in prompt
    assert "In a chat, what the new question says replaces the earlier item" in prompt
    # Changed 2026-11-19: the period question rotates among her forms; this is a woman's form of one of them.
    assert new["messages"][1]["content"] in {f.woman for f in PERIOD_QUESTIONS}
    assert new["labels"]["gender"] == "woman"
    assert without_batch5_lines(prompt) == old["messages"][0]["content"]  # nothing else changed
    assert old["messages"][1]["content"] == "CLARIFY: azdak mn emta la emta?"  # the stored example is not touched


def test_the_neutral_form_goes_to_a_user_whose_gender_is_not_given_and_a_man_keeps_his():
    question, reply = "aya mahal 3am ehke?", "CLARIFY: aya mahal azdak?"
    assert rerender(old_example(NOT_GIVEN, question, reply))["messages"][1]["content"] == "CLARIFY: aya mahal bel zabt?"
    new = rerender(old_example(MAN, question, reply))
    assert new["messages"][1]["content"] == reply and "\nThe user is a man.\n" in new["messages"][0]["content"]


def test_earlier_replies_in_the_chat_take_the_users_form_too():
    history = (Exchange("aday sarafet hal fatra?", "CLARIFY: azdak mn emta la emta?"),)
    new = rerender(old_example(WOMAN, "mn 1 la 5 hal shaher", "SELECT 1", history))
    expected = for_gender("CLARIFY: azdak mn emta la emta?", Gender.WOMAN, "aday sarafet hal fatra?")
    assert expected in {f.woman for f in PERIOD_QUESTIONS}
    assert f"Question: aday sarafet hal fatra?\nReply: {expected}\n" in new["messages"][0]["content"]


def test_rebuilding_twice_gives_the_same_example():
    once = rerender(old_example(WOMAN, "shu?", "CLARIFY: shu baddak ta3ref bel zabt?"))
    assert rerender(once)["messages"][0]["content"] == once["messages"][0]["content"]


@pytest.mark.parametrize("change", [
    lambda p: p.replace("The user's vendors: ", "The user's vendors:  "),
    lambda p: p.replace("Reply:", "Answer:"),
    lambda p: p.replace("\n\nToday:", "\nToday:"),
    lambda p: p.replace("Rules:", "Rule:"),  # different instructions would be silently replaced
])  # fmt: skip
def test_a_prompt_not_in_build_prompts_form_is_refused(change):
    old = old_example(MAN, "aday sarafet?", "SELECT 1")
    old["messages"][0]["content"] = change(old["messages"][0]["content"])
    with pytest.raises(UnreadablePrompt):
        rerender(old)


# --- The user's own "I" words (Christina, 2026-11-19, table D) ---

from research.dataset.genders import question_for_gender  # noqa: E402

TABLE_D = [("def3a", "defe3"), ("defaa", "defe3"), ("7esa", "7eses"), ("7ase", "7ases"), ("7asi", "7ases"),
           ("hase", "hases"), ("hesa", "heses"), ("hasi", "hasis"), ("meshtreye", "meshtere"),
           ("meshtriye", "meshteri"), ("3ayshe", "3ayesh"), ("aayshe", "aayesh")]  # fmt: skip  # 7ase/7asi/hase/3ayshe: 2026-11-19


@pytest.mark.parametrize("woman, man", TABLE_D)
def test_a_mans_question_says_i_as_a_man(woman, man):
    assert question_for_gender(f"aday {woman} 3al khobez?", Gender.MAN) == f"aday {man} 3al khobez?"
    assert question_for_gender(f"aday {woman} 3al khobez?", Gender.WOMAN) == f"aday {woman} 3al khobez?"


@pytest.mark.parametrize("man, woman", [("defe3", "def3a"), ("7eses", "7esa"), ("heses", "hesa"), ("hasis", "hasi"),
                                        ("hases", "hase"), ("7ases", "7ase"), ("3ayesh", "3ayshe"), ("aayesh", "aayshe"),
                                        ("meshtere", "meshtreye"), ("meshteri", "meshtriye")])  # fmt: skip
def test_a_womans_question_says_i_as_a_woman(man, woman):
    assert question_for_gender(f"2ele aday {man} hal shaher", Gender.WOMAN) == f"2ele aday {woman} hal shaher"


def test_words_the_same_for_both_and_users_with_no_gender_keep_what_was_written():
    for gender in Gender:
        assert question_for_gender("aday dafa3et w dafa3it 3al benzine?", gender) == "aday dafa3et w dafa3it 3al benzine?"
    assert question_for_gender("aday def3a w defe3?", Gender.NOT_GIVEN) == "aday def3a w defe3?"


def test_only_whole_words_change_and_a_capital_stays():
    assert question_for_gender("Def3a kteer, def3aa?", Gender.MAN) == "Defe3 kteer, def3aa?"


def test_the_users_question_and_earlier_questions_take_the_speakers_form():
    history = (Exchange("aday def3a 3al lahme?", "SELECT 1"),)
    new = rerender(old_example(MAN, "w 3al khobez, aday def3a?", "SELECT 2", history))
    prompt = new["messages"][0]["content"]
    assert "Question: aday defe3 3al lahme?\nReply: SELECT 1" in prompt
    assert prompt.endswith("Question: w 3al khobez, aday defe3?\nReply:")


# --- the period question in her forms (2026-11-19; neutral forms approved the same day) ---

HER_PERIOD_FORMS = [  # (man, woman, neutral)
    ("CLARIFY: azdak mn emta la emta?", "CLARIFY: azdik mn emta la emta?", "CLARIFY: mn emta la emta bel zabt?"),
    ("CLARIFY: men aymata la aymata azdak?", "CLARIFY: men aymata la aymata azdik?",
     "CLARIFY: men aymata la aymata bel zabt?"),
    ("CLARIFY: 3an aya fatra 7abeb ta3ref?", "CLARIFY: 3an aya fatra 7abe ta3rfe?", "CLARIFY: 3an aya fatra bel zabt?"),
    ("CLARIFY: aan aya fatra baddak ta3rif?", "CLARIFY: aan aya fatra baddik ta3irfe?", "CLARIFY: 3an aya fatra bel zabt?"),
]  # fmt: skip


def test_the_period_question_rotates_among_her_forms_in_the_users_gender():
    questions = [f"aday sarafet hal fatra {n}?" for n in range(60)]
    for gender, column in ((Gender.MAN, 0), (Gender.WOMAN, 1), (Gender.NOT_GIVEN, 2)):
        used = {for_gender("CLARIFY: azdak mn emta la emta?", gender, q) for q in questions}
        assert used == {forms[column] for forms in HER_PERIOD_FORMS}


def test_the_same_question_always_gets_the_same_period_question():
    for gender in Gender:
        first = for_gender("CLARIFY: azdak mn emta la emta?", gender, "aday sarafet bi awal el shaher?")
        assert first == for_gender("CLARIFY: azdak mn emta la emta?", gender, "aday sarafet bi awal el shaher?")


# --- fixes by code to stored gold replies (2026-11-19) ---

from research.dataset.fixes import fixed_reply  # noqa: E402

OFTEN = ("SELECT ROUND(COUNT(DISTINCT receipt_id) / 3.0, 1) AS visits_per_month FROM receipts WHERE vendor = 'Car Spa' "
         "AND receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '3 months' AND receipt_date < "
         "date_trunc('month', CURRENT_DATE)")  # fmt: skip


def test_how_often_also_returns_the_visits_of_the_3_months():
    """Approved by Christina on 2026-11-19: '0.7 marra bel shaher' is not said; the count lets the answer say
    'martain bel 3 eshor el ekhrin'."""
    assert fixed_reply(OFTEN) == OFTEN.replace(
        "SELECT ROUND(", "SELECT COUNT(DISTINCT receipt_id) AS visits, ROUND(", 1)
    assert fixed_reply(fixed_reply(OFTEN)) == fixed_reply(OFTEN)


@pytest.mark.parametrize("reply", ["SELECT COUNT(DISTINCT receipt_id) AS visits FROM receipts WHERE vendor = 'X'",
                                   "CLARIFY: shu?", "UNSUPPORTED", "REPLY: Walaw"])  # fmt: skip
def test_other_replies_are_left_as_they_are(reply):
    assert fixed_reply(reply) == reply


def test_the_fix_reaches_the_answer_and_the_earlier_turns():
    history = (Exchange("aday 3am ru7 3a Car Spa?", OFTEN),)
    new = rerender(old_example(MAN, "w 3a Medco?", OFTEN, history))
    assert new["messages"][1]["content"] == fixed_reply(OFTEN)
    assert f"Reply: {fixed_reply(OFTEN)}\n" in new["messages"][0]["content"]


PRICE_CHANGE = ("SELECT latest.receipt_date AS latest_date, ROUND(latest.price, 2) AS latest_price, previous.receipt_date "
                "AS previous_date, ROUND(previous.price, 2) AS previous_price, ROUND((latest.price - previous.price) / "
                "NULLIF(previous.price, 0) * 100, 1) AS percent_change FROM (SELECT receipt_date, COALESCE(unit_price, "
                "line_total / quantity){per} AS price FROM purchases WHERE item_name = 'falafel'{unit} ORDER BY "
                "receipt_date DESC, receipt_id DESC LIMIT 1) AS latest, (SELECT receipt_date, COALESCE(unit_price, "
                "line_total / quantity){per} AS price FROM purchases WHERE item_name = 'falafel'{unit} ORDER BY "
                "receipt_date DESC, receipt_id DESC LIMIT 1 OFFSET 1) AS previous")  # fmt: skip


@pytest.mark.parametrize(("per", "unit"), [("", ""), (" / size_amount * 1000", " AND size_unit = 'g'")])
def test_a_price_change_compares_purchases_in_the_latest_ones_currency(per, unit):
    """Approved by Christina on 2026-11-19: 420,000 LBP against $4.20 gave +9,999,900%."""
    fixed = fixed_reply(PRICE_CHANGE.format(per=per, unit=unit))
    latest = (f"(SELECT currency FROM purchases WHERE item_name = 'falafel'{unit} ORDER BY receipt_date DESC, "
              "receipt_id DESC LIMIT 1)")  # fmt: skip
    assert fixed.startswith("SELECT latest.currency, latest.receipt_date AS latest_date, ")
    assert fixed.count(f"WHERE item_name = 'falafel'{unit} AND currency = {latest} ORDER BY") == 2
    assert fixed.count("SELECT receipt_date, currency, COALESCE(unit_price, line_total / quantity)") == 2
    assert fixed_reply(fixed) == fixed


def test_a_price_change_in_another_shape_is_refused_not_passed_on():
    with pytest.raises(ValueError, match="approved shape"):
        fixed_reply(PRICE_CHANGE.format(per="", unit="").replace("LIMIT 1 OFFSET 1", "LIMIT 2"))


def test_the_price_change_rule_now_says_the_same_currency_and_old_prompts_still_rebuild():
    from app.domain.assistant.prompt import INSTRUCTIONS
    from research.dataset.rerender import CHANGED_RULES

    before, now = CHANGED_RULES[0]
    assert now in INSTRUCTIONS and before not in INSTRUCTIONS and "in the same currency" in now
    old = old_example(MAN, "zed se3r el falafel?", PRICE_CHANGE.format(per="", unit=""))
    assert before in old["messages"][0]["content"]
    assert now in rerender(old)["messages"][0]["content"]


TOP_VISITED = ("SELECT vendor, COUNT(DISTINCT receipt_id) AS visits FROM receipts WHERE receipt_date >= "
               "date_trunc('month', CURRENT_DATE) AND receipt_date < date_trunc('month', CURRENT_DATE) + INTERVAL "
               "'1 month' GROUP BY vendor ORDER BY visits DESC LIMIT 1")  # fmt: skip


def test_the_shop_visited_most_leaves_out_bills_and_the_users_subscriptions():
    """Approved by Christina on 2026-11-19 (option B): one user's top shop was Anghami."""
    period = TOP_VISITED.split(" WHERE ", 1)[1].split(" GROUP BY")[0]
    assert fixed_reply(TOP_VISITED, ["Spinneys", "Anghami", "Netflix", "EDL"]) == (
        "SELECT vendor, COUNT(DISTINCT receipt_id) AS visits FROM category_spending WHERE category <> 'Utilities' "
        f"AND vendor NOT IN ('Netflix', 'Anghami') AND {period} GROUP BY vendor ORDER BY visits DESC LIMIT 1")
    assert fixed_reply(TOP_VISITED, ["Spinneys"]) == (
        "SELECT vendor, COUNT(DISTINCT receipt_id) AS visits FROM category_spending WHERE category <> 'Utilities' "
        f"AND {period} GROUP BY vendor ORDER BY visits DESC LIMIT 1")
    assert fixed_reply(fixed_reply(TOP_VISITED, ["Anghami"]), ["Anghami"]) == fixed_reply(TOP_VISITED, ["Anghami"])


def test_only_the_top_one_of_all_shops_changes():
    supermarkets = ("SELECT vendor, COUNT(DISTINCT receipt_id) AS visits FROM category_spending WHERE category = "
                    "'Groceries' AND receipt_date >= CURRENT_DATE - 7 GROUP BY vendor ORDER BY visits DESC LIMIT 1")
    all_shops = TOP_VISITED.removesuffix(" LIMIT 1")
    for reply in (supermarkets, all_shops):
        assert fixed_reply(reply, ["Anghami"]) == reply


def test_the_shop_rule_now_says_bills_and_subscriptions_are_not_visits():
    from app.domain.assistant.prompt import INSTRUCTIONS
    from research.dataset.rerender import CHANGED_RULES

    before, now = CHANGED_RULES[1]
    assert now in INSTRUCTIONS and "Bills and subscriptions are not visits" in now  # the old text begins the new
    old = old_example(MAN, "aya ma7al rehet aktar hal shaher?", TOP_VISITED)
    new = rerender(old)
    assert now in new["messages"][0]["content"]
    assert new["messages"][1]["content"] == fixed_reply(TOP_VISITED, NAMES.vendors)


def test_the_previous_purchase_is_still_the_one_before_the_latest():
    fixed = fixed_reply(PRICE_CHANGE.format(per="", unit=""))
    assert fixed.count("ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1 OFFSET 1) AS previous") == 1
    assert fixed.count("ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1) AS latest") == 1


def test_a_users_own_subscriptions_are_left_out_in_the_rebuilt_example():
    names = UserNames(items=["sushi"], vendors=["Spinneys", "Anghami"], categories=["Groceries", "Utilities"])
    prompt = without_batch5_lines(build_prompt("aya ma7al rehet aktar hal shaher?", names, TODAY, gender=Gender.MAN))
    old = {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": TOP_VISITED}],
           "labels": {"user": MAN, "language": "arabizi", "spec": "b3-x-1"}}  # fmt: skip
    assert "vendor NOT IN ('Anghami')" in rerender(old)["messages"][1]["content"]
