"""The prompts and the chat history sent with a question. Decisions approved by the user on 2026-11-03; do not
change an expected value to make a test pass."""

from datetime import date, datetime, timezone
from decimal import Decimal

from app.domain.assistant.conversation import AnswerDetails, AnswerKind, Attempt, Message, MessageRole, Step
from app.domain.assistant.prompt import (
    GENDER_LINES,
    Exchange,
    Gender,
    UserNames,
    build_answer_prompt,
    build_prompt,
    recent_exchanges,
    repair_prompt,
)

NAMES = UserNames(items=["laban", "water", "water heater"], vendors=["Spinneys", "Carrefour"],
                  categories=["Groceries", "Dining", "Uncategorized", "Tax, discounts & rounding"])  # fmt: skip
_ids = iter(range(1, 10**6))
TODAY = date(2026, 11, 3)


def question(text: str) -> Message:
    return Message(next(_ids), MessageRole.USER, text, datetime(2026, 11, 3, tzinfo=timezone.utc))


def reply(content: str, kind: AnswerKind = AnswerKind.ANSWER, sql: str | None = None) -> Message:
    return Message(next(_ids), MessageRole.ASSISTANT, content, datetime(2026, 11, 3, tzinfo=timezone.utc),
                   AnswerDetails(kind, sql=sql))  # fmt: skip


# --- The SQL step's prompt (round 2, Q6) ---


def test_the_prompt_has_the_views_the_users_names_the_chat_and_the_question_last():
    history = [Exchange("How much did I spend on groceries this month?", "SELECT 1")]
    prompt = build_prompt("and last month?", NAMES, TODAY, history, gender=Gender.NOT_GIVEN)

    for view in ("receipts(receipt_id", "purchases(receipt_id", "category_spending(receipt_id"):
        assert view in prompt
    assert 'The user\'s items: "laban", "water", "water heater"' in prompt
    assert 'The user\'s vendors: "Spinneys", "Carrefour"' in prompt
    assert '"Tax, discounts & rounding"' in prompt
    assert "Question: How much did I spend on groceries this month?\nReply: SELECT 1" in prompt
    assert prompt.endswith("Question: and last month?\nReply:")


def test_the_prompt_gives_the_date_and_weekday_it_was_asked_on():
    """Changed with the user on 2026-11-05 (it used to hold no date): "October" needs the year, so the date and
    weekday are part of the input; relative dates still use CURRENT_DATE."""
    prompt = build_prompt("how much in October?", NAMES, date(2025, 1, 31), gender=Gender.NOT_GIVEN)
    assert "Today: 2025-01-31 (Friday)" in prompt
    assert date.today().isoformat() not in prompt  # the date given, never the computer's clock
    assert "CURRENT_DATE" in prompt
    assert "A month or day named without a year means the most recent one up to today" in prompt


def test_the_prompt_states_the_users_gender_after_the_date():
    """Decided with the user on 2026-11-17 (batch 5): woman, man or not given; the app sends not given until sign-up
    asks for it."""
    lines = {gender: build_prompt("kifak?", NAMES, TODAY, gender=gender).splitlines() for gender in Gender}
    assert "The user is a woman." in lines[Gender.WOMAN]
    assert "The user is a man." in lines[Gender.MAN]
    assert "The user's gender is not given." in lines[Gender.NOT_GIVEN]
    for gender, prompt_lines in lines.items():
        today = prompt_lines.index("Today: 2026-11-03 (Tuesday)")
        assert prompt_lines[today + 1].startswith("The user")
        assert sum(line.startswith(("The user is a", "The user's gender")) for line in prompt_lines) == 1


def test_the_rules_say_a_new_question_replaces_what_it_names_and_keeps_what_it_leaves_out():
    """The prompt line approved by the user on 2026-11-18 (her R6 decision), next to the follow-up rule."""
    prompt = build_prompt("tab w aday saref 3a l akel?", NAMES, TODAY, gender=Gender.NOT_GIVEN)
    follow_up = prompt.index("Use earlier questions in the chat to fill in what a follow-up leaves out")
    rule = prompt.index("In a chat, what the new question says replaces the earlier item, shop, period or measure;"
                        " what it leaves out\n  comes from the earlier question.")  # fmt: skip
    assert follow_up < rule < prompt.index("Today:")


