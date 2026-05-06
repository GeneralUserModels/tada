"""Connector package."""

import os

if os.environ.get("TADA_PARENT_WATCHDOG") == "1":
    from connectors._parent_watchdog import start_parent_watchdog

    start_parent_watchdog()
