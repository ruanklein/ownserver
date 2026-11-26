"""Run Ownserver with ``python -m ownserver``."""

import sys

from .app import main


if __name__ == "__main__":
    sys.exit(main())
