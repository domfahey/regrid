"""Each command's `--options` help example must be accepted by that command."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from regrid import cli
from regrid.client import RegridClient

# Calls each --options command through the same endpoint method the CLI dispatches to.
CALLS: dict[str, Callable[[RegridClient, dict[str, Any]], Any]] = {
    "point": lambda c, o: c.point(lat=39.9, lon=-75.1, **o),
    "area": lambda c, o: c.area({"type": "Point", "coordinates": [-75.1, 39.9]}, **o),
    "address": lambda c, o: c.address("1 Main St", **o),
    "apn": lambda c, o: c.apn("123", **o),
    "owner": lambda c, o: c.owner("Smith", **o),
    "query": lambda c, o: c.query({"owner": {"ilike": "smith"}}, **o),
    "parcel": lambda c, o: c.parcel("00000000-0000-4000-8000-000000000000", **o),
    "parcel-path": lambda c, o: c.parcel_path("/us/nj/camden/camden", **o),
    "verse": lambda c, o: c.verse(**o),
    "usage": lambda c, o: c.usage(**o),
    "schema": lambda c, o: c.schema("parcel", **o),
}


def _options_help() -> dict[str, str]:
    parser = cli._parser()
    subparsers = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    helps: dict[str, str] = {}
    for name, sub in subparsers.choices.items():
        for action in sub._actions:
            if action.dest == "options":
                helps[name] = action.help or ""
    return helps


def test_every_options_command_is_exercised() -> None:
    assert set(_options_help()) == set(CALLS)


@pytest.mark.parametrize("command", sorted(CALLS))
def test_help_example_is_accepted_by_its_command(command: str) -> None:
    help_text = _options_help()[command]
    match = re.search(r"e\.g\. '(\{.*?\})'", help_text)
    assert match, f"{command} --options help has no example: {help_text!r}"
    options = json.loads(match.group(1))
    assert isinstance(options, dict)
    client = RegridClient(
        "test", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    )
    # Validation runs before any request; a rejected key raises here.
    CALLS[command](client, options)
