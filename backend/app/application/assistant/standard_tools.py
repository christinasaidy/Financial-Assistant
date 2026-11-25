"""The Standard mode's tools: the operations its model may ask for (2026-11-23; budgets 2026-11-25).

A tool is a typed backend operation: its input is checked here against its schema, it runs as the signed-in user
(the user id comes from the request, never from the model: no tool has a user field, and unknown fields are
refused), it reuses the services the screens use, and its output is bounded. The only writes are listed below.

- query_receipts: one SELECT over the three assistant views, through the same safety layers as Beta (the guard, the
  answering rules, the read-only role and its limits). One difference: the names it filters on are checked against
  ALL the user's confirmed receipts, not the 100 newest vendors the Beta prompt lists (a model-written name is never
  trusted: only a name found in the user's own data is let through).
- find_names: the user's exact spelling of a vendor, item or category, or similar names to ask about.
- get_receipt: one receipt and its lines.
- get_spending_summary: a month's totals by currency and category (SpendingService, as the Home screen shows them).
- get_budgets: a month's budgets and how much of each is used (BudgetService, as the Budgets screen shows them).
- save_memory, update_memory, forget_memory, search_memories: the user's memories, through MemoryService (the same
  rules as the memory endpoints).
- propose_budget, confirm_budget (2026-11-25): set or change a budget, confirmed first (the owner's decision).
  propose_budget checks the change and sets nothing; the answer must show its amount. confirm_budget sets it through
  BudgetService (as the Budgets screen does), and only with exactly the values the previous answer in the same
  conversation asked the user to confirm: never in the answer that asked, never with other values, never twice.
  Only from the current month onwards; removing a budget stays on the Budgets screen.
These are the only writes: memories and budgets, never receipts or anything else.

Results are JSON text for the model. Amounts stay exact (Decimal written as text), never rounded here.
"""

import json
import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal

from app.application.assistant.dtos import BudgetProposal, QueryResult, ToolCall, ToolSpec
from app.application.assistant.interfaces import QueryRules, ReadOnlyQueryRunner, SqlGuard
from app.application.assistant.memory_service import MemoryService, MemorySource
from app.application.budgets.budget_service import BudgetService
from app.application.budgets.dtos import SetBudgetRequest
from app.application.receipts.receipt_service import ReceiptService
from app.application.shared.unit_of_work import UnitOfWorkFactory
from app.application.spending.spending_service import SpendingService
from app.domain.assistant import answer as answers
from app.domain.assistant.errors import (
    InvalidMemory,
    MemoryNotFound,
    QueryFailed,
    QueryRejected,
    TooManyMemories,
    UnsafeQuery,
)
from app.domain.assistant.memory import Memory, MemoryKind
from app.domain.assistant.names import KnownName, MatchStatus, NameKind, match_name
from app.domain.assistant.prompt import UserNames
from app.domain.budgets.budget import validate_limit
from app.domain.budgets.errors import InvalidBudget
from app.domain.receipts.errors import ReceiptNotFound
from app.domain.shared.currency import Currency

logger = logging.getLogger(__name__)

TOOLS_VERSION = "standard-tools-2026-11-25.1"  # saved with every Standard answer, like the prompt's version
_AMOUNT = re.compile(r"\d{1,13}(\.\d{1,2})?")  # a budget amount as the model writes it: digits, no separators
MAX_RESULT_ROWS = 50  # rows of a query result shown to the model (the runner itself keeps at most 200)
MAX_RESULT_CHARACTERS = 12_000
MAX_RECEIPT_LINES = 100
INVENTORY_LIMIT = 5_000  # names looked through by find_names; a user with more is told the search was partial
MAX_NAME_LENGTH = 200
MAX_SQL_LENGTH = 4_000
_KINDS = {"items": NameKind.ITEM, "vendors": NameKind.VENDOR, "categories": NameKind.CATEGORY}


