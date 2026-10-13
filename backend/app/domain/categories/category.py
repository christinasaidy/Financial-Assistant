from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    is_shared: bool  # a system default visible to every user
