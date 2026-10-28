"""Local configuration checks; never print credentials or contact the API."""

import os
from pathlib import Path


def main() -> int:
    exists = Path(".env").is_file()
    print("PASS .env exists" if exists else "FAIL .env missing")
    token = os.environ.get("REGRID_TOKEN", "").strip()
    configured = bool(token) and token != "replace_with_your_regrid_api_token"
    print(
        "PASS REGRID_TOKEN configured" if configured else "FAIL REGRID_TOKEN missing or placeholder"
    )
    print("Local check only; API authentication was not tested")
    return 0 if exists and configured else 1


if __name__ == "__main__":
    raise SystemExit(main())
