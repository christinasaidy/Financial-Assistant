"""Corrections to stored gold replies, made by code when the mix is built (batch 5, from 2026-11-19).

The stored batches stay as they were reviewed; each fix rewrites one exact SQL shape, so it can only change the lines
it names, and the rebuild (rerender.py) applies it to every reply in an example (the answer and the chat's earlier
turns), so the model never sees the old shape next to the new one.

- "How often do I go to <shop>" (B13, batch 4): it returned only the visits per month (0.7), which no one says.
  It now also returns the visits of those 3 months, so the answer can say "martain bel 3 eshor el ekhrin"
  (approved by Christina on 2026-11-19). The per-month figure stays, as the prompt's rule asks.
"""

import re

_VISITS_PER_MONTH = re.compile(r"^SELECT ROUND\(COUNT\(DISTINCT receipt_id\) / 3\.0, 1\) AS visits_per_month FROM ")
_WITH_VISITS = "SELECT COUNT(DISTINCT receipt_id) AS visits, ROUND(COUNT(DISTINCT receipt_id) / 3.0, 1) AS visits_per_month FROM "



# - "Did the price of X go up" (B4, batch 3, 42 lines) compared the latest purchase with the one before it whatever
#   its currency (420,000 LBP against $4.20: +9,999,900%). Both purchases are now in the latest one's currency, which
#   is returned too (approved by Christina on 2026-11-19, with the prompt rule "in the same currency").
_PRICE_CHANGE = re.compile(
    r"\(SELECT receipt_date, (?P<price>COALESCE\(unit_price, line_total / quantity\)(?: / size_amount \* 1000)?) AS "
    r"price FROM purchases WHERE (?P<where>item_name = '(?:[^']|'')*'(?: AND size_unit = '[a-z]+')?) ORDER BY "
    r"receipt_date DESC, receipt_id DESC LIMIT 1(?P<offset> OFFSET 1)?\)")
_PRICE_CHANGE_START = "SELECT latest.receipt_date AS latest_date, "


def _same_currency(found: re.Match) -> str:
    where = found.group("where")
    latest_currency = f"(SELECT currency FROM purchases WHERE {where} ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1)"
    return (f"(SELECT receipt_date, currency, {found.group('price')} AS price FROM purchases WHERE {where} AND currency = "
            f"{latest_currency} ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1{found.group('offset') or ''})")


def _price_change(reply: str) -> str:
    if not reply.startswith(_PRICE_CHANGE_START) or " AND currency = " in reply:
        return reply
    fixed, count = _PRICE_CHANGE.subn(_same_currency, reply)
    if count != 2:
        raise ValueError(f"A price-change query not in the approved shape: {reply[:120]}")
    return "SELECT latest.currency, " + fixed.removeprefix("SELECT ")



# - "The shop I went to most" (all shops, the top one; 24 lines) counted a bill or a subscription as a visit (one
#   user's answer was Anghami). Bills are left out by their category (Utilities) and subscriptions by name, since
#   they often have no category of their own (approved by Christina on 2026-11-19, option B, with the prompt rule).
SUBSCRIPTION_VENDORS = ("Netflix", "Shahid", "Anghami", "Spotify")
_TOP_VISITED = re.compile(r"^SELECT vendor, COUNT\(DISTINCT receipt_id\) AS visits FROM receipts WHERE (?P<period>.+) "
                          r"GROUP BY vendor ORDER BY visits DESC LIMIT 1$")


def _quoted(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _top_visited(reply: str, vendors) -> str:
    found = _TOP_VISITED.match(reply)
    if not found:
        return reply
    theirs = [name for name in SUBSCRIPTION_VENDORS if name in vendors]
    listed = ", ".join(_quoted(name) for name in theirs)
    not_subscriptions = f" AND vendor NOT IN ({listed})" if theirs else ""
    return (f"SELECT vendor, COUNT(DISTINCT receipt_id) AS visits FROM category_spending WHERE category <> 'Utilities'"
            f"{not_subscriptions} AND {found.group('period')} GROUP BY vendor ORDER BY visits DESC LIMIT 1")


def fixed_reply(reply: str, vendors=()) -> str:
    """The gold reply with every approved fix applied (`vendors`: the user's, as the prompt lists them); any other
    reply is returned as it is."""
    return _top_visited(_price_change(_VISITS_PER_MONTH.sub(_WITH_VISITS, reply, count=1)), vendors)
