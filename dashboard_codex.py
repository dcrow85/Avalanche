#!/usr/bin/env python3
"""
Wrapper for the standard Avalanche dashboard with Codex defaults.

Default workspace: C:\terrarium-codex
Default port: 8281
"""
import os
import sys

import dashboard


def main():
    args = sys.argv[1:]
    port = "8281"
    workspace = r"C:\terrarium-codex"

    if args and not args[0].startswith("--"):
        workspace = os.path.abspath(args[0])
        args = args[1:]

    sys.argv = [sys.argv[0], workspace, "--port", port, *args]
    dashboard.main()


if __name__ == "__main__":
    main()