def test_a_user_with_no_receipts_gets_empty_lists():
    prompt = build_prompt("hi", UserNames([], [], ["Groceries"]), TODAY, gender=Gender.NOT_GIVEN)
    assert "The user's items: (none yet)" in prompt


def test_a_repair_shows_the_reply_that_failed_and_why():
    prompt = build_prompt("water?", NAMES, TODAY, gender=Gender.NOT_GIVEN)
    repaired = repair_prompt(prompt, "SELECT 1 FROM purchases WHERE item_name ILIKE '%water%'", "Item names must match")
    assert repaired.startswith(prompt)
    assert "ILIKE '%water%'" in repaired and "Item names must match" in repaired
    assert repaired.endswith("Reply:")


# --- The chat history (round 1, Q9; round 3, Q11) ---


def test_the_sql_is_sent_as_the_model_wrote_it_with_current_date():
    written = "SELECT SUM(total) FROM receipts WHERE receipt_date >= date_trunc('month', CURRENT_DATE)"
    ran = "SELECT SUM(total) FROM receipts WHERE receipt_date >= DATE_TRUNC('MONTH', CAST('2026-11-03' AS DATE))"
    details = AnswerDetails(AnswerKind.ANSWER, sql=ran, attempts=(
        Attempt(Step.SQL, "m", "SELECT 1 FROM receipt_items", "Only the receipts, ... views can be queried"),
        Attempt(Step.SQL, "m", f"```sql\n{written}\n```"),
        Attempt(Step.ANSWER, "m", "You spent $22.00 this month."),
    ))  # fmt: skip
    answer = Message(next(_ids), MessageRole.ASSISTANT, "You spent $22.00 this month.",
                     datetime(2026, 11, 3, tzinfo=timezone.utc), details)  # fmt: skip
    assert recent_exchanges([question("this month?"), answer], 6, 6000) == [Exchange("this month?", written)]


def test_each_exchange_is_the_question_and_the_sql_never_the_numbers_shown():
    messages = [question("groceries this month?"), reply("You spent $8.00.", sql="SELECT 8"), question("and last?")]
    assert recent_exchanges(messages, 6, 6000) == [Exchange("groceries this month?", "SELECT 8")]


def test_clarify_reply_and_unsupported_are_sent_with_their_prefix_and_failures_are_left_out():
    """Changed requirement, approved by the user on 2026-11-17 (it used to send the bare text): a clarifying question
    or short reply keeps its CLARIFY: / REPLY: prefix, as in training, so the model can tell its own question from
    an answer."""
    messages = [
        question("milk?"), reply("Did you mean laban?", AnswerKind.CLARIFY),
        question("hi"), reply("Hi! Ask me about your spending.", AnswerKind.REPLY),
        question("budget?"), reply("I can answer ...", AnswerKind.UNSUPPORTED),
        question("???"), reply("Sorry, I couldn't answer that.", AnswerKind.ERROR),
    ]  # fmt: skip
    assert recent_exchanges(messages, 6, 6000) == [
        Exchange("milk?", "CLARIFY: Did you mean laban?"),
        Exchange("hi", "REPLY: Hi! Ask me about your spending."),
        Exchange("budget?", "UNSUPPORTED"),
    ]


def test_an_answered_clarify_reaches_the_prompt_as_the_model_wrote_it():
    messages = [question("aday sarafet bi awal el shaher?"), reply("azdik mn emta la emta?", AnswerKind.CLARIFY)]
    prompt = build_prompt("mn 1 la 5 hal shaher", NAMES, TODAY, recent_exchanges(messages, 6, 6000),
                          gender=Gender.WOMAN)  # fmt: skip
    assert ("Question: aday sarafet bi awal el shaher?\nReply: CLARIFY: azdik mn emta la emta?\n\n"
            "Question: mn 1 la 5 hal shaher\nReply:") in prompt  # fmt: skip


def test_a_question_left_without_an_answer_is_skipped():
    messages = [question("lost"), question("groceries?"), reply("$8", sql="SELECT 8"), question("now")]
    assert recent_exchanges(messages, 6, 6000) == [Exchange("groceries?", "SELECT 8")]


