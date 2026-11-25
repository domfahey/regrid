"""Tests for scripts/check_module_coverage.py per-module coverage gate."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load("check_module_coverage", ROOT / "scripts/check_module_coverage.py")


def test_evaluate_report_passes_and_identifies_lowest():
    report = {
        "files": {
            "src/regrid/a.py": {"summary": {"percent_covered": 100.0}},
            "src/regrid/b.py": {
                "summary": {"percent_covered": 95.0, "percent_covered_display": "95.00"}
            },
        }
    }
    failures, lowest, count = checker.evaluate_report(report, 95.0)
    assert failures == []
    assert lowest == ("src/regrid/b.py", 95.0, "95.00")
    assert count == 2


def test_evaluate_report_flags_modules_below_threshold():
    report = {
        "files": {
            "src/regrid/a.py": {
                "summary": {"percent_covered": 99.5, "percent_covered_display": "99.50"}
            },
            "src/regrid/b.py": {
                "summary": {"percent_covered": 94.99, "percent_covered_display": "94.99"}
            },
        }
    }
    failures, lowest, count = checker.evaluate_report(report, 95.0)
    assert failures == [("src/regrid/b.py", 94.99, "94.99")]
    assert lowest == ("src/regrid/b.py", 94.99, "94.99")
    assert count == 2


def test_evaluate_report_rejects_empty_report():
    with pytest.raises(ValueError, match="No measured modules"):
        checker.evaluate_report({"files": {}}, 95.0)


def test_main_rejects_missing_data_file_and_invalid_threshold(tmp_path, capsys):
    missing = tmp_path / "missing.coverage"
    assert checker.main(["--data-file", str(missing), "--no-config"]) == 1
    assert "not found" in capsys.readouterr().err

    dummy = tmp_path / "dummy.coverage"
    dummy.write_bytes(b"")
    assert checker.main(["--data-file", str(dummy), "--fail-under", "101", "--no-config"]) == 1
    assert "Invalid coverage threshold" in capsys.readouterr().err


def test_main_enforces_per_module_gate_on_real_coverage_data(tmp_path, capsys):
    mod = tmp_path / "sample.py"
    mod.write_text(
        "def classify(x):\n    if x > 0:\n        return 'pos'\n    return 'nonpos'\nclassify(1)\n",
        encoding="utf-8",
    )
    data_file = tmp_path / ".coverage"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--branch",
            f"--data-file={data_file}",
            str(mod),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert run.returncode == 0, run.stderr

    # Missed branch + return leaves sample.py below 95%, so the gate must fail.
    assert checker.main(["--data-file", str(data_file), "--fail-under", "95", "--no-config"]) == 1
    err = capsys.readouterr().err
    assert "FAIL per-module coverage gate (95.00%)" in err
    assert "sample.py" in err

    # With a threshold below the measured percentage, the gate passes.
    assert checker.main(["--data-file", str(data_file), "--fail-under", "50", "--no-config"]) == 0
    out = capsys.readouterr().out
    assert "PASS per-module coverage >= 50.00% across 1 modules" in out
