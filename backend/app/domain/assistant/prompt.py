"""What the language model is sent (assistant phase 3, approved by the user on 2026-11-03).

`build_prompt` is the one place the SQL step's prompt is made. The app uses it, and so will the scripts that write
the fine-tuning dataset, so the model is always trained on exactly what it is later sent. It holds:
- the instructions and the three assistant views;
- the user's own item, vendor and category names, so every filter can use an exact name;
- today's date and weekday, so a month or day named without a year can be placed ("in October");
- the recent chat (each earlier question with the SQL that answered it, never the numbers it showed);
- the question.
Relative dates ("this month") are written with CURRENT_DATE, which the backend replaces with the same date before
the query runs. Each example carries its own date, so it stays correct whenever it is used (decided with the user
on 2026-11-05, after the pilot showed that "October" cannot be answered without knowing the year).

The answer step's prompt (`build_answer_prompt`) is used only by the app.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.assistant.answer import read_reply
from app.domain.assistant.conversation import AnswerKind, Message, MessageRole, Step
from app.domain.assistant.errors import UnusableReply

# Written out rather than taken from the system's locale, so the prompt is the same on every machine.
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# Categories the views make up themselves, so they are valid even though no user created them.
VIEW_CATEGORIES = ("Uncategorized", "Tax, discounts & rounding")

INSTRUCTIONS = """You answer questions about the user's own shop receipts in Lebanon, asked in English or Arabizi.
Reply with exactly one of these, and nothing else:
- one PostgreSQL SELECT query that answers the question;
- CLARIFY: <a short question>, when the question is unclear, or names an item, shop or category the user does not have;
- UNSUPPORTED, when the receipts cannot answer it (budgets, predictions, prices in shops in general, anything else);
- REPLY: <a short reply>, for greetings, thanks, or "what can you do". Never state amounts in a REPLY.
Write CLARIFY and REPLY text in the language of the question.

The query may read only these three views. Each shows only this user's confirmed receipts.
receipts(receipt_id, receipt_date, vendor, currency, total, total_usd)
  one row per receipt. Use it for total spending and for counting receipts or visits.
purchases(receipt_id, receipt_date, vendor, item, item_name, category, quantity, unit_price, line_total,
          size_amount, size_unit, currency, line_total_usd, brand)
  one row per purchased line. item is the text printed on the receipt; item_name is what the product is.
  line_total is what was paid for the line, unit_price the price of one unit (may be null).
  size_amount and size_unit are the size of one unit in g, ml or pcs (null when not printed).
  brand is lower case (null when not printed).
category_spending(receipt_id, receipt_date, vendor, category, currency, amount, amount_usd)
  spending split by category; adds up to the receipts' totals. Use it for spending by category and for
  "where did my money go". Its 'Tax, discounts & rounding' category is the difference between a receipt's
  total and its lines.
currency is 'USD' or 'LBP'. Every amount also has a USD value (total_usd, line_total_usd, amount_usd) at the rate
saved with its receipt.

Rules:
- Filter items with item_name = '<name>', vendors with vendor = '<name>' and categories with category = '<name>',
  using a name exactly as listed below. Never use LIKE, ILIKE or a partial name: "water" is not "water heater".
- A kind of product that is not one of the user's categories (clothes, electronics, medicine, cleaning products,
  snacks): filter item_name IN the user's items of that kind, e.g. item_name IN ('t-shirt', 'socks'). Use
  category = '<name>' only for one of the user's own categories.
