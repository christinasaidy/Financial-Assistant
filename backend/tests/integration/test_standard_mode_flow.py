"""The Standard mode end to end against the real database (2026-11-23): the API, the turn, the real tools (the
guard, the answering rules, the read-only role, row-level security, the spending and budget services) and the saved
answer. Only the model is scripted: by a ScriptedChatModel, or by the real Anthropic adapter talking to a fake HTTP
server. So these tests prove the plumbing and the data boundaries, never what a real model would answer, and they
make no paid call.

AC-07 isolation, AC-08 SQL boundaries, AC-09 old names, AC-10 ambiguity, AC-15 evidence, plus Phase 2's "done": a
mocked Sonnet tool call completes through the real application and saves an answer.
"""

import json
import uuid
from datetime import date
from decimal import Decimal

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.app import create_app
from app.application.assistant.dtos import ToolCall
from app.application.assistant.standard_tools import StandardTools, ToolContext
from app.domain.assistant import answer as answers
from app.infrastructure.config import Settings
from app.infrastructure.database.connection import create_db_engine
from app.infrastructure.database.readonly_query_runner import SqlReadOnlyQueryRunner
from app.infrastructure.database.unit_of_work import SqlUnitOfWorkFactory
from app.infrastructure.language_model.anthropic_chat_model import AnthropicChatModel
from app.infrastructure.sql.query_rules import SqlGlotQueryRules
from app.infrastructure.sql.sql_guard import SqlGlotGuard
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.integration.conftest import forget_usage_by_email
from tests.fakes import FakeAssistantModel, FakeReceiptExtractor, ScriptedChatModel, calls, says

TODAY = date(2026, 11, 23)
THIS_MONTH = TODAY.replace(day=1)
SPINNEYS_SQL = ("SELECT currency, SUM(total) AS spent, SUM(total_usd) AS spent_usd FROM receipts "
                "WHERE vendor = 'Spinneys' GROUP BY currency")  # fmt: skip


@pytest.fixture
def settings(engine):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")
    if not settings.readonly_database_url:
        pytest.skip("READONLY_DATABASE_URL is not set (the ai_readonly role's connection)")
    return settings


@pytest.fixture
def make_client(settings, tmp_path):
    def _make(model, beta=None):
        container = build_container(settings, extractor=FakeReceiptExtractor(), storage=LocalFileStorage(tmp_path),
                                    today=lambda: TODAY, assistant_model=beta or FakeAssistantModel(),
                                    standard_model=model)  # fmt: skip
        return TestClient(create_app(container)), container

    return _make


@pytest.fixture
def sign_in(engine):
    emails: list[str] = []

    def _sign_in(client) -> tuple[dict[str, str], int]:
        email = f"{uuid.uuid4()}@test.local"
        emails.append(email)
        body = {"email": email, "password": "correct-horse"}
        assert client.post("/auth/register", json=body | {"first_name": "Sam", "gender": "male"}).status_code == 201
        result = client.post("/auth/login", json=body).json()
        return {"Authorization": f"Bearer {result['access_token']}"}, result["user"]["id"]

    yield _sign_in
    for email in emails:
        forget_usage_by_email(engine, email)
    with engine.begin() as conn:
        for email in emails:
            conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


