"""Catalog correctness independent of generated response models."""

import json
from importlib.resources import files

import pytest
from pydantic import ValidationError

from regrid.catalog import CATALOG_VERSION, PARCEL_FIELDS, ParcelCatalog, load_catalog


def test_catalog_matches_supplied_snapshot_and_preserves_identifier_types():
    assert CATALOG_VERSION == "2026-07-09"
    assert len(PARCEL_FIELDS) == 169
    assert list(PARCEL_FIELDS)[0] == "ogc_fid"
    assert list(PARCEL_FIELDS)[-1] == "lowest_parcel_elevation"
    for name in ("geoid", "parcelnumb", "tax_id", "szip", "lat", "lon", "cdl_raw"):
        assert PARCEL_FIELDS[name].datatype == "text"
    assert PARCEL_FIELDS["ll_uuid"].datatype == "uuid"
    assert PARCEL_FIELDS["ll_stack_uuid"].datatype == "text"
    assert PARCEL_FIELDS["ll_gissqft"].datatype == "bigint"
    assert PARCEL_FIELDS["year_built_effective_date"].datatype == "integer"
    assert PARCEL_FIELDS["ll_updated_at"].datatype == "timestamp with time zone"


def test_tier_query_and_coverage_metadata_are_distinct():
    assert PARCEL_FIELDS["owner"].tier == "standard"
    assert PARCEL_FIELDS["zoning_type"].tier == "premium"
    assert PARCEL_FIELDS["owner"].queryable is True
    assert PARCEL_FIELDS["struct"].queryable is True
    assert PARCEL_FIELDS["tax_id"].queryable is False
    assert PARCEL_FIELDS["geoid"].coverage_column == "geoid_pct"
    assert PARCEL_FIELDS["city"].preferred_alternatives == ("scity",)


def test_catalog_entries_and_mapping_cannot_be_mutated():
    with pytest.raises(TypeError):
        PARCEL_FIELDS["owner"] = PARCEL_FIELDS["parcelnumb"]
    with pytest.raises(ValidationError, match="frozen"):
        PARCEL_FIELDS["parcelnumb"].datatype = "integer"


def test_packaged_catalog_loads_outside_repository(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    catalog = load_catalog()
    assert catalog.country == "us"
    assert catalog.metadata_reviewed_on == "2026-10-27"
    assert catalog.query_documentation_url.endswith("/filter-parcels-query-by-field")
    assert catalog.fields[0].name == "ogc_fid"
    assert catalog.fields[-1].name == "lowest_parcel_elevation"


@pytest.mark.parametrize("problem", ["duplicate", "alternative", "datatype", "extra"])
def test_invalid_catalog_changes_fail_before_use(problem):
    data = json.loads(files("regrid").joinpath("data/parcel_fields.json").read_text())
    if problem == "duplicate":
        data["fields"].append(data["fields"][0])
    elif problem == "alternative":
        data["fields"][0]["preferred_alternatives"] = ["nonexistent_field"]
    elif problem == "datatype":
        data["fields"][0]["datatype"] = "money"
    else:
        data["fields"][0]["typo"] = True
    with pytest.raises(ValidationError):
        ParcelCatalog.model_validate_json(json.dumps(data))
