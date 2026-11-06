"""Container health check: the decoder must report the running state."""

from __future__ import annotations

import json
import os
import sys
import urllib.request

from .publisher import STATUS_PATH


def check(port: int, timeout: float = 3.0) -> bool:
    """Return True when the local decoder reports the running state."""
    url = f"http://127.0.0.1:{port}{STATUS_PATH}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            status = json.load(response)
    except (OSError, ValueError):
        return False
    return isinstance(status, dict) and status.get("state") == "running"


if __name__ == "__main__":
    sys.exit(0 if check(int(os.environ.get("OSP_PORT", "8765"))) else 1)