def test_at_most_six_exchanges_the_oldest_dropped_first():
    messages = []
    for n in range(8):
        messages += [question(f"q{n}"), reply("x", sql=f"SELECT {n}")]
    kept = recent_exchanges(messages, 6, 6000)
    assert [e.question for e in kept] == ["q2", "q3", "q4", "q5", "q6", "q7"]


def test_the_character_cap_drops_whole_exchanges_oldest_first():
    messages = [question("a" * 50), reply("x", sql="S" * 50), question("b" * 10), reply("x", sql="T" * 10)]
    assert recent_exchanges(messages, 6, 99) == [Exchange("b" * 10, "T" * 10)]
    assert len(recent_exchanges(messages, 6, 120)) == 2


# --- The answer step's prompt ---


def test_the_answer_prompt_shows_amounts_to_the_cent_and_the_usd_total():
    prompt = build_answer_prompt(
        "and last month?",
        ["currency", "total_spent", "total_spent_usd"],
        [("USD", Decimal("13.50"), Decimal("13.50")), ("LBP", Decimal("1450000.00"), Decimal("16.2011173184"))],
        {"total_spent_usd": Decimal("29.7011173184")},
        3,
        False,
        date(2026, 11, 3),
        gender=Gender.NOT_GIVEN,
    )
    assert "Row: LBP | 1450000.00 | 16.20" in prompt  # stored amounts as they are
    assert "Column totals: total_spent_usd = 29.70" in prompt
    assert "Number of receipts used: 3" in prompt
    assert "Today: 2026-11-03" in prompt
    assert "cut off" not in prompt


def test_the_answer_prompt_states_the_users_gender_after_the_date():
    """Decided with the user on 2026-11-17: the gender line in both prompts (batch 5 trains the answer step)."""
    for gender in Gender:
        lines = build_answer_prompt("aday sarafet?", ["total"], [(Decimal("1.00"),)], {}, None, False,
                                    date(2026, 11, 3), gender=gender).splitlines()  # fmt: skip
        today = lines.index("Today: 2026-11-03")
        assert lines[today + 1] == GENDER_LINES[gender] and lines[today + 2] == "Question: aday sarafet?"


def test_small_figures_keep_enough_places_and_a_cut_off_result_is_announced():
    prompt = build_answer_prompt("price per ml?", ["per_ml"], [(Decimal("0.00375"),)] * 3, {}, None, True,
                                 date(2026, 11, 3), gender=Gender.NOT_GIVEN)  # fmt: skip
    assert "Row: 0.0038" in prompt
    assert "only the first 3 rows are shown" in prompt
    assert "Number of receipts used" not in prompt  # unknown (e.g. a UNION): not claimed


def test_the_prompt_states_the_week_and_price_conventions():
    prompt = build_prompt("how much last week?", NAMES, TODAY, gender=Gender.NOT_GIVEN)
    assert '"Last week" is the previous Monday to Sunday' in prompt  # approved 2026-11-05
    assert "per 100 g or 100 ml (unit price / size_amount * 100)" in prompt  # decision 8, 2026-11-07


def test_the_prompt_states_the_period_and_counting_conventions():  # approved 2026-11-05, after the pilot
    prompt = build_prompt("did I spend more this month or last?", NAMES, TODAY, gender=Gender.NOT_GIVEN)
    assert "return each period as the first day of its month: date_trunc('month', receipt_date) AS month" in prompt
    assert '"how many times", "how often" and "how many visits" count receipts: COUNT(DISTINCT receipt_id)' in prompt
    assert '"How many <items> did I buy" adds up the quantity: SUM(quantity)' in prompt


# --- Periods, sizes and comparisons (approved 2026-11-07, worked examples with today 2027-02-10) ---


def test_the_prompt_states_the_rolling_periods_with_current_date():
    prompt = build_prompt("adde sarafet ekher 7 iyem?", NAMES, TODAY, gender=Gender.NOT_GIVEN)
    assert '"Today": receipt_date = CURRENT_DATE. "Yesterday": receipt_date = CURRENT_DATE - 1.' in prompt
    assert ("\"This week\" is this Monday to Sunday:\n  receipt_date >= date_trunc('week', CURRENT_DATE) AND "
            "receipt_date < date_trunc('week', CURRENT_DATE) + INTERVAL '1 week'") in prompt  # fmt: skip
    assert '"The last N days" is today and the N-1 days before it; "the last N weeks" is the last N*7 days' in prompt
    assert "receipt_date > CURRENT_DATE - 7 AND receipt_date <= CURRENT_DATE" in prompt
    assert '"The last N months" starts the day after the same date N months ago' in prompt
    assert "receipt_date > CURRENT_DATE - INTERVAL '3 months' AND receipt_date <= CURRENT_DATE" in prompt
    assert "\"Since the start of the year\" is this year so far: receipt_date >= date_trunc('year', CURRENT_DATE)" in prompt


