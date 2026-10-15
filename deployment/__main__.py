"""Delegate python3 -B -m deployment to the command-line handler."""

from .cli import main

raise SystemExit(main())
