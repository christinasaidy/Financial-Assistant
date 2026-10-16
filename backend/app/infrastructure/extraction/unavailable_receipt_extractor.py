from collections.abc import Sequence

from app.domain.receipts.errors import ExtractionFailed
from app.domain.receipts.extraction import ExtractedReceipt


class UnavailableReceiptExtractor:
    """Used when no vision-model API key is configured. Every receipt ends as `failed`,
    so the app still works through manual entry."""

    def extract(
        self, content: bytes, content_type: str, category_names: Sequence[str], known_names: Sequence[str] = ()
    ) -> ExtractedReceipt:
        raise ExtractionFailed("No vision model is configured (set GEMINI_API_KEY)")