@dataclass(frozen=True)
class ToolContext:
    """What every tool call of one question shares."""

    today: date  # one date for the whole turn: the context the model was given and every query's CURRENT_DATE
    asked: str  # the user's earlier questions and this one, for the date rules
    conversation_id: int | None = None  # where a memory saved now was asked for
    question_message_id: int | None = None
    budget_proposals: tuple[BudgetProposal, ...] = ()  # what the previous answer asked to confirm


@dataclass(frozen=True)
class ToolOutcome:
    content: str  # JSON text for the model
    is_error: bool
    evidence: tuple[object, ...] = ()  # values the answer may quote (numbers are taken from them)
    receipt_ids: tuple[int, ...] = ()  # receipts the result is based on, when they can be listed
    sources_listed: bool | None = None  # None: not a data tool; False: data whose receipts cannot be listed
    record: dict = field(default_factory=dict)  # for the turn's execution record (never shown to the user)
    memory_written: bool = False  # a memory was saved, corrected or forgotten (or already saved as asked)
    budget_proposal: BudgetProposal | None = None  # a change this answer asks the user to confirm
    budget_written: bool = False  # a confirmed budget change was set


def _schema(properties: dict, required: Sequence[str]) -> dict:
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


_YEAR = {"type": "integer", "description": "The year, e.g. 2026"}
_MONTH = {"type": "integer", "description": "The month number, 1 to 12"}

SPECS = (
    ToolSpec(
        "query_receipts",
        "Run one read-only PostgreSQL SELECT over the user's confirmed receipts: the views receipts, purchases and "
        "category_spending described in your instructions. For totals, comparisons, rankings, lists and purchase "
        "history. Names must be the user's exact spellings. Returns columns, rows (at most 50 shown), whether the "
        "result was truncated, and the receipts it is based on when they can be worked out.",
        _schema({"sql": {"type": "string", "description": "One SELECT statement"}}, ["sql"]),
    ),
    ToolSpec(
        "find_names",
        "Find the user's exact spelling of a shop (vendor), item or category among all their confirmed receipts. "
        "Returns status found (with the exact name), ambiguous, suggestions (similar names to ask the user about; "
        "never treat one as found) or not_found.",
        _schema(
            {
                "kind": {"type": "string", "enum": [kind.value for kind in NameKind]},
                "name": {"type": "string", "description": "The name as the user wrote it"},
            },
            ["kind", "name"],
        ),
    ),
    ToolSpec(
        "get_receipt",
        "Get one of the user's receipts by its receipt_id: shop, date, currency, total, rate and every line.",
        _schema({"receipt_id": {"type": "integer"}}, ["receipt_id"]),
    ),
    ToolSpec(
        "get_spending_summary",
        "A month's confirmed spending: the total in each currency used, everything converted into one currency, "
        "and the split by category, exactly as the app's Home screen shows it.",
        _schema(
            {"year": _YEAR, "month": _MONTH, "currency": {"type": "string", "enum": [c.value for c in Currency],
                                                          "description": "The currency to convert everything into"}},
            ["year", "month", "currency"],
        ),  # fmt: skip
    ),
    ToolSpec(
        "get_budgets",
        "The user's budgets for a month: each category's limit, how much is spent and left, its state, and for "
        "the current month the pace (where spending ends up at this rate).",
        _schema({"year": _YEAR, "month": _MONTH}, ["year", "month"]),
    ),
    ToolSpec(
        "propose_budget",
        "Check a budget the user asked to set or change, and record it for them to confirm. It sets nothing. "
        "category is the category's exact name; limit_amount is digits only (e.g. 150 or 2500000), in currency; "
        "the amount applies from year/month onwards, this month or later. Returns the change and the budget it "
        "replaces. Then show the user the category, amount, currency and month and ask them to confirm.",
        _schema(
            {
                "category": {"type": "string"},
                "currency": {"type": "string", "enum": [c.value for c in Currency]},
                "limit_amount": {"type": "string"},
                "year": _YEAR,
                "month": _MONTH,
            },
            ["category", "currency", "limit_amount", "year", "month"],
        ),
    ),
    ToolSpec(
        "confirm_budget",
        "Set a budget change the user has just confirmed: only one your previous answer proposed (listed in the "
        "question's context), with exactly the same values. Only when their latest message clearly says yes.",
        _schema(
            {
                "category": {"type": "string"},
                "currency": {"type": "string", "enum": [c.value for c in Currency]},
                "limit_amount": {"type": "string"},
                "year": _YEAR,
                "month": _MONTH,
            },
            ["category", "currency", "limit_amount", "year", "month"],
        ),
    ),
    ToolSpec(
        "save_memory",
        "Save something the user explicitly asked you to remember. kind preference: how to answer them (text is the "
        'preference as a short sentence; alias, target_kind and target_name are ""). kind alias: their own name for '
        "one of their shops, items or categories (alias is their name; target_kind and target_name the exact name "
        'from their receipts; text is ""). Never amounts or other figures. Returns the saved memory.',
        _schema(
            {
                "kind": {"type": "string", "enum": [kind.value for kind in MemoryKind]},
                "text": {"type": "string"},
                "alias": {"type": "string"},
                "target_kind": {"type": "string", "enum": [*(kind.value for kind in NameKind), ""]},
                "target_name": {"type": "string"},
            },
            ["kind", "text", "alias", "target_kind", "target_name"],
        ),
    ),
    ToolSpec(
        "update_memory",
        'Correct a saved memory by its id: a preference gets a new text (target_name ""), an alias a new '
        'target_name, the user\'s exact name for it (text "").',
        _schema({"memory_id": {"type": "integer"}, "text": {"type": "string"}, "target_name": {"type": "string"}},
                ["memory_id", "text", "target_name"]),  # fmt: skip
    ),
    ToolSpec(
        "forget_memory",
        "Delete a saved memory by its id, when the user asks you to forget it.",
        _schema({"memory_id": {"type": "integer"}}, ["memory_id"]),
    ),
    ToolSpec(
        "search_memories",
        "Search the user's saved memories by words in them; an empty query lists them all (at most 20).",
        _schema({"query": {"type": "string"}}, ["query"]),
    ),
)


