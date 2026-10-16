"""Find receipt files that no receipt points at, and remove them with --delete (second code review, finding 11).

    python -m app.clean_files            # only lists them
    python -m app.clean_files --delete   # removes them

Only files the app stored itself (its own random names, in a numbered user folder under UPLOAD_DIR), older than
24 hours, and not referenced by any of that user's receipts are touched. See ReceiptService.find_orphaned_files.
"""

import argparse
import logging

from app.api.container import Container
from app.infrastructure.config import Settings
from app.main import build_container


def main(argv: list[str] | None = None, container: Container | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.clean_files", description=__doc__.splitlines()[0])
    parser.add_argument("--delete", action="store_true", help="remove the files instead of only listing them")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    receipts = (container or build_container(Settings())).receipts
    orphans = receipts.remove_orphaned_files() if args.delete else receipts.find_orphaned_files()
    verb = "Removed" if args.delete else "Would remove"
    for paths in orphans.values():
        for path in paths:
            print(f"{verb} {path}")
    print(f"{verb} {sum(len(paths) for paths in orphans.values())} file(s).")
    if not args.delete and orphans:
        print("Run again with --delete to remove them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
