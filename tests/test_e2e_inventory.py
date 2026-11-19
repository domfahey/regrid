"""Every CLI subcommand must have an end-to-end test (runs in `make check`, not `make e2e`).

E2E tests are deselected from `make check`, so this parses their sources: it collects the
subcommand argument of every ``run_cli``/``run_cli_offline`` call, not any matching string.
"""

import argparse
import ast
from pathlib import Path

from e2e_support import GLOBAL_VALUE_OPTIONS

from regrid.cli import _parser

E2E_FILES = sorted(Path(__file__).parent.glob("test_e2e*.py"))
RUNNERS = {"run_cli", "run_cli_offline"}


def _subcommands() -> list[str]:
    # argparse keeps subparsers in a private attribute; this test only reads it.
    actions = [a for a in _parser()._actions if isinstance(a, argparse._SubParsersAction)]
    assert len(actions) == 1
    return sorted(actions[0].choices)


def _called_subcommand(call: ast.Call, positional: int) -> str | None:
    """The first string literal after the leading ``server`` and global option pairs."""
    args = call.args[positional:]
    index = 0
    while index < len(args):
        node = args[index]
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            return None  # starred or computed: not a literal subcommand
        if node.value in GLOBAL_VALUE_OPTIONS:
            index += 2
            continue
        return None if node.value.startswith("--") else node.value
    return None


def exercised_subcommands(files: list[Path]) -> set[str]:
    found: set[str] = set()
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in RUNNERS:
                    name = _called_subcommand(node, 1 if node.func.id == "run_cli" else 0)
                    if name:
                        found.add(name)
    return found


def test_every_subcommand_has_an_e2e_test() -> None:
    files = [f for f in E2E_FILES if f.name != Path(__file__).name]
    assert files, "no tests/test_e2e*.py files found"
    missing = sorted(set(_subcommands()) - exercised_subcommands(files))
    assert not missing, f"CLI subcommands without an e2e test: {missing}"


def test_inventory_ignores_stray_literals(tmp_path: Path) -> None:
    sample = tmp_path / "test_e2e_sample.py"
    sample.write_text(
        'fields = {"owner": 1}\nparams = {"query": 2}\n'
        'run_cli(server, "--timeout", "1", "address", "x")\n'
        'run_cli_offline("--base-url", "u", "map", "a")\n'
    )
    assert exercised_subcommands([sample]) == {"address", "map"}
