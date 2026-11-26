import json

from sqlalchemy import Connection, text

from app.domain.assistant.conversation import AssistantMode, Turn, TurnStatus

_SELECT = """
    SELECT t.id, t.conversation_id, t.question_message_id, m.content AS question, t.assistant_mode, t.status,
           t.answer_message_id, t.idempotency_key, t.problem
    FROM assistant_turns t
    JOIN messages m ON m.id = t.question_message_id
"""


class SqlTurnRepository:
    """Works on a connection already scoped to one user; turns are owned by `app_user_id()`.

    The database holds the rules the service relies on: one running turn per conversation (a unique index), one
    turn per key and user, a turn only in the user's own conversation, and only a running turn can finish."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def start(
        self, conversation_id: int, question_message_id: int, mode: AssistantMode, idempotency_key: str | None
    ) -> int | None:
        # ON CONFLICT DO NOTHING (any unique rule): a request racing this one for the same conversation or key waits
        # for it to commit, then finds the row and inserts nothing. None tells the caller to back off.
        return self._conn.execute(
            text(
                "INSERT INTO assistant_turns (user_id, conversation_id, question_message_id, assistant_mode, "
                "idempotency_key) VALUES (app_user_id(), :conversation_id, :question_id, :mode, :key) "
                "ON CONFLICT DO NOTHING RETURNING id"
            ),
            {"conversation_id": conversation_id, "question_id": question_message_id, "mode": mode.value,
             "key": idempotency_key},
        ).scalar_one_or_none()  # fmt: skip

    def give_up_abandoned(self, conversation_id: int, older_than_seconds: float) -> int:
        return self._conn.execute(
            text(
                "UPDATE assistant_turns SET status = 'failed', problem = 'abandoned', finished_at = now() "
                "WHERE conversation_id = :id AND status = 'running' "
                "AND started_at < now() - make_interval(secs => :seconds)"
            ),
            {"id": conversation_id, "seconds": float(older_than_seconds)},
        ).rowcount

    def find_by_key(self, idempotency_key: str) -> Turn | None:
        row = self._conn.execute(
            text(_SELECT + " WHERE t.idempotency_key = :key"), {"key": idempotency_key}
        ).one_or_none()
        return _to_turn(row) if row else None

    def get(self, turn_id: int) -> Turn | None:
        row = self._conn.execute(text(_SELECT + " WHERE t.id = :id"), {"id": turn_id}).one_or_none()
        return _to_turn(row) if row else None

    def complete(self, turn_id: int, answer_message_id: int, execution: dict | None = None) -> bool:
        return bool(
            self._conn.execute(
                text(
                    "UPDATE assistant_turns SET status = 'completed', answer_message_id = :answer, "
                    "execution = CAST(:execution AS jsonb), finished_at = now() "
                    "WHERE id = :id AND status = 'running'"
                ),
                {"id": turn_id, "answer": answer_message_id,
                 "execution": json.dumps(execution) if execution is not None else None},
            ).rowcount  # fmt: skip
        )

    def fail(self, turn_id: int, problem: str) -> bool:
        return bool(
            self._conn.execute(
                text(
                    "UPDATE assistant_turns SET status = 'failed', problem = :problem, finished_at = now() "
                    "WHERE id = :id AND status = 'running'"
                ),
                {"id": turn_id, "problem": problem[:500]},
            ).rowcount
        )

    def previous_execution(self, conversation_id: int, turn_id: int) -> dict | None:
        row = self._conn.execute(
            text(
                "SELECT status, execution FROM assistant_turns WHERE conversation_id = :conversation AND id < :id "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"conversation": conversation_id, "id": turn_id},
        ).one_or_none()
        if row is None or row.status != TurnStatus.COMPLETED.value or not isinstance(row.execution, dict):
            return None
        return row.execution


def _to_turn(row) -> Turn:
    return Turn(
        id=row.id,
        conversation_id=row.conversation_id,
        question_message_id=row.question_message_id,
        question=row.question,
        mode=AssistantMode(row.assistant_mode),
        status=TurnStatus(row.status),
        answer_message_id=row.answer_message_id,
        idempotency_key=row.idempotency_key,
        problem=row.problem,
    )