def add(client, headers, total, vendor="Spinneys", currency="USD", lines=(), day=None, category=None):
    body = {"vendor_name": vendor, "receipt_date": (day or THIS_MONTH).isoformat(), "currency": currency,
            "total": total, "primary_category_id": category, "lbp_per_usd": "89500",
            "lines": [{"description": name, "normalized_name": name.lower(), "line_total": amount}
                      for name, amount in lines]}  # fmt: skip
    response = client.post("/receipts/manual", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def tools(settings, engine, make_client):
    """The real tools on their own, to call them the way the workflow does."""
    _, container = make_client(ScriptedChatModel())
    runner = SqlReadOnlyQueryRunner(create_db_engine(settings.readonly_database_url))
    return StandardTools(SqlUnitOfWorkFactory(engine), SqlGlotGuard(), SqlGlotQueryRules(), runner,
                         container.spending, container.budgets, container.receipts)  # fmt: skip


def call(tools, user_id, name, args, asked="how much?"):
    outcome = tools.run(user_id, ToolCall("toolu_1", name, args), ToolContext(TODAY, asked))
    return outcome, json.loads(outcome.content)


def ask(client, headers, question, **body):
    return client.post("/assistant/ask", json={"question": question, "assistant_mode": "standard"} | body,
                       headers=headers)  # fmt: skip


# --- Phase 2 done: a scripted tool call through the real application ---


def test_a_standard_question_is_answered_with_a_tool_and_saved(make_client, sign_in, as_user):
    model = ScriptedChatModel(calls(("toolu_1", "query_receipts", {"sql": SPINNEYS_SQL})),
                              says("You spent $23.00 at Spinneys this month."))  # fmt: skip
    client, _ = make_client(model)
    headers, user_id = sign_in(client)
    spinneys = add(client, headers, "23.00", lines=[("Milk", "5"), ("Bread", "18")])
    add(client, headers, "9.00", vendor="Carrefour")

    response = ask(client, headers, "How much did I spend at Spinneys?")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content"] == "You spent $23.00 at Spinneys this month."
    assert (body["assistant_mode"], body["kind"], body["models"]) == ("standard", "answer", ["fake-sonnet"])
    assert body["source_receipts"] == [{"receipt_id": spinneys, "available": True}]
    for internal in ("execution", "prompt_version", "tools"):  # the internal record never reaches the client
        assert internal not in body

    result = json.loads(model.requests[1].messages[-1].parts[0].content)  # what the tool really returned
    assert result["rows"] == [["USD", "23.00", "23.00"]] and result["truncated"] is False

    with as_user(user_id) as conn:  # the turn keeps how it was answered (row-level security: as its user)
        turn = conn.execute(text("SELECT status, assistant_mode, execution FROM assistant_turns")).one()
    assert (turn.status, turn.assistant_mode) == ("completed", "standard")
    execution = turn.execution
    assert execution["outcome"] == "answered" and execution["prompt_version"].startswith("standard-")
    assert execution["tools"][0]["name"] == "query_receipts" and "'Spinneys'" in execution["tools"][0]["sql"]
    assert execution["usage"]["input_tokens"] == 20 and execution["sources_complete"] is True

    # Reopened, the saved answer is shown as it was, in Standard.
    conversation = client.get(f"/assistant/conversations/{body['conversation_id']}", headers=headers).json()
    assert conversation["assistant_mode"] == "standard"
    assert conversation["messages"][1]["content"] == body["content"]


def test_the_real_adapter_runs_a_tool_round_through_the_app(settings, tmp_path, sign_in, as_user):
    """The Anthropic adapter itself (the official SDK) against a fake HTTP server, inside the real app."""

    def reply(content, stop_reason):
        return {"id": "msg", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5", "content": content,
                "stop_reason": stop_reason, "stop_sequence": None,
                "usage": {"input_tokens": 3000, "output_tokens": 60, "cache_creation_input_tokens": 2500,
                          "cache_read_input_tokens": 0}}  # fmt: skip

    script = [
        reply([{"type": "thinking", "thinking": "", "signature": "sig"},
               {"type": "tool_use", "id": "toolu_A", "name": "query_receipts", "input": {"sql": SPINNEYS_SQL}}],
              "tool_use"),
        reply([{"type": "text", "text": "You spent $23.00 at Spinneys."}], "end_turn"),
    ]  # fmt: skip
    sent: list[dict] = []

    def server(request):
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json=script.pop(0), headers={"request-id": f"req_{len(sent)}"})

    adapter = AnthropicChatModel("sk-ant-test", "claude-sonnet-5-5", max_retries=0,
                                 http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(server)))
    container = build_container(settings, extractor=FakeReceiptExtractor(), storage=LocalFileStorage(tmp_path),
                                today=lambda: TODAY, assistant_model=FakeAssistantModel(), standard_model=adapter)
    client = TestClient(create_app(container))  # fmt: skip
    headers, user_id = sign_in(client)
    add(client, headers, "23.00")

    body = ask(client, headers, "How much at Spinneys?").json()
    assert (body["content"], body["models"]) == ("You spent $23.00 at Spinneys.", ["claude-sonnet-5-5"])
    second = sent[1]["messages"]
    assert second[1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig"}  # sent back unchanged
    tool_result = second[2]["content"][0]
    assert (tool_result["type"], tool_result["tool_use_id"], tool_result["is_error"]) == ("tool_result", "toolu_A",
                                                                                         False)  # fmt: skip
    assert "2026-11-23" in sent[0]["messages"][-1]["content"][0]["text"]  # the date goes with the question
    with as_user(user_id) as conn:
        execution = conn.execute(text("SELECT execution FROM assistant_turns")).scalar_one()
    assert [c["request_id"] for c in execution["calls"]] == ["req_1", "req_2"]
    assert execution["usage"]["cache_creation_input_tokens"] == 5000


def test_a_model_failure_is_saved_as_an_error_and_beta_is_never_asked(make_client, sign_in):
    from app.domain.assistant.errors import ModelFailed

    beta = FakeAssistantModel()
    client, _ = make_client(ScriptedChatModel(ModelFailed("The Standard model did not answer in time")), beta=beta)
    headers, _ = sign_in(client)
    body = ask(client, headers, "How much did I spend?").json()
    assert (body["kind"], body["content"], body["assistant_mode"]) == ("error", answers.FAILURE, "standard")
    assert beta.sql_prompts == []  # never a silent fallback to the other mode


def test_the_modes_endpoint_shows_the_standard_model(make_client, sign_in):
    client, _ = make_client(ScriptedChatModel())
    headers, _ = sign_in(client)
    modes = {m["mode"]: m for m in client.get("/assistant/modes", headers=headers).json()}
    assert modes["standard"] == {"mode": "standard", "available": True, "models": ["fake-sonnet"], "reason": None}


# --- AC-07: isolation ---


def test_a_user_cannot_read_another_users_receipts_through_the_tools(tools, make_client, sign_in):
    client, _ = make_client(ScriptedChatModel())
    alice_headers, alice = sign_in(client)
    bob_headers, bob = sign_in(client)
    alice_receipt = add(client, alice_headers, "10.00", vendor="Spinneys")
    bob_receipt = add(client, bob_headers, "99.00", vendor="Bob's Garage")

    outcome, body = call(tools, alice, "get_receipt", {"receipt_id": bob_receipt})
    assert outcome.is_error and body == {"error": "The user has no receipt with that id"}

    _, body = call(tools, alice, "query_receipts", {"sql": "SELECT receipt_id, total FROM receipts"})
    assert body["rows"] == [[alice_receipt, "10.00"]]  # row-level security: only her own rows

    outcome, body = call(tools, alice, "query_receipts", {"sql": "SELECT SUM(total) FROM receipts "
                                                                 "WHERE vendor = 'Bob''s Garage'"})  # fmt: skip
    assert outcome.is_error and "Not the user's exact spelling" in body["error"]  # his shop is not one of hers

    _, body = call(tools, alice, "find_names", {"kind": "vendor", "name": "Bob's Garage"})
    assert body["status"] == "not_found"

    outcome, body = call(tools, bob, "get_receipt", {"receipt_id": bob_receipt})
    assert not outcome.is_error and body["total"] == "99.00"


# --- AC-08: SQL boundaries ---


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM users",
        "SELECT * FROM public.receipts",
        "SELECT * FROM assistant_turns",
        "DELETE FROM receipts",
        "UPDATE receipts SET total = 0",
        "SELECT set_config('app.user_id', '1', false)",
        "SELECT 1; SELECT 2",
        "SELECT * FROM receipts WHERE vendor LIKE 'Spin%'",
        "SELECT * FROM receipts WHERE receipt_date = now()",
    ],
)
def test_unsafe_or_rule_breaking_sql_is_refused(tools, make_client, sign_in, sql):
    client, _ = make_client(ScriptedChatModel())
    headers, user_id = sign_in(client)
    add(client, headers, "10.00")
    outcome, body = call(tools, user_id, "query_receipts", {"sql": sql})
    assert outcome.is_error and body["error"]
    assert outcome.sources_listed is False and outcome.evidence == ()


