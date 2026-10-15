from dataclasses import dataclass


@dataclass(frozen=True)
class QueryResult:
    sql: str  # exactly what ran
    columns: list[str]
    rows: list[tuple]
    truncated: bool  # more rows existed than the limit allows
