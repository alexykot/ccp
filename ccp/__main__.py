"""`python3 -m ccp` — the same entry point as the `ccp` console script and `bin/ccp`."""
import sys

from ccp.cli import main

sys.exit(main())
