"""Fail if any measured module's combined line + branch coverage is below the threshold."""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Any

import coverage
from coverage.results import display_covered, should_fail_under

DEFAULT_FAIL_UNDER = 95.0
DEFAULT_PRECISION = 2


def _format_threshold(threshold: float, precision: int) -> str:
    if round(threshold, precision) == threshold:
        return f"{threshold:.{precision}f}"
    return f"{threshold:g}"


def _collect_source_files(source_dir: Path) -> list[Path]:
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")
    files = sorted(
        path
        for path in source_dir.rglob("*.py")
        if path.is_file() and "__pycache__" not in path.parts
    )
    if not files:
        raise ValueError(f"No Python modules found under source directory: {source_dir}")
    return files


def evaluate_report(
    report: dict[str, Any],
    threshold: float,
    *,
    precision: int = DEFAULT_PRECISION,
    require_branch: bool = True,
    expected_files: Collection[Path] | None = None,
) -> tuple[list[tuple[str, float, str]], tuple[str, float, str], int]:
    """Return ``(failures, lowest, module_count)`` for a coverage.py JSON report."""
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 100.0:
        raise ValueError(f"Invalid coverage threshold: {threshold}")
    if not isinstance(report, dict):
        raise ValueError("Invalid coverage report format")
    if require_branch:
        meta = report.get("meta")
        if not isinstance(meta, dict) or meta.get("branch_coverage") is not True:
            raise ValueError("Coverage data lacks branch coverage")
    files = report.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("No measured modules found in coverage report")

    failures: list[tuple[str, float, str]] = []
    lowest: tuple[str, float, str] | None = None
    measured_resolved: set[Path] = set()

    for path in sorted(files):
        file_info = files[path]
        summary = file_info.get("summary") if isinstance(file_info, dict) else None
        raw_percent = summary.get("percent_covered") if isinstance(summary, dict) else None
        if isinstance(raw_percent, bool) or not isinstance(raw_percent, (int, float)):
            raise ValueError(f"Invalid coverage summary for {path}")
        percent = float(raw_percent)
        if not math.isfinite(percent):
            raise ValueError(f"Invalid coverage summary for {path}")
        display = display_covered(percent, precision)
        entry = (path, percent, display)
        measured_resolved.add(Path(path).resolve())
        if lowest is None or percent < lowest[1]:
            lowest = entry
        if should_fail_under(percent, threshold, precision):
            failures.append(entry)

    total_count = len(files)
    if expected_files is not None:
        zero_display = display_covered(0.0, precision)
        cwd = Path.cwd().resolve()
        for expected in sorted(expected_files):
            resolved = expected.resolve()
            if resolved not in measured_resolved:
                try:
                    label = str(resolved.relative_to(cwd))
                except ValueError:
                    label = str(expected)
                entry = (f"{label} (not measured)", 0.0, zero_display)
                total_count += 1
                if lowest is None or 0.0 < lowest[1]:
                    lowest = entry
                if should_fail_under(0.0, threshold, precision):
                    failures.append(entry)

    if lowest is None:  # pragma: no cover - files is verified non-empty above
        raise ValueError("No measured modules found in coverage report")
    return failures, lowest, total_count


def check_data_file(
    data_file: Path | None = None,
    *,
    fail_under: float | None = None,
    source_dir: Path | None = None,
) -> tuple[float, int, list[tuple[str, float, str]], tuple[str, float, str], int]:
    """Load coverage data and evaluate per-module combined line + branch coverage."""
    if fail_under is not None:
        threshold = float(fail_under)
        if not math.isfinite(threshold) or not 0.0 <= threshold <= 100.0:
            raise ValueError(f"Invalid coverage threshold: {threshold}")
    else:
        threshold = -1.0

    expected_files = _collect_source_files(source_dir) if source_dir is not None else None
    cov = coverage.Coverage() if data_file is None else coverage.Coverage(data_file=str(data_file))
    resolved_data = Path(cov.config.data_file)
    if not resolved_data.is_file():
        raise FileNotFoundError(f"Coverage data file not found: {resolved_data}")

    if fail_under is None:
        configured = cov.config.fail_under
        threshold = float(configured) if configured > 0 else DEFAULT_FAIL_UNDER
        if not math.isfinite(threshold) or not 0.0 <= threshold <= 100.0:
            raise ValueError(f"Invalid coverage threshold: {threshold}")

    precision = cov.config.precision if cov.config.precision > 0 else DEFAULT_PRECISION
    cov.load()
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "coverage.json"
        cov.json_report(outfile=str(out))
        report = json.loads(out.read_text(encoding="utf-8"))
    failures, lowest, count = evaluate_report(
        report,
        threshold,
        precision=precision,
        require_branch=True,
        expected_files=expected_files,
    )
    return threshold, precision, failures, lowest, count


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enforce a minimum combined line + branch coverage percentage for every module."
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help=(
            "Minimum combined coverage percentage per module "
            f"(default: positive report.fail_under from config, else {DEFAULT_FAIL_UNDER:g})"
        ),
    )
    parser.add_argument(
        "--data-file",
        type=Path,
        default=None,
        help="Path to the coverage.py data file (default: COVERAGE_FILE or coverage config)",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="Optional package directory; fail if any .py module under it was not measured",
    )
    args = parser.parse_args(argv)
    try:
        threshold, precision, failures, lowest, count = check_data_file(
            args.data_file,
            fail_under=args.fail_under,
            source_dir=args.source_dir,
        )
    except (OSError, ValueError, coverage.CoverageException) as exc:
        print(f"module-coverage: {exc}", file=sys.stderr)
        return 1
    threshold_text = _format_threshold(threshold, precision)
    if failures:
        print(
            f"FAIL per-module coverage gate ({threshold_text}%) failed for {len(failures)} "
            f"of {count} module(s):",
            file=sys.stderr,
        )
        for path, _percent, display in failures:
            print(f"  {path}: {display}% < {threshold_text}%", file=sys.stderr)
        return 1
    print(
        f"PASS per-module coverage >= {threshold_text}% across {count} modules "
        f"(lowest: {lowest[2]}% in {lowest[0]})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
