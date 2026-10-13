"""Composition root: the only place that knows every layer and wires them together.

Run with:  uvicorn app.main:app --reload
"""

from fastapi import FastAPI

from app.api.app import create_app
from app.api.container import AuthServices, CategoryServices, Container, ReceiptServices
from app.application.auth.get_current_user import GetCurrentUser
from app.application.auth.login import Login
from app.application.auth.register_user import RegisterUser
from app.application.categories.list_categories import ListCategories
from app.application.receipts.confirm_receipt import ConfirmReceipt
from app.application.receipts.create_manual_receipt import CreateManualReceipt
from app.application.receipts.delete_receipt import DeleteReceipt
from app.application.receipts.get_receipt import GetReceipt
from app.application.receipts.list_receipts import ListReceipts
from app.application.receipts.ports import FileStorage, ReceiptExtractor
from app.application.receipts.process_receipt import ProcessReceipt
from app.application.receipts.upload_receipt import UploadReceipt
from app.infrastructure.config import Settings
from app.infrastructure.database.connection import create_db_engine
from app.infrastructure.database.unit_of_work import SqlUnitOfWorkFactory
from app.infrastructure.database.user_repository import SqlUserRepository
from app.infrastructure.extraction.gemini_receipt_extractor import GeminiReceiptExtractor
from app.infrastructure.extraction.unavailable_receipt_extractor import UnavailableReceiptExtractor
from app.infrastructure.security.password_hasher import Argon2PasswordHasher
from app.infrastructure.security.token_service import JwtTokenService
from app.infrastructure.storage.local_file_storage import LocalFileStorage


def build_container(
    settings: Settings,
    extractor: ReceiptExtractor | None = None,
    storage: FileStorage | None = None,
) -> Container:
    """Wire the real implementations. Tests pass their own extractor and storage."""
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not set (see backend/.env.example)")

    engine = create_db_engine(settings.database_url)
    users = SqlUserRepository(engine)
    uow = SqlUnitOfWorkFactory(engine)
    hasher = Argon2PasswordHasher()
    tokens = JwtTokenService(settings.jwt_secret, settings.jwt_expire_minutes)
    storage = storage or LocalFileStorage(settings.upload_dir)
    if extractor is None:
        extractor = (
            GeminiReceiptExtractor(settings.gemini_api_key, settings.gemini_model)
            if settings.gemini_api_key
            else UnavailableReceiptExtractor()
        )

    return Container(
        auth=AuthServices(
            register_user=RegisterUser(users, hasher),
            login=Login(users, hasher, tokens),
            get_current_user=GetCurrentUser(users),
            tokens=tokens,
        ),
        receipts=ReceiptServices(
            upload=UploadReceipt(uow, storage),
            process=ProcessReceipt(uow, storage, extractor),
            confirm=ConfirmReceipt(uow),
            create_manual=CreateManualReceipt(uow),
            get=GetReceipt(uow),
            list_all=ListReceipts(uow),
            delete=DeleteReceipt(uow, storage),
        ),
        categories=CategoryServices(list_all=ListCategories(uow)),
    )


def build_app(settings: Settings | None = None) -> FastAPI:
    return create_app(build_container(settings or Settings()))


app = build_app()
