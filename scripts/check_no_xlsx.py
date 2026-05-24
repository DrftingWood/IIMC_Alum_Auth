#!/usr/bin/env python
"""Pre-commit hook to prevent .xlsx/.xls files from being committed."""

import logging
import subprocess
import sys

logger = logging.getLogger(__name__)


def main() -> int:
    """Check for .xlsx/.xls files in staged changes."""
    try:
        output = subprocess.check_output(  # noqa: S603, S607  # pragma: no cover
            ["git", "diff", "--cached", "--name-only"],  # noqa: S603, S607
            text=True,
        )
        files = output.strip().split("\n") if output.strip() else []

        xlsx_files = [f for f in files if f.endswith((".xlsx", ".xls"))]

        if xlsx_files:
            logger.error("ERROR: .xlsx/.xls files must not be committed:")
            for f in xlsx_files:
                logger.error(f"  - {f}")
            return 1

        return 0
    except subprocess.CalledProcessError as e:
        logger.exception("Error running git command: %s", e)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR, format="%(message)s")
    sys.exit(main())
