"""County data-date lookup from a saved Regrid /verse response.

Uses only the standard library, makes no network requests, and never reads credentials.
It reports the dates Regrid publishes and never judges whether data is stale.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MAX_AGE_DAYS_LIMIT = 36500
DATE_KEYS = ("last_refresh", "assessor_data_date", "usps_data_date")


class FreshnessError(ValueError):
    """A diagnostic containing only fixed invariants or a county path."""


def county_path(path: str) -> str:
    """Return the first three segments of a US path: /us/<state>/<county>."""
    segments = path.split("/") if isinstance(path, str) else []
    if len(segments) < 4 or segments[0] != "" or segments[1] != "us" or not all(segments[2:4]):
        raise FreshnessError("Expected a US path with state and county, e.g. /us/nj/camden")
    return "/".join(segments[:4])


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _features(verse: object) -> list[object]:
    if isinstance(verse, dict) and isinstance(verse.get("features"), list):
        return verse["features"]
    return [verse]


def county_dates(verse: dict, path: str) -> dict[str, Any]:
    """Return the county's published dates, matching ``properties.path`` exactly."""
    county = county_path(path)
    for feature in _features(verse):
        properties = feature.get("properties") if isinstance(feature, dict) else None
        if isinstance(properties, dict) and properties.get("path") == county:
            return {
                "path": county,
                "county": _text(properties.get("county")),
                "state": _text(properties.get("state")),
                **{key: _text(properties.get(key)) for key in DATE_KEYS},
            }
    raise FreshnessError(f"No verse entry found for {county}")


def default_cache_path(env: Mapping[str, str] | None = None, os_name: str | None = None) -> Path:
    """Default verse cache: %LOCALAPPDATA% on Windows, else XDG_CACHE_HOME or ~/.cache."""
    env = os.environ if env is None else env
    if (os.name if os_name is None else os_name) == "nt":
        base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = env.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "regrid" / "verse.json"


def check_max_age_days(value: object) -> float:
    """Return ``value`` as a float, or raise ValueError unless it is finite and in 0..36500."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        number = math.nan
    if not math.isfinite(number) or not 0 <= number <= MAX_AGE_DAYS_LIMIT:
        raise ValueError(f"max_age_days must be a finite number between 0 and {MAX_AGE_DAYS_LIMIT}")
    return number


def is_stale(retrieved_at: str, max_age_days: float, now: datetime | None = None) -> bool:
    """True when ``retrieved_at`` is older than ``max_age_days`` or cannot be parsed.

    ``max_age_days`` is checked first, before ``retrieved_at`` is parsed: it must be a finite
    number from 0 to 36500, otherwise ValueError is raised.
    """
    limit = timedelta(days=check_max_age_days(max_age_days))
    try:
        when = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) - when > limit


def read_cache(path: Path, base_url: str | None = None) -> tuple[str, dict] | None:
    """Return ``(retrieved_at, response)`` or None if the cache is absent or unusable.

    When ``base_url`` is given (trailing slashes ignored), a cache stored for a different
    (or no) base URL is a miss.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    retrieved_at, response = data.get("retrieved_at"), data.get("response")
    if not isinstance(retrieved_at, str) or not isinstance(response, dict):
        return None
    if base_url is not None and data.get("base_url") != base_url.rstrip("/"):
        return None
    return retrieved_at, response


def write_cache(path: Path, retrieved_at: str, response: dict, base_url: str | None = None) -> None:
    """Atomically write the cache; the directory is created private where supported."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    base_url = base_url.rstrip("/") if base_url is not None else None
    document = {"retrieved_at": retrieved_at, "base_url": base_url, "response": response}
    body = json.dumps(document, allow_nan=False)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".verse-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as temp:
            temp.write(body + "\n")
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report county data dates from a verse response.")
    commands = parser.add_subparsers(dest="command", required=True)
    county = commands.add_parser("county", help="Show a county's published data dates")
    county.add_argument("verse", type=Path, help="Saved /verse response JSON")
    county.add_argument("--path", required=True, help="Regrid path, e.g. /us/nj/camden")
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.verse.read_text(encoding="utf-8"))
        result = county_dates(document, args.path)
    except (OSError, ValueError) as exc:
        print(f"freshness: {' '.join(str(exc).split())}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
