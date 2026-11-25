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


def _run_coverage(
    cwd: Path,
    script: Path,
    *,
    data_file: Path,
    branch: bool = True,
    source: str | None = None,
) -> None:
    cmd = [sys.executable, "-m", "coverage", "run", f"--data-file={data_file}"]
    if branch:
        cmd.append("--branch")
    if source is not None:
        cmd.append(f"--source={source}")
    cmd.append(str(script))
    run = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    assert run.returncode == 0, run.stderr


def test_evaluate_report_passes_and_identifies_lowest():
    report = {
        "meta": {"branch_coverage": True},
        "files": {
            "src/regrid/a.py": {"summary": {"percent_covered": 100.0}},
            "src/regrid/b.py": {"summary": {"percent_covered": 95.0}},
        },
    }
    failures, lowest, count = checker.evaluate_report(report, 95.0)
    assert failures == []
    assert lowest == ("src/regrid/b.py", 95.0, "95.00")
    assert count == 2


def test_evaluate_report_matches_coverage_rounding_semantics():
    # At precision=2, 94.9975% displays as 95.00% and passes coverage.results.should_fail_under.
    report = {
        "meta": {"branch_coverage": True},
        "files": {
            "src/regrid/borderline_pass.py": {"summary": {"percent_covered": 94.9975}},
            "src/regrid/borderline_fail.py": {"summary": {"percent_covered": 94.994}},
        },
    }
    failures, lowest, count = checker.evaluate_report(report, 95.0, precision=2)
    assert failures == [("src/regrid/borderline_fail.py", 94.994, "94.99")]
    assert lowest == ("src/regrid/borderline_fail.py", 94.994, "94.99")
    assert count == 2


@pytest.mark.parametrize(
    ("report", "match"),
    [
        ({"meta": {"branch_coverage": True}, "files": {}}, "No measured modules"),
        ({"meta": {"branch_coverage": True}, "files": "bad"}, "No measured modules"),
        ({"meta": {"branch_coverage": False}, "files": {"a.py": {}}}, "lacks branch coverage"),
        (
            {"meta": {"branch_coverage": True}, "files": {"a.py": {"summary": {}}}},
            "Invalid coverage summary",
        ),
        (
            {
                "meta": {"branch_coverage": True},
                "files": {"a.py": {"summary": {"percent_covered": float("nan")}}},
            },
            "Invalid coverage summary",
        ),
        (
            {
                "meta": {"branch_coverage": True},
                "files": {"a.py": {"summary": {"percent_covered": True}}},
            },
            "Invalid coverage summary",
        ),
    ],
)
def test_evaluate_report_rejects_malformed_and_line_only_reports(report, match):
    with pytest.raises(ValueError, match=match):
        checker.evaluate_report(report, 95.0)


@pytest.mark.parametrize("bad_threshold", ["-1", "101", "nan", "inf", "-inf"])
def test_main_rejects_out_of_range_and_non_finite_thresholds(
    tmp_path, monkeypatch, capsys, bad_threshold
):
    monkeypatch.chdir(tmp_path)
    dummy = tmp_path / "dummy.coverage"
    dummy.write_bytes(b"")
    assert checker.main(["--data-file", str(dummy), f"--fail-under={bad_threshold}"]) == 1
    assert "Invalid coverage threshold" in capsys.readouterr().err


@pytest.mark.parametrize("content", [b"", b"not-a-sqlite-db"], ids=["empty", "corrupt"])
def test_main_handles_missing_empty_and_corrupt_data_files(tmp_path, monkeypatch, capsys, content):
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing.coverage"
    assert checker.main(["--data-file", str(missing), "--fail-under", "95"]) == 1
    assert "not found" in capsys.readouterr().err

    bad = tmp_path / "bad.coverage"
    bad.write_bytes(content)
    assert checker.main(["--data-file", str(bad), "--fail-under", "95"]) == 1
    assert capsys.readouterr().err.startswith("module-coverage:")


