#!/usr/bin/env python3
"""Wrapper for the Avalanche dashboard with V4.4 Codex defaults."""
import os
import sys

import dashboard


def main():
    args = sys.argv[1:]
    port = "8981"
    workspace = r"C:\terrarium-v44-codex"

    if args and not args[0].startswith("--"):
        workspace = os.path.abspath(args[0])
        args = args[1:]

    if "--port" in args:
        idx = args.index("--port")
        if idx + 1 < len(args):
            port = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

    dashboard.HTML_PAGE = dashboard.HTML_PAGE.replace(
        "Avalanche Hypervisor V4.1", "Avalanche Hypervisor V4.4 Codex"
    ).replace(
        "AVALANCHE HYPERVISOR V4.1", "AVALANCHE HYPERVISOR V4.4 CODEX"
    )
    sys.argv = [sys.argv[0], workspace, "--port", port, *args]
    dashboard.main()


if __name__ == "__main__":
    main()