class StandardTools:
    """Runs the tools the Standard model asks for. Built once per process; holds no per-request state."""

    specs = SPECS

    def __init__(
        self,
        uow: UnitOfWorkFactory,
        guard: SqlGuard,
        rules: QueryRules,
        runner: ReadOnlyQueryRunner,
        spending: SpendingService,
        budgets: BudgetService,
        receipts: ReceiptService,
        clock: Callable[[], float] = time.perf_counter,
        *,
        memories: MemoryService | None = None,
    ) -> None:
        self._uow = uow
        self._guard = guard
        self._rules = rules
        self._runner = runner
        self._spending = spending
        self._budgets = budgets
        self._receipts = receipts
        self._clock = clock
        self._memories = memories
        self._handlers = {
            "query_receipts": self._query_receipts,
            "find_names": self._find_names,
            "get_receipt": self._get_receipt,
            "get_spending_summary": self._get_spending_summary,
            "get_budgets": self._get_budgets,
            "propose_budget": self._propose_budget,
            "confirm_budget": self._confirm_budget,
            "save_memory": self._save_memory,
            "update_memory": self._update_memory,
            "forget_memory": self._forget_memory,
            "search_memories": self._search_memories,
        }
        self._schemas = {spec.name: spec.input_schema for spec in SPECS}

    def run(self, user_id: int, call: ToolCall, context: ToolContext) -> ToolOutcome:
        """Run one call as `user_id`. An unknown tool or invalid input is refused without running anything; a
        refusal or failure comes back as an error result the model can read, never as an exception."""
        started = self._clock()
        record: dict = {"name": call.name, "input": _bounded_input(call.input)}
        handler = self._handlers.get(call.name)
        if handler is None:
            problem: str | None = f"There is no tool called {call.name!r}"
        else:
            problem = _invalid(self._schemas[call.name], call.input)
        if problem is not None:
            outcome = _error(problem, sources_listed=None)
        else:
            try:
                outcome = handler(user_id, call.input, context)
            except (UnsafeQuery, QueryRejected, QueryFailed) as exc:
                outcome = _error(str(exc), sources_listed=False)
            except (InvalidMemory, MemoryNotFound, TooManyMemories, InvalidBudget) as exc:
                outcome = _error(str(exc), sources_listed=None)
            except Exception as exc:  # a bug or the database down: the model is told, the turn goes on
                logger.exception("Standard tool %s failed", call.name)
                outcome = _error("The tool failed; this could not be checked", sources_listed=False,
                                 record={"exception": type(exc).__name__})  # fmt: skip
        record |= {"ok": not outcome.is_error, "duration_ms": round((self._clock() - started) * 1000)}
        record |= outcome.record
        if outcome.is_error:
            record["problem"] = json.loads(outcome.content)["error"]
        return replace(outcome, record=record)

    # --- the tools ---

    def _query_receipts(self, user_id: int, args: dict, context: ToolContext) -> ToolOutcome:
        sql = args["sql"].strip()
        if not sql or len(sql) > MAX_SQL_LENGTH:
            return _error(f"The SQL must be 1 to {MAX_SQL_LENGTH} characters", sources_listed=False)
        sql = self._guard.check(sql)
        literals = self._rules.named_literals(sql)
        with self._uow(user_id) as work:
            found = {kind: work.names.existing(_KINDS[kind], sorted(names)) for kind, names in literals.items()}
        unknown = {kind: sorted(literals[kind] - found[kind]) for kind in literals if literals[kind] - found[kind]}
        if unknown:
            listed = "; ".join(f"{kind}: {', '.join(repr(name) for name in names)}" for kind, names in unknown.items())
            return _error(
                f"Not the user's exact spelling ({listed}). Use find_names, or ask the user which they mean",
                sources_listed=False,
            )
        names = UserNames(items=sorted(found["items"]), vendors=sorted(found["vendors"]),
                          categories=sorted(found["categories"]))  # fmt: skip
        sql = self._rules.prepare(sql, names, context.today)  # loose matches, the clock, CURRENT_DATE -> the date
        self._rules.check_dates(sql, context.asked, context.today)
        result = self._runner.run(user_id, self._guard.check(sql))
        receipt_ids = self._sources(user_id, sql)
        shown, cut = _shown_rows(result)
        payload = {
            "columns": result.columns,
            "rows": [[_json_value(value) for value in row] for row in shown],
            "row_count": len(result.rows),
            "truncated": result.truncated or cut,
        }
        if result.truncated:
            payload["note"] = "More rows matched than the limit allows: this is only part of the result"
        elif cut:
            payload["note"] = f"Only the first {len(shown)} of {len(result.rows)} rows are shown"
        if answers.is_empty_result(result.rows):
            payload["note"] = "No confirmed receipt matched"
        totals = answers.column_totals(result.columns, shown)
        evidence = (*answers.result_numbers(shown), *totals.values(), Decimal(len(result.rows)),
                    *([Decimal(len(receipt_ids))] if receipt_ids is not None else []))  # fmt: skip
        record = {"sql": sql, "rows": len(result.rows), "truncated": payload["truncated"],
                  "receipts": None if receipt_ids is None else len(receipt_ids)}  # fmt: skip
        return ToolOutcome(_json(payload), False, evidence, receipt_ids or (), receipt_ids is not None, record)

    def _sources(self, user_id: int, sql: str) -> tuple[int, ...] | None:
        query = self._rules.sources_query(sql)
        if query is None:
            return None
        try:
            result = self._runner.run(user_id, self._guard.check(query))
        except (UnsafeQuery, QueryFailed) as exc:
            logger.warning("The source receipts of a Standard query could not be found: %s", exc)
            return None
        if result.truncated:  # a capped list is not every source: say they cannot be listed rather than undercount
            return None
        return tuple(int(row[0]) for row in result.rows if row[0] is not None)

    def _find_names(self, user_id: int, args: dict, context: ToolContext) -> ToolOutcome:
        kind = NameKind(args["kind"])
        name = args["name"].strip()
        if not name or len(name) > MAX_NAME_LENGTH:
            return _error(f"The name must be 1 to {MAX_NAME_LENGTH} characters", sources_listed=None)
        with self._uow(user_id) as work:
            known = work.names.inventory(kind, INVENTORY_LIMIT + 1)
        partial = len(known) > INVENTORY_LIMIT
        match = match_name(name, known[:INVENTORY_LIMIT])
        payload: dict = {"status": match.status.value, "names": [_known(entry) for entry in match.names]}
        notes = {
            MatchStatus.FOUND: "This is the user's exact spelling: use it in queries",
            MatchStatus.AMBIGUOUS: "More than one name has this spelling: ask the user which they mean",
            MatchStatus.SUGGESTIONS: "No name has this spelling. These are only similar names, not confirmed: ask "
            "the user which one they mean, if any",
            MatchStatus.NOT_FOUND: "No name with this or a similar spelling among the user's confirmed receipts. "
            "That does not prove they never bought there: it may be spelled differently or not confirmed yet",
        }
        payload["note"] = notes[match.status]
        if partial:
            payload["partial"] = f"Only the {INVENTORY_LIMIT} most recently used names were searched"
        record = {"status": match.status.value, "names": len(match.names), "partial": partial}
        return ToolOutcome(_json(payload), False, (), (), None, record)

    def _get_receipt(self, user_id: int, args: dict, context: ToolContext) -> ToolOutcome:
        receipt_id = args["receipt_id"]
        if receipt_id < 1:
            return _error("receipt_id must be a positive number", sources_listed=False)
        try:
            receipt = self._receipts.get(user_id, receipt_id).receipt
        except ReceiptNotFound:  # another user's receipt is "not found" too: row-level security hides it
            return _error("The user has no receipt with that id", sources_listed=False)
        with self._uow(user_id) as work:
            categories = {category.id: category.name for category in work.categories.list_all()}
        lines = receipt.lines[:MAX_RECEIPT_LINES]
        payload = {
            "receipt_id": receipt.id,
            "status": receipt.status.value,  # only a confirmed receipt counts in totals
            "vendor": receipt.vendor_name,
            "receipt_date": _json_value(receipt.receipt_date),
            "currency": _json_value(receipt.currency),
            "total": _json_value(receipt.total),
            "lbp_per_usd": _json_value(receipt.lbp_per_usd),
            "category": categories.get(receipt.primary_category_id) if receipt.primary_category_id else None,
            "lines": [
                {
                    "item": line.description,
                    "item_name": line.normalized_name,
                    "brand": line.brand,
                    "quantity": _json_value(line.quantity),
                    "unit_price": _json_value(line.unit_price),
                    "line_total": _json_value(line.line_total),
                    "size": None if line.size_amount is None else f"{_json_value(line.size_amount)} {line.size_unit}",
                    "category": categories.get(line.category_id) if line.category_id else None,
                }
                for line in lines
            ],
        }
        if len(receipt.lines) > len(lines):
            payload["note"] = f"Only the first {len(lines)} of {len(receipt.lines)} lines are shown"
        return ToolOutcome(_json(payload), False, (payload,), (receipt.id,), True, {"receipt_id": receipt.id})

    def _get_spending_summary(self, user_id: int, args: dict, context: ToolContext) -> ToolOutcome:
        problem = _check_month(args["year"], args["month"])
        if problem:
            return _error(problem, sources_listed=False)
        summary = self._spending.monthly_summary(user_id, args["year"], args["month"], Currency(args["currency"]))

        def part(entry) -> dict:
            return {
                "currency": entry.currency.value,
                "total": _json_value(entry.total),
                "receipt_count": entry.receipt_count,
                "categories": [{"name": c.name, "amount": _json_value(c.amount)} for c in entry.categories],
                "tax_discounts_and_rounding": _json_value(entry.adjustments),
            }

        payload = {
            "month": _json_value(summary.month),
            "combined": part(summary.combined),
            "by_currency": [part(entry) for entry in summary.by_currency],
            "receipts_awaiting_review": summary.awaiting_review,
            "converted_at_current_rate": summary.converted_at_current_rate,
            "current_lbp_per_usd": _json_value(summary.current_lbp_per_usd),
        }
        # The summary has no list of receipts, so its sources cannot be listed (never invented).
        return ToolOutcome(_json(payload), False, (payload,), (), False, {"month": payload["month"]})

    def _get_budgets(self, user_id: int, args: dict, context: ToolContext) -> ToolOutcome:
        problem = _check_month(args["year"], args["month"])
        if problem:
            return _error(problem, sources_listed=None)
        statuses = self._budgets.list_for_month(user_id, args["year"], args["month"])
        payload = {
            "budgets": [
                {
                    "category": status.category_name,
                    "currency": status.currency.value,
                    "limit": _json_value(status.limit_amount),
                    "spent": _json_value(status.spent),
                    "remaining": _json_value(status.remaining),
                    "percent_used": _json_value(status.percent_used),
                    "state": status.state.value,
                    "pace": None if status.pace is None else {
                        "projected": _json_value(status.pace.projected),
                        "projected_over": status.pace.projected_over,
                        "low_confidence": status.pace.low_confidence,
                    },
                }
                for status in statuses
            ]
        }  # fmt: skip
        if not statuses:
            payload["note"] = "The user has no budget for this month"
        return ToolOutcome(_json(payload), False, (payload,), (), False, {"budgets": len(statuses)})

    def _budget_change(self, user_id: int, args: dict, context: ToolContext) -> BudgetProposal | ToolOutcome:
        """The change asked for, checked (nothing is set here), or the error to give the model."""
        problem = _check_month(args["year"], args["month"])
        if problem:
            return _error(problem, sources_listed=None)
        if (args["year"], args["month"]) < (context.today.year, context.today.month):
            return _error("A budget set here starts this month or later; earlier months are changed on the Budgets "
                          "screen", sources_listed=None)  # fmt: skip
        amount = args["limit_amount"].strip()
        if not _AMOUNT.fullmatch(amount):
            return _error("limit_amount must be digits only (e.g. 150 or 2500000), with at most 2 decimals",
                          sources_listed=None)  # fmt: skip
        limit_amount = Decimal(amount)
        validate_limit(limit_amount)
        with self._uow(user_id) as work:
            categories = work.categories.list_all()
        wanted = args["category"].strip().casefold()
        found = [category for category in categories if category.name.casefold() == wanted]
        if len(found) != 1:
            names = ", ".join(sorted(category.name for category in categories))
            return _error(f"No category is called {args['category']!r}. The user's categories: {names}. Ask the "
                          "user which one they mean", sources_listed=None)  # fmt: skip
        return BudgetProposal(found[0].id, found[0].name, Currency(args["currency"]), limit_amount, args["year"],
                              args["month"])  # fmt: skip

    def _propose_budget(self, user_id: int, args: dict, context: ToolContext) -> ToolOutcome:
        change = self._budget_change(user_id, args, context)
        if isinstance(change, ToolOutcome):
            return change
        current = next((status for status in self._budgets.list_for_month(user_id, change.year, change.month)
                        if status.category_id == change.category_id), None)  # fmt: skip
        payload = {
            "proposed": _proposal(change),
            "replaces": None if current is None else {"currency": current.currency.value,
                                                      "limit": _json_value(current.limit_amount)},
            "note": "Nothing is set yet. Show the user this category, amount, currency and starting month, and ask "
            "them to confirm. Set it with confirm_budget only after they answer yes, with exactly these values.",
        }  # fmt: skip
        return ToolOutcome(_json(payload), False, (payload,), (), None, {"proposal": change.to_record()},
                           budget_proposal=change)  # fmt: skip

    def _confirm_budget(self, user_id: int, args: dict, context: ToolContext) -> ToolOutcome:
        if not context.budget_proposals:
            return _error("Your previous answer did not ask the user to confirm a budget change. Propose it with "
                          "propose_budget and ask them first", sources_listed=None)  # fmt: skip
        change = self._budget_change(user_id, args, context)
        if isinstance(change, ToolOutcome):
            return change
        if change not in context.budget_proposals:  # only what the user was shown and asked about
            waiting = "; ".join(_describe(p) for p in context.budget_proposals) or "none"
            return _error("These are not the values the user was asked to confirm in your previous answer (waiting: "
                          f"{waiting}). Propose the change with propose_budget and ask them first",
                          sources_listed=None)  # fmt: skip
        status = self._budgets.set_budget(user_id, SetBudgetRequest(change.category_id, change.year, change.month,
                                                                     change.currency, change.limit_amount))
        payload = {
            "set": _proposal(change),
            "this_month": {"spent": _json_value(status.spent), "remaining": _json_value(status.remaining),
                           "state": status.state.value},
        }  # fmt: skip
        return ToolOutcome(_json(payload), False, (payload,), (), None, {"set": change.to_record()},
                           budget_written=True)  # fmt: skip


    # --- memories ---

    def _memory_service(self) -> MemoryService:
        if self._memories is None:
            raise MemoryNotFound("Memories are not available")
        return self._memories

    def _save_memory(self, user_id: int, args: dict, context: ToolContext) -> ToolOutcome:
        source = None
        if context.conversation_id is not None and context.question_message_id is not None:
            source = MemorySource(context.conversation_id, context.question_message_id)
        service = self._memory_service()
        if args["kind"] == MemoryKind.PREFERENCE:
            if args["alias"] or args["target_kind"] or args["target_name"]:
                return _error("A preference has only a text: alias, target_kind and target_name must be empty",
                              sources_listed=None)  # fmt: skip
            saved = service.save_preference(user_id, args["text"], source)
        else:
            if not args["target_kind"]:
                return _error("An alias needs target_kind: vendor, item or category", sources_listed=None)
            saved = service.save_alias(user_id, args["alias"], NameKind(args["target_kind"]), args["target_name"],
                                       source)  # fmt: skip
        payload = {"saved": saved.created, "memory": _memory(saved.memory)}
        if not saved.created:
            payload["note"] = "This was already saved; nothing new was saved"
        record = {"memory_id": saved.memory.id, "created": saved.created}
        return ToolOutcome(_json(payload), False, (), (), None, record, memory_written=True)

    def _update_memory(self, user_id: int, args: dict, context: ToolContext) -> ToolOutcome:
        memory = self._memory_service().update(user_id, args["memory_id"], args["text"] or None,
                                               args["target_name"] or None)  # fmt: skip
        return ToolOutcome(_json({"updated": True, "memory": _memory(memory)}), False, (), (), None,
                           {"memory_id": memory.id}, memory_written=True)  # fmt: skip

    def _forget_memory(self, user_id: int, args: dict, context: ToolContext) -> ToolOutcome:
        self._memory_service().forget(user_id, args["memory_id"])
        return ToolOutcome(_json({"forgotten": True, "memory_id": args["memory_id"]}), False, (), (), None,
                           {"memory_id": args["memory_id"]}, memory_written=True)  # fmt: skip

    def _search_memories(self, user_id: int, args: dict, context: ToolContext) -> ToolOutcome:
        found = self._memory_service().search(user_id, args["query"])
        return ToolOutcome(_json({"memories": [_memory(m) for m in found]}), False, (), (), None,
                           {"found": len(found)})  # fmt: skip


