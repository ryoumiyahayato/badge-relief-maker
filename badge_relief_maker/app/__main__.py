"""Package command-line entry point."""

import sys

from .main import main


raise SystemExit(main(sys.argv[1:]))
