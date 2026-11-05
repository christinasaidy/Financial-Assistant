"""Seeds the evaluation data (data/seed.json) as a throwaway user, through the app's own services."""

import json
import secrets
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text

from app.application.auth.dtos import RegisterRequest
from app.application.receipts.dtos import ConfirmReceiptRequest, UploadReceiptRequest
from app.domain.receipts.extraction import ExtractedLine, ExtractedReceipt
from app.domain.receipts.receipt import ReceiptLine
from research.evaluation.questions import SEED_FILE
from research.evaluation.wiring import Evaluation

EMAIL_DOMAIN = "evaluation.local"


def seed_user(evaluation: Evaluation, path: Path = SEED_FILE) -> int:
    """A new user holding the evaluation receipts; returns its id. Remove it with `remove_user` afterwards."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rate = Decimal(data["rate"])
    email = f"evaluation-{uuid.uuid4()}@{EMAIL_DOMAIN}"
    user_id = evaluation.auth.register(RegisterRequest(email, secrets.token_urlsafe(24))).id
    category_ids = {category.name: category.id for category in evaluation.categories.list_all(user_id)}
    for receipt in data["receipts"]:
        evaluation.receipts.create_manual(user_id, ConfirmReceiptRequest(
            vendor_name=receipt["vendor"],
            receipt_date=date.fromisoformat(receipt["date"]),
            currency=receipt["currency"],
            total=Decimal(receipt["total"]),
            primary_category_id=category_ids[receipt["category"]],
            lines=[_line(line) for line in receipt["lines"]],
            lbp_per_usd=rate,
        ))  # fmt: skip
    for receipt in data.get("waiting_for_review", ()):  # read by the stand-in reader, then left unconfirmed
        evaluation.reader.next = ExtractedReceipt(
            vendor_name=receipt["vendor"], receipt_date=date.fromisoformat(receipt["date"]),
            currency=receipt["currency"], total=Decimal(receipt["total"]),
            lines=[ExtractedLine(description=line[0].upper(), line_total=Decimal(line[6]), normalized_name=line[0])
                   for line in receipt["lines"]],
        )  # fmt: skip
        uploaded = evaluation.receipts.upload(user_id, UploadReceiptRequest(uuid.uuid4().bytes, "image/jpeg"))
        evaluation.receipts.process(user_id, uploaded.receipt.id)
    return user_id


def remove_user(evaluation: Evaluation, user_id: int) -> None:
    """Delete the throwaway user and, with it, everything it owns. PENDING the user's decision: the app has no
    public way to delete a user yet, so this is a direct statement for now (as the backend's own tests do)."""
    engine = create_engine(evaluation.settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :id AND email LIKE :pattern"),
                     {"id": user_id, "pattern": f"evaluation-%@{EMAIL_DOMAIN}"})  # fmt: skip
    engine.dispose()


def _line(line: list) -> ReceiptLine:
    name, brand, size, unit, quantity, unit_price, line_total = line
    return ReceiptLine(
        description=name.upper(), line_total=Decimal(line_total), quantity=Decimal(quantity),
        unit_price=Decimal(unit_price) if unit_price else None, normalized_name=name,
        size_amount=Decimal(size) if size else None, size_unit=unit, brand=brand,
    )  # fmt: skip