# --- helpers ---


def memory_line(memory: Memory) -> str:
    """A memory as the turn's context lists it."""
    return f"- memory {memory.id} ({memory.kind.value}): {memory.text}"


def budget_line(proposal: BudgetProposal) -> str:
    """A change waiting for the user's answer, as the turn's context lists it."""
    return f"- {_describe(proposal)}"


def _describe(proposal: BudgetProposal) -> str:
    return (f"category {proposal.category!r}, {proposal.currency.value} {proposal.limit_amount} a month, from "
            f"{proposal.year}-{proposal.month:02d}")  # fmt: skip


def _proposal(change: BudgetProposal) -> dict:
    return {"category": change.category, "currency": change.currency.value, "limit": str(change.limit_amount),
            "from_month": f"{change.year}-{change.month:02d}"}  # fmt: skip


def _memory(memory: Memory) -> dict:
    found = {"id": memory.id, "kind": memory.kind.value, "text": memory.text}
    if memory.kind is MemoryKind.ALIAS:
        found |= {"alias": memory.alias, "target_kind": memory.target_kind.value, "target_name": memory.target_name}
    return found


def _error(problem: str, *, sources_listed: bool | None, record: dict | None = None) -> ToolOutcome:
    return ToolOutcome(_json({"error": problem}), True, (), (), sources_listed, record or {})