def test_the_prompt_states_the_named_periods_written_out():
    prompt = build_prompt("adde sarafet hal weekend?", NAMES, TODAY, gender=Gender.NOT_GIVEN)
    assert '"on Monday": the most recent Monday up to today' in prompt
    assert "the weekend (Saturday and Sunday: this one\n  if today is Saturday or Sunday, otherwise the last one)" in prompt
    assert "summer (June to August)" in prompt
    assert ("A range includes its first and\n  last day: \"1 to 15 October\" is receipt_date >= '2026-10-01' AND "
            "receipt_date < '2026-10-16'.") in prompt  # fmt: skip


def test_the_prompt_states_the_arabizi_period_words_and_when_to_ask_back():
    prompt = build_prompt("adde sarafet bi kanoun?", NAMES, TODAY, gender=Gender.NOT_GIVEN)
    assert '"jem3a" alone is a week ("hal jem3a" this week, "el jem3a li mar2it" last week); "nhar el jem3a" is\n  Friday.' in prompt
    assert '"Kanoun el awal" is December and "kanoun el tene" January.' in prompt
    assert ('Reply CLARIFY for "kanoun" alone, a semester, or\n  "the start of the year" (bi awal el sene) '
            'without "since".') in prompt  # fmt: skip


def test_the_prompt_states_the_unit_price_and_size_conventions():
    prompt = build_prompt("kam kilo rez jebt?", NAMES, TODAY, gender=Gender.NOT_GIVEN)
    assert "A unit price is COALESCE(unit_price, line_total / quantity). Per kilo or litre: unit price / size_amount * 1000." in prompt
    assert "per 100 g or 100 ml (unit price / size_amount * 100); per piece for sizes in pcs" in prompt
    assert "by unit price for lines with no size" in prompt
    assert "Compare only lines with the same size_unit (or\n  both without a size) and the same currency" in prompt
    assert "SUM(quantity * size_amount) FILTER (WHERE size_unit = 'g') / 1000" in prompt
    assert "a dozen is 12 pieces" in prompt
    assert "COUNT(*) FILTER (WHERE size_amount IS NULL) AS purchases_without_size" in prompt


def test_the_prompt_states_how_to_filter_a_kind_of_product():  # approved 2026-11-07
    prompt = build_prompt("adde sarafet 3al tyeb hal shaher?", NAMES, TODAY, gender=Gender.NOT_GIVEN)
    assert ("- A kind of product that is not one of the user's categories (clothes, electronics, medicine, cleaning "
            "products,\n  snacks): filter item_name IN the user's items of that kind, e.g. item_name IN ('t-shirt', "
            "'socks'). Use\n  category = '<name>' only for one of the user's own categories.") in prompt  # fmt: skip


