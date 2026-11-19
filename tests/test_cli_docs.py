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


def _walk(parser: argparse.ArgumentParser) -> tuple[set[str], dict[str, set[str]]]:
    """Return (subcommand names, {subcommand or "global": long option strings})."""
    names: set[str] = set()
    flags: dict[str, set[str]] = {}

    def visit(p: argparse.ArgumentParser, owner: str) -> None:
        # argparse has no public API for listing actions or subparsers; use the private ones.
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


def _word(token: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w-]){re.escape(token)}(?![\w-])")


def _command(name: str) -> re.Pattern[str]:
    """A subcommand shown as code: `regrid NAME` or a backtick right before NAME."""
    return re.compile(rf"(?:regrid |`){re.escape(name)}(?![\w-])")


def test_cli_md_mentions_every_subcommand_and_flag() -> None:
    names, flags = _walk(_parser())
    lines = CLI_MD.read_text(encoding="utf-8").splitlines()
    missing = sorted(n for n in names if not any(_command(n).search(ln) for ln in lines))
    for owner, owned in flags.items():
        for flag in sorted(owned):
            flag_re = _word(flag)
            if owner == "global":
                ok = any(flag_re.search(ln) for ln in lines)
            else:
                cmd_re = _command(owner)
                ok = any(flag_re.search(ln) and cmd_re.search(ln) for ln in lines)
            if not ok:
                missing.append(f"{owner} {flag}")
    assert not missing, f"cli.md does not show on one line: {missing}"


def _options_bullets() -> list[tuple[list[str], list[str], str]]:
    """Return (commands, backticked keys, text) for each `--options` bullet in cli.md."""
    text = CLI_MD.read_text(encoding="utf-8")
    bullets = re.findall(r"^- (`--options` on .+?)(?=\n- |\n\n)", text, re.M | re.S)
    out = []
    for raw in bullets:
        head, _, body = " ".join(raw.split()).partition(": ")
        commands = re.findall(r"`([a-z-]+)`", head.replace("`--options`", ""))
        # Only the first sentence names keys; later ones (e.g. "`typeahead` takes no ...") do not.
        sentence = re.split(r"(?<=[.)])\.? (?=[A-Z`])", body)[0]
        accepted = re.sub(r"\([^)]*rejected\)", "", sentence)  # "(`limit` is rejected)"
        out.append((commands, re.findall(r"`([a-z_]+)`", accepted), body))
    return out


def _probe_client() -> object:
    from regrid.client import RegridClient

    return RegridClient(
        "test", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    )


def _accepts(command: str, key: str, value: object) -> bool:
    """Ask the real endpoint method whether it accepts one --options key (US country)."""
    client = _probe_client()
    point = {"lat": 39.9, "lon": -75.1}
    calls = {
        "point": lambda o: client.point(**point, **o),  # type: ignore[attr-defined]
        "area": lambda o: client.area({"type": "Point", "coordinates": [-75.1, 39.9]}, **o),  # type: ignore[attr-defined]
        "address": lambda o: client.address("1 Main St", **o),  # type: ignore[attr-defined]
        "apn": lambda o: client.apn("123", **o),  # type: ignore[attr-defined]
        "owner": lambda o: client.owner("Smith", **o),  # type: ignore[attr-defined]
        "query": lambda o: client.query({"owner": {"ilike": "smith"}}, **o),  # type: ignore[attr-defined]
        "parcel": lambda o: client.parcel("00000000-0000-4000-8000-000000000000", **o),  # type: ignore[attr-defined]
        "parcel-path": lambda o: client.parcel_path("/us/nj/camden/camden", **o),  # type: ignore[attr-defined]
        "verse": lambda o: client.verse(**o),  # type: ignore[attr-defined]
        "usage": lambda o: client.usage(**o),  # type: ignore[attr-defined]
        "schema": lambda o: client.schema("parcel", **o),  # type: ignore[attr-defined]
    }
    try:
        calls[command]({key: value})
    except (ValueError, TypeError):
        return False
    return True


# One valid value per key type, so a rejection means "unsupported key", not "bad value".
_SAMPLE = {"limit": 1, "begin_date": "2024-01-01", "end_date": "2024-01-31"}


def _sample(key: str) -> object:
    return _SAMPLE.get(key, True)


def test_options_bullets_are_found() -> None:
    commands = {c for cmds, _, _ in _options_bullets() for c in cmds}
    assert {"point", "parcel", "parcel-path", "verse", "usage", "schema"} <= commands


def test_documented_options_keys_are_accepted() -> None:
    from regrid.endpoints import _parcel_options

    bad = []
    for commands, keys, _ in _options_bullets():
        for command in commands:
            for key in keys:
                if not _accepts(command, key, _sample(key)):
                    bad.append(f"{command} --options {key}")
    assert not bad, f"cli.md names keys the code rejects: {bad}"
    # return_* flags: the doc says "return flags" without listing them; spot-check the set.
    assert any(k.startswith("return_") for k in _parcel_options("us"))


def test_documented_options_sets_are_exact_for_verse_usage_schema() -> None:
    from regrid.endpoints import _USAGE, _parcel_options

    # Every key name the code knows about, probed against the real methods.
    universe = _parcel_options("us") | _USAGE | {"limit", "path", "premium_only", "return_geometry"}
    documented = {c: set(k) for cmds, k, _ in _options_bullets() for c in cmds}
    for command in ("verse", "usage", "schema"):
        accepted = {k for k in universe if _accepts(command, k, _sample(k))}
        assert documented[command] == accepted, command
    # Cross-check the usage set against the code constant, not just the probe.
    assert documented["usage"] == set(_USAGE)


def test_parcel_commands_reject_limit_and_doc_says_so() -> None:
    for command in ("parcel", "parcel-path"):
        assert not _accepts(command, "limit", 1)
    for command in ("point", "area", "address", "apn", "owner", "query"):
        assert _accepts(command, "limit", 1)
    for commands, keys, body in _options_bullets():
        if "parcel" in commands:
            assert "limit" not in keys
            assert "`limit` is rejected" in body


def test_typeahead_takes_no_options() -> None:
    import inspect

    from regrid.endpoints import EndpointsMixin

    params = inspect.signature(EndpointsMixin.typeahead).parameters.values()
    assert not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params)
    assert "takes no `--options`" in CLI_MD.read_text(encoding="utf-8")