- Filter on brand = '<brand>' only when the user names a brand.
- For dates relative to today use CURRENT_DATE, for example this month:
  receipt_date >= date_trunc('month', CURRENT_DATE) AND receipt_date < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month'
  "Last week" is the previous Monday to Sunday:
  receipt_date >= date_trunc('week', CURRENT_DATE) - INTERVAL '1 week' AND receipt_date < date_trunc('week', CURRENT_DATE)
  "Today": receipt_date = CURRENT_DATE. "Yesterday": receipt_date = CURRENT_DATE - 1.
  "This week" is this Monday to Sunday:
  receipt_date >= date_trunc('week', CURRENT_DATE) AND receipt_date < date_trunc('week', CURRENT_DATE) + INTERVAL '1 week'
  "The last N days" is today and the N-1 days before it; "the last N weeks" is the last N*7 days, e.g. the last 7 days:
  receipt_date > CURRENT_DATE - 7 AND receipt_date <= CURRENT_DATE
  "The last N months" starts the day after the same date N months ago, e.g. the last 3 months:
  receipt_date > CURRENT_DATE - INTERVAL '3 months' AND receipt_date <= CURRENT_DATE
  "Since the start of the year" is this year so far: receipt_date >= date_trunc('year', CURRENT_DATE)
  A month or day named without a year means the most recent one up to today (asked in February, "October" is last
  year's October); write its dates out, e.g. receipt_date >= '2026-10-01' AND receipt_date < '2026-11-01'.
  The same for a weekday ("on Monday": the most recent Monday up to today), the weekend (Saturday and Sunday: this one
  if today is Saturday or Sunday, otherwise the last one) and summer (June to August). A range includes its first and
  last day: "1 to 15 October" is receipt_date >= '2026-10-01' AND receipt_date < '2026-10-16'.
  Never use now() or CURRENT_TIMESTAMP.
- In Arabizi, "jem3a" alone is a week ("hal jem3a" this week, "el jem3a li mar2it" last week); "nhar el jem3a" is
  Friday. "Kanoun el awal" is December and "kanoun el tene" January. Reply CLARIFY for "kanoun" alone, a semester, or
  "the start of the year" (bi awal el sene) without "since".
- To compare periods, return each period as the first day of its month: date_trunc('month', receipt_date) AS month,
  and GROUP BY it.
- Counting: "how many times", "how often" and "how many visits" count receipts: COUNT(DISTINCT receipt_id).
  "How many <items> did I buy" adds up the quantity: SUM(quantity). "How many receipts" counts receipts.
- For amounts, GROUP BY currency and return both the amount and its USD value, e.g.
  SELECT currency, SUM(amount) AS total_spent, SUM(amount_usd) AS total_spent_usd ... GROUP BY currency.
  If the user asks for dollars ("bel dollar"), return only the USD value.
- What the user paid for an item: the latest price, or the average and range, with vendor and date.
- A unit price is COALESCE(unit_price, line_total / quantity). Per kilo or litre: unit price / size_amount * 1000.
  Compare prices between shops per 100 g or 100 ml (unit price / size_amount * 100); per piece for sizes in pcs
  (unit price / size_amount); by unit price for lines with no size. Compare only lines with the same size_unit (or
  both without a size) and the same currency; also return how many purchases each figure is based on.
- "How many kilos / litres" is SUM(quantity * size_amount) FILTER (WHERE size_unit = 'g') / 1000 (or 'ml'); pieces
  are SUM(quantity * size_amount) FILTER (WHERE size_unit = 'pcs'), and a dozen is 12 pieces. Lines with no size
  are left out; also return COUNT(*) FILTER (WHERE size_amount IS NULL) AS purchases_without_size.
- Compute every difference, percentage or average in the query itself.
- Use earlier questions in the chat to fill in what a follow-up leaves out ("and last month?"), but never reuse
  numbers from earlier answers."""


@dataclass(frozen=True)
class UserNames:
    """The names a query may filter on, as the user's receipts spell them."""

    items: Sequence[str]
    vendors: Sequence[str]
    categories: Sequence[str]


@dataclass(frozen=True)
class Exchange:
    """An earlier question and how the assistant handled it: the SQL that answered it, or its own text."""

    question: str
    reply: str


def build_prompt(question: str, names: UserNames, today: date, history: Sequence[Exchange] = ()) -> str:
    parts = [
        INSTRUCTIONS,
        "",
        f"Today: {today.isoformat()} ({WEEKDAYS[today.weekday()]})",
        "The user's items: " + _quoted(names.items),
        "The user's vendors: " + _quoted(names.vendors),
        "The user's categories: " + _quoted(names.categories),
    ]
    if history:
        parts += ["", "Earlier in this chat:"]
        for exchange in history:
            parts += [f"Question: {exchange.question}", f"Reply: {exchange.reply}"]
    parts += ["", f"Question: {question}", "Reply:"]
    return "\n".join(parts)


def repair_prompt(prompt: str, previous_reply: str | None, problem: str) -> str:
    """The same prompt, with the reply that could not be used and why, for the one second attempt."""
    shown = previous_reply.strip() if previous_reply else "(no reply)"
    return (
        f"{prompt}\n{shown}\n\n"
        f"That reply could not be used: {problem}\n"
        "Reply again, following the rules above.\nReply:"
    )


def recent_exchanges(messages: Sequence[Message], max_exchanges: int, max_characters: int) -> list[Exchange]:
    """The chat to send with a new question (oldest first): at most `max_exchanges` earlier exchanges and
    `max_characters` of their text, dropping the oldest whole exchanges first.

    An exchange is a question followed by its answer. A question with no answer (the server stopped while
    answering) and an answer that failed are left out, since neither says anything about what was meant."""
    exchanges: list[Exchange] = []
    for question, answer in zip(messages, messages[1:]):
        if question.role is not MessageRole.USER or answer.role is not MessageRole.ASSISTANT:
            continue
        reply = _reply_of(answer)
        if reply is not None:
            exchanges.append(Exchange(question.content, reply))

    kept = exchanges[-max_exchanges:] if max_exchanges > 0 else []
    while kept and sum(len(e.question) + len(e.reply) for e in kept) > max_characters:
        kept.pop(0)
    return kept


def build_answer_prompt(
    question: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[object]],
    column_totals: dict[str, Decimal],
    receipt_count: int | None,
    truncated: bool,
    today: date,
) -> str:
    """The answer step: the model writes the answer from the query's result, in the question's language."""
    lines = [
        "Write the answer to the user's question about their own receipts, using only the query result below.",
        "Rules:",
        "- Write in the language of the question (English or Arabizi). One to three short sentences.",
        "- Use only numbers that appear below. Never compute new ones, and never guess.",
        "- Money: write USD as $12.50 and LBP as 1,450,000 LBP. Keep each currency separate. When there are",
        "  amounts in more than one currency, also give the combined total in USD (the total of the USD column),",
        "  as \"about $X in total\".",
        "- Dates: write them like 1 November 2026.",
        "- This is what the user paid on their own receipts, not shop prices in general. If sizes are missing,",
        "  say the sizes may differ.",
        "- You may comment briefly on the numbers when the question asks for it. Give no other advice.",
    ]
    if truncated:
        lines.append(f"- The result was cut off: only the first {len(rows)} rows are shown. Say so.")
    lines += [
        "",
        f"Today: {today.isoformat()}",
        f"Question: {question}",
        "Result columns: " + " | ".join(columns),
    ]
    lines += ["Row: " + " | ".join(_shown(value) for value in row) for row in rows]
    if column_totals:
        lines.append(
            "Column totals: " + ", ".join(f"{name} = {_shown(total)}" for name, total in column_totals.items())
        )
    if receipt_count is not None:
        lines.append(f"Number of receipts used: {receipt_count}")
    lines += ["", "Answer:"]
    return "\n".join(lines)