def test_the_prompt_states_the_batch3_conventions():  # approved 2026-11-15, worked examples with today 2027-02-10
    prompt = build_prompt("3edele kel shi sarafto abel mbere7", NAMES, TODAY, gender=Gender.NOT_GIVEN)
    assert '"The day before yesterday": receipt_date = CURRENT_DATE - 2.' in prompt
    assert ('"Since <a weekday>" (and "<weekday> el madi") is the most recent such day before today, never today '
            '(asked\n  on a Tuesday, "since Tuesday" starts last week\'s Tuesday), up to today: '
            "receipt_date >= '<that date>'.\n  \"Since yesterday\": receipt_date >= CURRENT_DATE - 1.") in prompt  # fmt: skip
    assert 'Reply CLARIFY for "lately" (hal fatra) with no period.' in prompt
    assert ("- A kind of shop: restaurants are the vendors of Dining spending, supermarkets of Groceries spending; use\n"
            "  category_spending, e.g. COUNT(DISTINCT receipt_id) ... WHERE category = 'Dining'.") in prompt  # fmt: skip
    # Changed requirement, approved by the user on 2026-11-19 (batch 5): bills and subscriptions are not visits.
    assert ('- "The shop I went to most" counts visits, COUNT(DISTINCT receipt_id) per vendor, most first; "the shop I '
            "spent\n  most at\" adds up money. Bills and subscriptions are not visits: leave out category = 'Utilities' "
            "and the\n  user's Netflix, Shahid, Anghami or Spotify, e.g. FROM category_spending WHERE category <> "
            "'Utilities' AND\n  vendor NOT IN ('Anghami').") in prompt  # fmt: skip
    assert ('- "List what I bought / spent": the purchases, with receipt_date, vendor, item_name, currency and '
            "line_total, by\n  date.") in prompt  # fmt: skip
    assert ("- The cheapest or priciest shop for an item, with no shops named: compare every shop it was bought at "
            "(the same\n  per-size rules), cheapest first.") in prompt  # fmt: skip
    assert ('- "For the same brand" at two shops: group by brand and vendor, keeping only brands bought at both.'
            in prompt)  # fmt: skip
    # Changed requirement, approved by the user on 2026-11-19 (batch 5): the two purchases are in the same currency
    # (the rule had compared 420,000 LBP with $4.20), and the currency is returned.
    assert ('- A price change ("did the price go up, by how much, in percent"): the latest purchase against the one '
            "before\n  it in the same currency, per kilo or litre when it has a size in g or ml, otherwise by unit price; "
            "return the\n  currency, both prices, their dates and the percent change. \"The average price went down\" "
            "compares this month's\n  average with last month's.") in prompt  # fmt: skip
    assert ('- "Since when have I been buying X": the first purchase\'s date, and how many times since.' in prompt)
    assert ('- "How much / how many do I usually buy a month": the last 3 complete months added up and divided by 3 '
            "(months\n  with none count as 0).") in prompt  # fmt: skip


def test_the_prompt_states_the_batch4_conventions():  # approved 2026-11-16, worked examples with today 2028-01-12
    prompt = build_prompt("aymata ekher mara akalet sushi", NAMES, TODAY, gender=Gender.NOT_GIVEN)
    assert ('  "Last year" (el sene el madye, el sene li mar2it) is the previous calendar year:\n'
            "  receipt_date >= date_trunc('year', CURRENT_DATE) - INTERVAL '1 year' AND receipt_date < "
            "date_trunc('year', CURRENT_DATE)\n") in prompt  # fmt: skip
    assert ('  "The last N years" works like the last N months ("mn sentain la hala2", "ekher sentain": the last 2 '
            "years).\n") in prompt  # fmt: skip
    assert '  "The last few weeks" (ekher kam jem3a) is the last 3 weeks.\n' in prompt
    assert ('  "Since summer" (mn el sayfiye) starts on 1 June of the most recent summer: '
            "receipt_date >= '<that date>'.\n") in prompt  # fmt: skip
    assert '  Reply CLARIFY for "the beginning of the month" (bi awal el shaher).\n' in prompt
    assert ('  "How often do I go to <shop>" with no period is visits per month: the last 3 complete months\' visits '
            "divided by 3.\n") in prompt  # fmt: skip
    assert "  A pharmacy (pharmacie): vendor IN the user's shops whose name says Pharmacie.\n" in prompt
    assert '- "When was the last time I bought X / went to <shop>": the latest date, MAX(receipt_date).\n' in prompt
    assert ('- "When did I go to <shop> / buy X" in a period: list the dates (receipt_date, vendor), by date.\n'
            in prompt)  # fmt: skip
    assert ("- A summary of a period (tolkhis, telkhis, mlakhas, lakhesle) is spending by category for that "
            "period.\n") in prompt  # fmt: skip


def test_the_prompt_states_the_brand_conventions():  # approved 2026-11-16
    prompt = build_prompt("aya brand roz arkhasle?", NAMES, TODAY, gender=Gender.NOT_GIVEN)
    assert ('- The cheapest brand of an item ("aya brand / aya naw3 X arkhas / awfar"): compare every brand it was '
            "bought in\n  (the same per-size rules), cheapest first; leave out lines with no brand.\n") in prompt  # fmt: skip
    assert ("- Which brand or kind is better (ahsan, afdal): reply CLARIFY; receipts show prices, not quality.\n"
            in prompt)  # fmt: skip