def test_main_defaults_to_95_when_config_omits_fail_under(tmp_path, monkeypatch, capsys):
    mod = tmp_path / "sample.py"
    mod.write_text(
        "def classify(x):\n    if x > 0:\n        return 'pos'\n    return 'nonpos'\nclassify(1)\n",
        encoding="utf-8",
    )
    data_file = tmp_path / ".coverage"
    _run_coverage(tmp_path, mod, data_file=data_file, branch=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("COVERAGE_FILE", raising=False)

    # No pyproject.toml and no --fail-under must still default to 95%, never 0%.
    assert checker.main([]) == 1
    err = capsys.readouterr().err
    assert "FAIL per-module coverage gate (95.00%)" in err
    assert "sample.py" in err

    # Explicit --fail-under 0 is still respected.
    assert checker.main(["--fail-under", "0"]) == 0
    assert "PASS per-module coverage >= 0.00% across 1 modules" in capsys.readouterr().out


def test_main_honors_coverage_file_env_var_instead_of_stale_dot_coverage(
    tmp_path, monkeypatch, capsys
):
    good = tmp_path / "good.py"
    good.write_text("x = 1\n", encoding="utf-8")
    low = tmp_path / "low.py"
    low.write_text(
        "def f(x):\n    if x:\n        return 1\n    return 2\nf(True)\n",
        encoding="utf-8",
    )
    stale_default = tmp_path / ".coverage"
    fresh_custom = tmp_path / "custom.coverage"
    _run_coverage(tmp_path, good, data_file=stale_default, branch=True)
    _run_coverage(tmp_path, low, data_file=fresh_custom, branch=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COVERAGE_FILE", str(fresh_custom))
    assert checker.main(["--fail-under", "95"]) == 1
    err = capsys.readouterr().err
    assert "low.py" in err
    assert "good.py" not in err


def test_main_rejects_line_only_coverage_data(tmp_path, monkeypatch, capsys):
    mod = tmp_path / "branchy.py"
    mod.write_text(
        "def f(x):\n    if x:\n        return 1\n    return 2\nf(True)\n",
        encoding="utf-8",
    )
    data_file = tmp_path / ".coverage"
    _run_coverage(tmp_path, mod, data_file=data_file, branch=False)

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("COVERAGE_FILE", raising=False)
    assert checker.main(["--fail-under", "50"]) == 1
    assert "lacks branch coverage" in capsys.readouterr().err


def test_main_multi_module_config_and_source_dir_completeness(tmp_path, monkeypatch, capsys):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "high.py").write_text(
        "\n".join(f"v{i} = {i}" for i in range(40)) + "\n", encoding="utf-8"
    )
    (pkg / "low.py").write_text(
        "def f(x):\n    if x:\n        return 1\n    return 2\n", encoding="utf-8"
    )
    driver = tmp_path / "run.py"
    driver.write_text("import pkg.high, pkg.low\npkg.low.f(True)\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.coverage.run]\nsource = ["pkg"]\nbranch = true\n'
        "[tool.coverage.report]\nfail_under = 95\nprecision = 2\n",
        encoding="utf-8",
    )
    data_file = tmp_path / ".coverage"
    _run_coverage(tmp_path, driver, data_file=data_file, branch=True, source="pkg")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("COVERAGE_FILE", raising=False)

    # Overall coverage is >95%, but low.py is below the configured 95% threshold.
    assert checker.main(["--source-dir", "pkg"]) == 1
    err = capsys.readouterr().err
    assert "FAIL per-module coverage gate (95.00%)" in err
    assert "low.py" in err

    # With an unmeasured module added under pkg/, --source-dir flags it as missing (0.00%).
    (pkg / "unmeasured.py").write_text("x = 1\n", encoding="utf-8")
    assert checker.main(["--fail-under", "50", "--source-dir", "pkg"]) == 1
    err = capsys.readouterr().err
    assert "unmeasured.py" in err
    assert "not measured" in err

    # Missing --source-dir fails cleanly.
    assert checker.main(["--source-dir", "does_not_exist"]) == 1
    assert "Source directory not found" in capsys.readouterr().err