def answer_repair_prompt(prompt: str, previous_answer: str | None, problem: str) -> str:
    shown = previous_answer.strip() if previous_answer else "(no answer)"
    return f"{prompt}\n{shown}\n\nThat answer could not be used: {problem}\nWrite it again.\nAnswer:"


def _reply_of(answer: Message) -> str | None:
    details = answer.details
    if details is None or details.kind is AnswerKind.ERROR:
        return None
    if details.kind is AnswerKind.ANSWER:
        # The SQL as the model wrote it (with CURRENT_DATE), not as it ran (with the date filled in), so the
        # history looks like the training examples. Answers saved before phase 3 only have the SQL that ran.
        written = next((a.output for a in reversed(details.attempts) if a.step is Step.SQL and a.problem is None
                        and a.output), None)  # fmt: skip
        if written is None:
            return details.sql
        try:
            return read_reply(written).text
        except UnusableReply:
            return details.sql
    if details.kind is AnswerKind.UNSUPPORTED:
        return "UNSUPPORTED"
    return answer.content  # a clarifying question or a short reply, as it was shown


def _quoted(names: Sequence[str]) -> str:
    return ", ".join(f'"{name}"' for name in names) or "(none yet)"


def _shown(value: object) -> str:
    """A value as the model sees it: amounts as stored (8.00), longer figures to the cent (16.2011 as 16.20, 1000.000
    as 1000), dates as YYYY-MM-DD, nothing as 'null'."""
    if value is None:
        return "null"
    if isinstance(value, Decimal):
        if not value.is_finite() or value.as_tuple().exponent >= -2:
            return str(value)
        if value == value.to_integral_value():
            return str(value.quantize(Decimal(1)))
        cents = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if cents == 0:  # a small figure such as a price per ml: keep enough places to be meaningful
            return str(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        return str(cents)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
