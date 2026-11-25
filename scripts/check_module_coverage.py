"""Fail if any measured module's combined line + branch coverage is below the threshold."""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import coverage


def evaluate_report(
    report: dict[str, Any], threshold: float
) -> tuple[list[tuple[str, float, str]], tuple[str, float, str] | None, int]:
    """Return ``(failures, lowest, module_count)`` for a coverage.py JSON report."""
    files = report.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("No measured modules found in coverage report")
    failures: list[tuple[str, float, str]] = []
    lowest: tuple[str, float, str] | None = None
    for path in sorted(files):
        summary = files[path].get("summary", {})
        percent = float(summary["percent_covered"])
        display = str(summary.get("percent_covered_display", f"{percent:.2f}"))
        entry = (path, percent, display)
        if lowest is None or percent < lowest[1]:
            lowest = entry
        if percent < threshold:
            failures.append(entry)
    return failures, lowest, len(files)


def check_data_file(
    data_file: Path,
    *,
    fail_under: float | None = None,
    config_file: bool | str = True,
) -> tuple[float, list[tuple[str, float, str]], tuple[str, float, str] | None, int]:
    """Load ``data_file`` and evaluate per-module combined line + branch coverage."""
    if not data_file.is_file():
        raise FileNotFoundError(f"Coverage data file not found: {data_file}")
    cov = coverage.Coverage(data_file=str(data_file), config_file=config_file)
    cov.load()
    if fail_under is None:
        configured = cov.get_option("report:fail_under")
        if isinstance(configured, (int, float, str)) and not isinstance(configured, bool):
            threshold = float(configured)
        else:
            threshold = 95.0
    else:
        threshold = float(fail_under)
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 100.0:
        raise ValueError(f"Invalid coverage threshold: {threshold}")
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "coverage.json"
        cov.json_report(outfile=str(out))
        report = json.loads(out.read_text(encoding="utf-8"))
    failures, lowest, count = evaluate_report(report, threshold)
    return threshold, failures, lowest, count


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enforce a minimum combined line + branch coverage percentage for every module."
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="Minimum combined coverage percentage per module (default: report.fail_under or 95)",
    )
    parser.add_argument(
        "--data-file",
        type=Path,
        default=Path(".coverage"),
        help="Path to the coverage.py data file (default: .coverage)",
    )
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="Ignore project coverage configuration files (useful for isolated tests)",
    )
    args = parser.parse_args(argv)
    try:
        threshold, failures, lowest, count = check_data_file(
            args.data_file,
            fail_under=args.fail_under,
            config_file=False if args.no_config else True,
        )
    except (OSError, ValueError, coverage.CoverageException) as exc:
        print(f"module-coverage: {exc}", file=sys.stderr)
        return 1
    if failures:
        print(
            f"FAIL per-module coverage gate ({threshold:.2f}%) failed for {len(failures)} "
            f"of {count} module(s):",
            file=sys.stderr,
        )
        for path, _percent, display in failures:
            print(f"  {path}: {display}% < {threshold:.2f}%", file=sys.stderr)
        return 1
    assert lowest is not None
    print(
        f"PASS per-module coverage >= {threshold:.2f}% across {count} modules "
        f"(lowest: {lowest[2]}% in {lowest[0]})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
