"""Opt-in parcel validation must not alter the raw response contract."""

import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from regrid import RegridDecodeError, TypedRegridClient
from regrid.models import ParcelProperties
from regrid.parcel_fields import ParcelFields


def test_typed_access_preserves_original_payload_and_identifier_strings():
    fields = {
        "parcelnumb": "000123-A",
        "geoid": "06037",
        "szip": "00123",
        "lat": "32.50",
        "lon": "-96.00",
        "ll_uuid": "8B6F4F51-58AD-4969-93B3-FDFB348A7084",
        "saledate": "2024-02-29",
        "ll_updated_at": "2026-07-09T13:22:32.000Z",
        "saleprice": 125000,
        "ll_gisacre": 1.25,
        "struct": True,
        "county_future_field": {"code": "001", "values": [1, None]},
    }
    payload = {"parcels": {"features": [{"properties": {"fields": fields}}]}}
    with TypedRegridClient(
        "mock-token", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        response = client.address("Example")
    properties = response.parcels.features[0].properties
    typed = properties.typed_fields
    assert typed.parcelnumb == "000123-A"
    assert typed.geoid == "06037"
    assert typed.lat == "32.50"
    assert typed.ll_uuid == "8B6F4F51-58AD-4969-93B3-FDFB348A7084"
    assert isinstance(typed.saleprice, int)
    assert typed.to_dict() == fields
    assert response.to_dict() == payload
    assert properties.fields == fields


@pytest.mark.parametrize("fields", [None, {}, {"owner": None}])
def test_absent_null_and_empty_fields_are_distinct(fields):
    properties = ParcelProperties.model_validate({"fields": fields})
    typed = properties.typed_fields
    assert (typed.to_dict() if typed is not None else None) == fields
    assert properties.to_dict() == {"fields": fields}
    absent = ParcelProperties.model_validate({})
    assert absent.typed_fields is None
    assert absent.to_dict() == {}


@pytest.mark.parametrize(
    "field,value",
    [
        ("parcelnumb", 123),
        ("geoid", 6037),
        ("lat", 32.5),
        ("yearbuilt", "2001"),
        ("yearbuilt", True),
        ("yearbuilt", 2001.5),
        ("struct", "true"),
        ("struct", 1),
        ("saleprice", True),
        ("saleprice", "125000"),
        ("saleprice", float("inf")),
        ("ll_gisacre", float("nan")),
        ("saledate", "2023-02-29"),
        ("saledate", "20240709"),
        ("saledate", "2024-02-29T00:00:00Z"),
        ("ll_updated_at", "2026-07-09T12:00:00"),
        ("ll_updated_at", "not-a-timestamp"),
        ("ll_uuid", "not-a-uuid"),
    ],
)
def test_opt_in_rejects_bad_known_fields_without_changing_raw(field, value):
    properties = ParcelProperties.model_validate({"fields": {field: value}})
    assert properties.fields[field] is value
    with pytest.raises(RegridDecodeError, match="Parcel fields failed schema validation") as error:
        properties.typed_fields
    assert error.value.__context__ is None
    assert error.value.__cause__ is None
    with pytest.raises(ValidationError):
        ParcelFields.model_validate({field: value})


def test_property_validates_current_fields_instead_of_returning_stale_cached_values():
    properties = ParcelProperties(fields={"owner": "First owner"})
    assert properties.typed_fields.owner == "First owner"
    properties.fields["owner"] = "New owner"
    assert properties.typed_fields.owner == "New owner"


def test_opt_in_validation_does_not_leak_sensitive_input():
    properties = ParcelProperties(fields={"yearbuilt": "private-record-value"})
    with pytest.raises(RegridDecodeError) as error:
        properties.typed_fields
    assert "private-record-value" not in str(error.value)
    assert error.value.__context__ is None


def test_generated_attributes_match_catalog_without_runtime_model_construction():
    result = subprocess.run(
        [sys.executable, "scripts/generate_parcel_fields.py", "--check"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
