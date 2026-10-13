"""Infrastructure layer: details such as the database, LLM clients and file storage.

Dependency Rule: may import `app.application` and `app.domain`. It implements the interfaces
the application layer defines. Nothing inside may be imported by the domain or application.
"""
