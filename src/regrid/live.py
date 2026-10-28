"""Explicit, bounded live-service smoke test; never imported by ordinary checks."""

from __future__ import annotations

import logging
import os

from .catalog import PARCEL_FIELDS
from .client import RegridClient
from .models import ParcelResponse, SchemaResponse, UsageResponse

DEFAULT_ADDRESS = "24 pennbrook dr haddonfield nj 08033"


def run(client: RegridClient, address: str) -> int:
    """Run at most four requests; print status and aggregate counts only."""
    stage = "public schema"
    try:
        schema = SchemaResponse.model_validate(client.schema("parcel"))
        definitions = schema.field_definitions
        if not definitions:
            print("FAIL public schema: no field definitions")
            return 1
        mismatches = sum(
            field.type is not None and field.type != PARCEL_FIELDS[name].datatype
            for name, field in definitions.items()
            if name in PARCEL_FIELDS
        )
        print(f"PASS public schema: {len(definitions)} definitions; {mismatches} type differences")
        # Report drift without treating added/removed fields as a service failure.
        if mismatches:
            print("NOTE schema differs from local catalog; typed validation may fail")
        stage = "usage baseline"
        baseline = UsageResponse.model_validate(client.usage())
        print("PASS usage baseline")
    except Exception:
        print(f"FAIL {stage}: request or response validation failed")
        return 1

    status = 0
    try:
        payload = client.address(
            address,
            limit=1,
            return_parcels=True,
            return_stacked=False,
            return_zoning=False,
            return_matched_buildings=False,
            return_matched_addresses=False,
            return_enhanced_ownership=False,
        )
        response = ParcelResponse.model_validate(payload)
        if response.parcels is None or len(response.parcels.features) != 1:
            print("FAIL parcel lookup: expected exactly one result; no expanded search attempted")
            status = 1
        else:
            properties = response.parcels.features[0].properties
            if properties is None or properties.typed_fields is None:
                print("FAIL parcel validation: missing properties or fields")
                status = 1
            else:
                print("PASS one-record lookup and typed fields (same response)")
                print("NOTE a returned result does not confirm the address is an exact match")
    except Exception:
        print("FAIL parcel lookup or typed validation")
        status = 1
    # Always attempt final usage after a potentially billable request, even on failure.
    try:
        final = UsageResponse.model_validate(client.usage())
        before, after = baseline.usage.cycle_usage, final.usage.cycle_usage
        if (
            before is not None
            and after is not None
            and before.results is not None
            and after.results is not None
            and baseline.usage.cycle_dates == final.usage.cycle_dates
        ):
            print(f"PASS final usage: observed record delta {after.results - before.results}")
        else:
            print("PASS final usage: comparable record counters unavailable")
        print("NOTE usage may lag or include other clients; delta is not a billing guarantee")
    except Exception:
        print("FAIL final usage: consumption could not be checked")
        status = 1
    return status


def main() -> int:
    """Require explicit configuration; never read .env or print exception details."""
    token = os.environ.get("REGRID_TOKEN", "").strip()
    address = os.environ.get("REGRID_LIVE_ADDRESS", "").strip() or DEFAULT_ADDRESS
    if not token or token == "replace_with_your_regrid_api_token":
        print("NOT RUN: set REGRID_TOKEN in your environment")
        return 2
    # HTTPX logging can reveal query-string credentials. Suppress it for this process.
    logging.disable(logging.CRITICAL)
    try:
        with RegridClient(token, max_limit=1, default_limit=1) as client:
            return run(client, address)
    except Exception:
        print("FAIL live smoke test initialization")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
