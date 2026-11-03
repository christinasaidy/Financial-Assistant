from app.domain.assistant.errors import ModelUnavailable


class UnavailableAssistantModel:
    """Used when no language-model API key is configured. Every question gets "the assistant isn't available";
    the rest of the app works as usual."""

    sql_model = "none"
    answer_model = "none"

    def write_sql(self, prompt: str) -> str:
        raise ModelUnavailable("No language model is configured (set ASSISTANT_API_KEY or GEMINI_API_KEY)")

    def write_answer(self, prompt: str) -> str:
        raise ModelUnavailable("No language model is configured (set ASSISTANT_API_KEY or GEMINI_API_KEY)")
