"""Application layer: one service per feature, orchestrating the domain rules.

Dependency Rule: may import `app.domain` and the standard library only.
Interfaces (for repositories, the extraction provider, the SQL generator) are
defined here and implemented in `app.infrastructure`. Services take and return plain
request/response objects, never ORM models or HTTP objects.
"""