# --- AC-09: names beyond the Beta prompt's newest 100 ---


def test_an_old_vendor_beyond_the_newest_100_is_found_and_queried(tools, make_client, sign_in):
    client, container = make_client(ScriptedChatModel())
    headers, user_id = sign_in(client)
    add(client, headers, "7.25", vendor="Old Corner Shop", day=date(2025, 1, 5))
    for i in range(100):
        add(client, headers, "1.00", vendor=f"Shop {i:03}")

    assert "Old Corner Shop" not in container.assistant.prompt_names(user_id).vendors  # Beta's cap is unchanged

    _, body = call(tools, user_id, "find_names", {"kind": "vendor", "name": "old corner shop"})
    assert (body["status"], [n["name"] for n in body["names"]]) == ("found", ["Old Corner Shop"])
    _, body = call(tools, user_id, "query_receipts",
                   {"sql": "SELECT SUM(total) AS spent FROM receipts WHERE vendor = 'Old Corner Shop'"})
    assert body["rows"] == [["7.25"]]


# --- AC-10: similar names stay uncertain ---


def test_similar_shop_names_are_suggestions_and_a_loose_spelling_is_refused(tools, make_client, sign_in):
    client, _ = make_client(ScriptedChatModel())
    headers, user_id = sign_in(client)
    add(client, headers, "5.00", vendor="Spinneys")
    add(client, headers, "6.00", vendor="Spinneys Achrafieh")

    _, body = call(tools, user_id, "find_names", {"kind": "vendor", "name": "spineys"})
    assert body["status"] == "suggestions" and "not confirmed" in body["note"]
    assert {n["name"] for n in body["names"]} == {"Spinneys", "Spinneys Achrafieh"}

    outcome, body = call(tools, user_id, "query_receipts", {"sql": "SELECT SUM(total) FROM receipts "
                                                                   "WHERE vendor = 'spinneys'"})  # fmt: skip
    assert outcome.is_error and "'spinneys'" in body["error"]  # never matched loosely


