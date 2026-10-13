"""Application layer: use cases that orchestrate domain rules.

Dependency Rule: may import `app.domain` and the standard library only.
Ports (interfaces for repositories, the extraction provider, the SQL generator) are
defined here and implemented in `app.infrastructure`. Use cases take and return plain
request/response objects, never ORM models or HTTP objects.
"""
