"""Enforces the Dependency Rule: source dependencies point inward only."""

import ast
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
STDLIB = set(sys.stdlib_module_names)

# layer -> the app layers it may import (besides itself and the standard library)
ALLOWED_APP_IMPORTS = {
    "domain": set(),
    "application": {"domain"},
    "infrastructure": {"domain", "application"},
    "api": {"domain", "application"},
}
# Only the inner layers must also avoid third-party packages.
STDLIB_ONLY = {"domain", "application"}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)
    return modules


def violations_in(layer: str) -> list[str]:
    problems: list[str] = []
    for path in (APP_DIR / layer).rglob("*.py"):
        for module in imported_modules(path):
            top = module.split(".")[0]
            if top == "app":
                parts = module.split(".")
                target = parts[1] if len(parts) > 1 else ""
                if target and target != layer and target not in ALLOWED_APP_IMPORTS[layer]:
                    problems.append(f"{path.relative_to(APP_DIR)} imports {module}")
            elif layer in STDLIB_ONLY and top not in STDLIB:
                problems.append(f"{path.relative_to(APP_DIR)} imports third-party {module}")
    return problems


def test_domain_depends_on_nothing_outside_itself():
    assert violations_in("domain") == []


def test_application_depends_only_on_domain():
    assert violations_in("application") == []


def test_infrastructure_depends_only_inward():
    assert violations_in("infrastructure") == []


def test_api_does_not_import_infrastructure():
    assert violations_in("api") == []
