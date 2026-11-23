import pytest


@pytest.fixture(autouse=True)
def _no_paid_standard_calls(monkeypatch):
    """Ordinary tests never call Anthropic: the Standard mode is off whatever backend/.env says. A test that needs
    Standard injects a fake model or workflow into build_container instead."""
    monkeypatch.setenv("STANDARD_ASSISTANT_ENABLED", "false")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
