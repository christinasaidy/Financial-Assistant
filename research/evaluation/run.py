"""Score a model on the pilot test questions (research phase 4; decisions approved by the user on 2026-11-05).

    backend\\.venv\\Scripts\\python -m research.evaluation.run                      # free: the expected answers
    backend\\.venv\\Scripts\\python -m research.evaluation.run --model NAME --yes   # a real model (costs money)
    ... --questions research/evaluation/data/test_questions.json                     # the test set

Run from the repository folder. Each run seeds a throwaway user with data/seed.json, asks every question in
data/questions.json through the app's own SQL step (AssistantService.run_question) on 2026-11-03, scores each reply
(scoring.py), removes the user, prints a summary and saves the full results in results/ (not committed). A questions
file naming a "user" (the test set: synthetic user 31) is asked as that synthetic user instead, on its own today.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from app.application.assistant.dtos import QuestionOutcome
from app.application.assistant.interfaces import AssistantModel
from app.infrastructure.language_model.openai_compatible_assistant_model import OpenAiCompatibleAssistantModel
from app.infrastructure.sql.query_rules import SqlGlotQueryRules
from app.infrastructure.sql.sql_guard import SqlGlotGuard
from research.evaluation.expected_model import ExpectedAnswersModel
from research.dataset.catalogue import load_catalogue
from research.dataset.users import make_user
from research.dataset.users import seed_user as seed_synthetic_user
from research.evaluation.questions import QUESTIONS_FILE, PilotQuestion, data_user, load_questions, seed_names
from research.evaluation.scoring import Score, score
from research.evaluation.seed import remove_user, seed_user
from research.evaluation.wiring import BACKEND_DIR, Evaluation, build_evaluation, load_settings

RESULTS_DIR = Path(__file__).resolve().parent / "results"
CALLS_PER_QUESTION = 2  # at most: the first try and one repair (the answer step is never called)


@dataclass(frozen=True)
class QuestionReport:
    question: PilotQuestion
    outcome: QuestionOutcome
    score: Score


def evaluate(evaluation: Evaluation, questions: Sequence[PilotQuestion], today: date, user: int | None = None
             ) -> list[QuestionReport]:  # fmt: skip
    """Seed the data (seed.json, or synthetic user `user`), ask every question, score it, and always remove the
    throwaway user."""
    if user is None:
        user_id = seed_user(evaluation)
    else:
        synthetic = make_user(load_catalogue(), user)
        if synthetic.today != today:
            raise ValueError(f"Synthetic user {user} is asked on its own today, {synthetic.today}, not {today}")
        user_id = seed_synthetic_user(evaluation, synthetic)
    try:
        if user is None:
            categories = tuple(c.name for c in evaluation.categories.list_all(user_id))
            names = seed_names(categories=categories)
        else:
            names = evaluation.assistant.prompt_names(user_id)
        guard, rules = SqlGlotGuard(), SqlGlotQueryRules()
        reports = []
        for question in questions:
            expected = [
                evaluation.assistant.run_query(user_id, rules.prepare(guard.check(a.sql), names, today)) if a.sql
                else None
                for a in question.accept
            ]  # fmt: skip
            outcome = evaluation.assistant.run_question(user_id, question.question, question.history)
            reports.append(QuestionReport(question, outcome, score(question, outcome, expected)))
        return reports
    finally:
        remove_user(evaluation, user_id)


def summary(reports: Sequence[QuestionReport], label: str) -> str:
    total = len(reports)
    right = sum(r.score.correct for r in reports)
    first = sum(r.score.first_try for r in reports)
    lines = [f"Model: {label}   Questions: {total}",
             f"Correct: {right}/{total}   on the first try: {first}/{total}", ""]  # counts: a pilot is too small for %
    for title, key in (("By type", lambda r: r.question.type), ("By language", lambda r: r.question.language)):
        counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for report in reports:
            counts[key(report)][0] += report.score.correct
            counts[key(report)][1] += 1
        lines.append(f"{title}: " + ", ".join(f"{name} {ok}/{n}" for name, (ok, n) in counts.items()))
    groups: dict[str, list[bool]] = defaultdict(list)
    for report in reports:
        if report.question.group:
            groups[report.question.group].append(report.score.correct)
    if groups:
        whole = sum(all(results) for results in groups.values())
        lines.append(f"Spelling groups right in every spelling: {whole}/{len(groups)}")
    wrong = [r for r in reports if not r.score.correct]
    if wrong:
        lines += ["", "Wrong:"]
        for report in wrong:
            q = report.question
            lines.append(f"  {q.id} [{q.language}, {q.type}] {report.score.reason}: {q.question}")
            if report.outcome.result is not None:
                lines.append(f"      ran: {report.outcome.result.sql}")
    return "\n".join(lines)


def results_json(reports: Sequence[QuestionReport], run: dict) -> dict:
    return {
        "run": run,
        "correct": sum(r.score.correct for r in reports),
        "first_try": sum(r.score.first_try for r in reports),
        "questions": [
            {
                "id": r.question.id, "question": r.question.question, "language": r.question.language,
                "type": r.question.type, "group": r.question.group, "correct": r.score.correct,
                "first_try": r.score.first_try, "reason": r.score.reason,
                "reply": r.outcome.reply.form.value if r.outcome.reply else None,
                "sql": r.outcome.result.sql if r.outcome.result else None,
                "attempts": [{"output": a.output, "problem": a.problem} for a in r.outcome.attempts],
            }
            for r in reports
        ],
    }  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score a model on the pilot test questions.")
    parser.add_argument("--model", default="expected", help='model name; "expected" (default, free) replies '
                        "with the expected answers")  # fmt: skip
    parser.add_argument("--base-url", help="the OpenAI-compatible API (default: ASSISTANT_BASE_URL)")
    parser.add_argument("--thinking", choices=["on", "off"], help="turn the model's thinking on or off")
    parser.add_argument("--questions", type=Path, default=QUESTIONS_FILE)
    parser.add_argument("--yes", action="store_true", help="confirm the calls to a real model")
    args = parser.parse_args(argv)

    today, questions = load_questions(args.questions)
    settings = load_settings()
    real = args.model != "expected"
    base_url = args.base_url or settings.assistant_base_url
    if real and not args.yes:
        print(f"This run makes up to {CALLS_PER_QUESTION * len(questions)} calls to {args.model} at {base_url}, "
              "which may cost money. Add --yes to start.")  # fmt: skip
        return 1
    model = _model(args, settings, base_url) if real else ExpectedAnswersModel(questions)

    started = datetime.now(UTC)
    with tempfile.TemporaryDirectory() as storage:
        evaluation = build_evaluation(settings, model, today, Path(storage))
        reports = evaluate(evaluation, questions, today, data_user(args.questions))
    label = f"{args.model}" + (f" (thinking {args.thinking})" if args.thinking else "")
    print(summary(reports, label))

    run = {"started": started.isoformat(timespec="seconds"), "model": args.model,
           "base_url": base_url if real else None, "thinking": args.thinking, "today": today.isoformat(),
           "user": data_user(args.questions), "questions_file": str(args.questions), **_backend_commit()}  # fmt: skip
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{started.strftime('%Y%m%d-%H%M%S')}-{_safe(args.model)}.json"
    path.write_text(json.dumps(results_json(reports, run), indent=2, default=str), encoding="utf-8")
    print(f"\nFull results: {path}")
    return 0


def _model(args: argparse.Namespace, settings, base_url: str) -> AssistantModel:
    api_key = settings.assistant_api_key or settings.gemini_api_key
    if not api_key:
        raise SystemExit("No API key: set ASSISTANT_API_KEY (or GEMINI_API_KEY) in backend/.env")
    thinking = {"on": True, "off": False}.get(args.thinking)
    return OpenAiCompatibleAssistantModel(base_url, api_key, args.model, args.model,
                                          timeout=settings.assistant_timeout_seconds, thinking=thinking)  # fmt: skip


def _backend_commit() -> dict:
    """The code that was measured: the commit, and whether there were uncommitted changes."""
    def git(*command: str) -> str:
        return subprocess.run(["git", *command], cwd=BACKEND_DIR, capture_output=True, text=True).stdout.strip()

    return {"backend_commit": git("rev-parse", "HEAD"), "uncommitted_changes": bool(git("status", "--porcelain"))}


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-." else "_" for ch in name)


if __name__ == "__main__":
    sys.exit(main())
