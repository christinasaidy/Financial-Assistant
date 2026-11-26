"""The two assistant modes and request keys (2026-11-23)."""

import pytest

from app.domain.assistant.conversation import (
    DEFAULT_MODE,
    AssistantMode,
    Conversation,
    clean_idempotency_key,
)
from app.domain.assistant.errors import InvalidIdempotencyKey


def test_a_client_that_names_no_mode_gets_the_original_workflow():
    """So a client written before the modes never starts a paid hosted-model conversation by itself."""
    assert DEFAULT_MODE is AssistantMode.BETA


def test_the_modes_are_exactly_standard_and_beta():
    assert {mode.value for mode in AssistantMode} == {"standard", "beta"}


def test_a_conversation_read_without_a_mode_is_beta():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    assert Conversation(1, "t", now, now, 0).mode is AssistantMode.BETA


def test_no_key_is_none_and_a_key_is_trimmed():
    assert clean_idempotency_key(None) is None
    assert clean_idempotency_key("  3f2b-11  ") == "3f2b-11"


@pytest.mark.parametrize("key", ["", "   ", "k" * 201, "line\nbreak", "tab\there"])
def test_an_empty_long_or_unprintable_key_is_refused(key):
    with pytest.raises(InvalidIdempotencyKey):
        clean_idempotency_key(key)


def test_a_key_of_200_characters_is_accepted():
    assert clean_idempotency_key("k" * 200) == "k" * 200
