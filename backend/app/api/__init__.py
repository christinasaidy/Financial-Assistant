"""API layer: FastAPI routers that translate HTTP into use-case calls.

Dependency Rule: may import `app.application` and `app.domain`, never `app.infrastructure`.
Concrete implementations reach the routers only through `app.main`, the composition root.
"""
