from app.domain.receipts.receipt import Receipt

MISSING_VENDOR = "missing_vendor"
MISSING_DATE = "missing_date"
MISSING_CURRENCY = "missing_currency"
MISSING_TOTAL = "missing_total"
TOTAL_MISMATCH = "total_mismatch"
LINE_WITHOUT_NAME = "line_without_name"


def review_flags(receipt: Receipt) -> list[str]:
    """Things the user should look at on the review screen. A flag never blocks saving:
    real receipts have tax, discounts and rounding, so lines often don't add up to the total."""
    flags: list[str] = []
    if not receipt.vendor_name:
        flags.append(MISSING_VENDOR)
    if receipt.receipt_date is None:
        flags.append(MISSING_DATE)
    if receipt.currency is None:
        flags.append(MISSING_CURRENCY)
    if receipt.total is None:
        flags.append(MISSING_TOTAL)
    elif receipt.lines and receipt.lines_total != receipt.total:
        flags.append(TOTAL_MISMATCH)
    if any(line.normalized_name is None for line in receipt.lines):
        flags.append(LINE_WITHOUT_NAME)
    return flags
