"""Healthcheck für Docker: `python -m app.healthcheck` endet mit 0, wenn der Server antwortet."""

import sys
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8000/api/v1/health"


def main() -> int:
    try:
        with urllib.request.urlopen(URL, timeout=4) as response:
            return 0 if response.status == 200 else 1
    except urllib.error.URLError, OSError:
        return 1


if __name__ == "__main__":
    sys.exit(main())