# --- the other tools reuse the screens' services ---


def test_the_summary_and_budgets_are_the_services_own_figures(tools, make_client, sign_in):
    client, container = make_client(ScriptedChatModel())
    headers, user_id = sign_in(client)
    groceries = {c["name"]: c["id"] for c in client.get("/categories", headers=headers).json()}["Groceries"]
    add(client, headers, "20.00", category=groceries)
    add(client, headers, "895000", currency="LBP", vendor="Carrefour", category=groceries)  # $10 at 89,500
    assert client.put(f"/budgets/{groceries}", json={"month": "2026-11", "limit_amount": "50"},
                      headers=headers).status_code == 200  # fmt: skip

    _, summary = call(tools, user_id, "get_spending_summary", {"year": 2026, "month": 11, "currency": "USD"})
    expected = container.spending.monthly_summary(user_id, 2026, 11, __import__("app.domain.shared.currency",
                                                                                 fromlist=["Currency"]).Currency.USD)
    assert Decimal(summary["combined"]["total"]) == expected.combined.total == Decimal("30.00")
    assert {e["currency"] for e in summary["by_currency"]} == {"USD", "LBP"}  # fmt: skip

    outcome, budgets = call(tools, user_id, "get_budgets", {"year": 2026, "month": 11})
    (budget,) = budgets["budgets"]
    assert (budget["category"], budget["limit"], budget["spent"]) == ("Groceries", "50.00", "30.00")
    assert budget["pace"] is not None and outcome.sources_listed is False  # a budget lists no receipts


def test_a_receipt_is_returned_with_its_lines_and_cited(tools, make_client, sign_in):
    client, _ = make_client(ScriptedChatModel())
    headers, user_id = sign_in(client)
    receipt_id = add(client, headers, "23.00", lines=[("Milk", "5"), ("Bread", "18")])
    outcome, body = call(tools, user_id, "get_receipt", {"receipt_id": receipt_id})
    assert (body["vendor"], body["total"], body["status"]) == ("Spinneys", "23.00", "confirmed")
    assert [(line["item_name"], line["line_total"]) for line in body["lines"]] == [("milk", "5.00"), ("bread", "18.00")]
    assert outcome.receipt_ids == (receipt_id,)


def test_an_empty_result_says_nothing_matched_rather_than_zero(tools, make_client, sign_in):
    client, _ = make_client(ScriptedChatModel())
    headers, user_id = sign_in(client)
    add(client, headers, "5.00")
    _, body = call(tools, user_id, "query_receipts", {"sql": "SELECT receipt_id FROM receipts WHERE vendor = "
                                                             "'Spinneys' AND receipt_date < '2020-01-01'"})  # fmt: skip
    assert (body["row_count"], body["note"]) == (0, "No confirmed receipt matched")