def _invalid(schema: dict, value: object) -> str | None:
    """Why `value` does not fit the tool's schema, or None. Only the features the schemas above use."""
    if not isinstance(value, dict):
        return "The input must be an object"
    properties = schema["properties"]
    extra = sorted(set(value) - set(properties))
    if extra:
        return f"Unknown input field(s): {', '.join(extra)}"
    missing = [name for name in schema["required"] if name not in value]
    if missing:
        return f"Missing input field(s): {', '.join(missing)}"
    for name, rule in properties.items():
        if name not in value:
            continue
        item = value[name]
        if rule["type"] == "string" and not isinstance(item, str):
            return f"{name} must be text"
        if rule["type"] == "integer" and (not isinstance(item, int) or isinstance(item, bool)):
            return f"{name} must be a whole number"
        if "enum" in rule and item not in rule["enum"]:
            return f"{name} must be one of: {', '.join(rule['enum'])}"
    return None


def _check_month(year: int, month: int) -> str | None:
    if not 2000 <= year <= 2100:
        return "year must be between 2000 and 2100"
    if not 1 <= month <= 12:
        return "month must be 1 to 12"
    return None


def _shown_rows(result: QueryResult) -> tuple[list[tuple], bool]:
    """The rows sent to the model: at most MAX_RESULT_ROWS and MAX_RESULT_CHARACTERS. True if some were left out."""
    shown: list[tuple] = []
    size = 0
    for row in result.rows[:MAX_RESULT_ROWS]:
        size += len(_json([_json_value(value) for value in row]))
        if size > MAX_RESULT_CHARACTERS and shown:
            break
        shown.append(row)
    return shown, len(shown) < len(result.rows)


def _known(entry: KnownName) -> dict:
    return {"name": entry.name, "receipts": entry.receipts, "last_used": _json_value(entry.last_used)}


def _json_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _bounded_input(value: object, limit: int = 2_000) -> object:
    """The model's input as saved in the execution record: kept whole unless it is very long."""
    text = _json(value)
    return value if len(text) <= limit else {"truncated": text[:limit]}
