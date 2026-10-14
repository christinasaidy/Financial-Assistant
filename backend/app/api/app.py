from fastapi import FastAPI

from app.api.auth import routes as auth_routes
from app.api.budgets import routes as budget_routes
from app.api.categories import routes as category_routes
from app.api.container import Container
from app.api.error_handlers import register_error_handlers
from app.api.health import routes as health_routes
from app.api.notifications import routes as notification_routes
from app.api.receipts import routes as receipt_routes
from app.api.spending import routes as spending_routes


def create_app(container: Container) -> FastAPI:
    app = FastAPI(title="Expense Tracker API")
    app.state.container = container
    app.include_router(health_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(receipt_routes.router)
    app.include_router(category_routes.router)
    app.include_router(spending_routes.router)
    app.include_router(budget_routes.router)
    app.include_router(notification_routes.router)
    register_error_handlers(app)
    return app
