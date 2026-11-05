from collections.abc import Sequence

from app.domain.assistant.answer import ReplyForm
from research.evaluation.questions import PilotQuestion

_REPLIES = {
    ReplyForm.CLARIFY: "CLARIFY: (the expected clarifying question)",
    ReplyForm.UNSUPPORTED: "UNSUPPORTED",
    ReplyForm.REPLY: "REPLY: (the expected short reply)",
}


class ExpectedAnswersModel:
    """The default "model": it replies to each test question with its first accepted answer. Running the evaluation
    with it costs nothing and should score 100%; anything less means the questions, the data or the scoring are
    wrong, not a model."""

    sql_model = "expected"
    answer_model = "expected"

    def __init__(self, questions: Sequence[PilotQuestion]) -> None:
        self._answers = {question.question: question.accept[0] for question in questions}

    def write_sql(self, prompt: str) -> str:
        accepted = self._answers[question_in(prompt)]
        return accepted.sql if accepted.sql is not None else _REPLIES[accepted.reply]

    def write_answer(self, prompt: str) -> str:
        raise AssertionError("The evaluation scores the SQL step only; the answer step is never called")


def question_in(prompt: str) -> str:
    """The question a prompt asks (also in a repair prompt, where the first reply and its problem follow it)."""
    return prompt.rsplit("\nQuestion: ", 1)[-1].split("\nReply:", 1)[0]
