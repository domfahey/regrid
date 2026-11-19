"""The skill's CLI command map must only show invocations the real parser accepts."""

from __future__ import annotations

import argparse
import re
import shlex
from pathlib import Path

import httpx
import pytest

from regrid.cli import _parser

CLI_MD = (
    Path(__file__).resolve().parents[1]
    / "plugins/regrid-research/skills/property-research/references/cli.md"
)
PLACEHOLDERS = {
    "L": "39.9",
    "M": "100",
    "N": "5",
    "FILE": "out.file",
    "F": "out.file",
    "NAME": "parcel",
    "JSON": "{}",
}


def _section() -> str:
    text = CLI_MD.read_text(encoding="utf-8")
    start = text.index("## Command map")
    return text[start : text.index("\n## ", start + 1)]


def _strip_optional(span: str) -> str:
    """Drop the [ ] markers that sit outside quotes; keep JSON brackets intact."""
    out: list[str] = []
    quote = ""
    for ch in span:
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch in "[]":
            continue
        out.append(ch)
    return "".join(out)


def _invocations() -> list[list[str]]:
    found = []
    for span in re.findall(r"`(regrid [^`]+)`", _section()):
        if "|" in span or "..." in span or span in {"regrid map", "regrid export"}:
            continue
        argv = shlex.split(_strip_optional(span))[1:]
        found.append(
            [
                re.sub(r"\b(L|M|N)\b", lambda m: PLACEHOLDERS[m.group(1)], tok)
                if tok not in PLACEHOLDERS
                else PLACEHOLDERS[tok]
                for tok in argv
            ]
        )
    return found


def test_command_map_is_not_empty() -> None:
    assert len(_invocations()) >= 12


@pytest.mark.parametrize("argv", _invocations(), ids=lambda argv: " ".join(argv)[:60])
def test_documented_invocation_parses(argv: list[str]) -> None:
    _parser().parse_args(argv)


_OFFLINE = {"fields", "map", "export", "address-map", "report", "client-token-typeahead"}


@pytest.mark.parametrize("argv", _invocations(), ids=lambda argv: " ".join(argv)[:60])
def test_documented_invocation_executes(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    from regrid import cli
    from regrid.client import RegridClient

    if argv[0] in _OFFLINE:
        pytest.skip("offline command makes no request")
    monkeypatch.setenv("REGRID_TOKEN", "test")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "out.file").write_text(
        '{"type":"Polygon","coordinates":[[[-75,39.9],[-75,40],[-74.9,40],[-75,39.9]]]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    verse = {"features": [{"properties": {"path": "/us/nj/camden"}}]}
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=verse if request.url.path.endswith("/verse") else {"parcels": {"features": []}},
        )
    )
    monkeypatch.setattr(
        cli,
        "RegridClient",
        lambda **kwargs: RegridClient(**{**kwargs, "transport": transport}),
    )
    concrete = {
        "LL_UUID": "00000000-0000-4000-8000-000000000000",
        "PATH": "/us/nj/camden/camden",
        "@FILE": "@out.file",
        '{"field":{"op":v}}': '{"owner":{"ilike":"smith"}}',
        "/us/<st>/<county>": "/us/nj/camden",
    }
    argv = [concrete.get(tok, tok) for tok in argv]
    assert cli.main(argv) == 0, (argv, capsys.readouterr().err)


def _walk(parser: "argparse.ArgumentParser") -> "tuple[set[str], dict[str, set[str]]]":
    """Return (subcommand names, {subcommand or "global": long option strings})."""
    names: set[str] = set()
    flags: dict[str, set[str]] = {}

    def visit(p: "argparse.ArgumentParser", owner: str) -> None:
        for action in p._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    names.add(name)
                    visit(sub, name)
            else:
                found = {
                    opt for opt in action.option_strings if opt.startswith("--") and opt != "--help"
                }
                if found:
                    flags.setdefault(owner, set()).update(found)

    visit(parser, "global")
    return names, flags


def _word(token: str) -> "re.Pattern[str]":
    return re.compile(rf"(?<![\w-]){re.escape(token)}(?![\w-])")


def test_cli_md_mentions_every_subcommand_and_flag() -> None:
    names, flags = _walk(_parser())
    lines = CLI_MD.read_text(encoding="utf-8").splitlines()
    missing = sorted(n for n in names if not any(_word(n).search(ln) for ln in lines))
    for owner, owned in flags.items():
        for flag in sorted(owned):
            flag_re = _word(flag)
            if owner == "global":
                ok = any(flag_re.search(ln) for ln in lines)
            else:
                cmd_re = _word(owner)
                ok = any(flag_re.search(ln) and cmd_re.search(ln) for ln in lines)
            if not ok:
                missing.append(f"{owner} {flag}")
    assert not missing, f"cli.md does not show on one line: {missing}"
