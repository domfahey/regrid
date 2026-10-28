# API Contract Coverage

This inventory tracks the Regrid OpenAPI 3.0.0 document with `info.version: 2.0.0` supplied in the project conversation. The base URL is `https://app.regrid.com/api/v2`. The supplied specification describes **33 distinct path-and-verb operations** after normalizing its five example paths containing query strings into `/parcels/query` or `/ca/parcels/query`.

`tests/test_api_contract.py` exercises all 33 operations through both the SDK and CLI. Fixtures assert the exact verb, host, path, complete query parameter set, authentication, request body, one-call behavior, and response preservation. Sixteen additional cases check endpoint-specific exclusions. These are mocked contract tests, not proof of live access, entitlements, data completeness, count billing, or current server behavior.

## Operation Inventory

All paths below are relative to `/api/v2`. `--options` carries the SDK keyword options as JSON. The same method names are available on `TypedRegridClient`.

| HTTP operation | SDK method | CLI command | Parameter profile |
| --- | --- | --- | --- |
| GET `/parcels/point` | `point` | `point` | US point GET |
| POST `/parcels/point` | `point(method="POST")` | `point --method POST` | US point POST |
| GET `/parcels/address` | `address` | `address` | US address |
| GET `/parcels/apn` | `apn` | `apn` | US APN |
| GET `/parcels/owner` | `owner` | `owner` | US owner |
| GET `/parcels/query` | `query` | `query --fields` | US query |
| GET `/parcels/area` | `area` | `area --geojson` | US area |
| POST `/parcels/area` | `area(method="POST")` | `area --method POST` | US area |
| GET `/parcels/typeahead` | `typeahead` | `typeahead` | `query` only |
| GET `/parcels/path` | `parcel_path` | `parcel-path` | Full `path` + C + P |
| GET `/parcels/{ll_uuid}` | `parcel` | `parcel` | UUID path argument + C + P |
| GET `/client_token/typeahead` | `client_token_typeahead` | `client-token-typeahead` | Optional `exp`; account token injected |
| GET `/schemas/parcel` | `schema("parcel")` | `schema parcel` | Optional `premium_only`; no authentication |
| GET `/schemas/building` | `schema("building")` | `schema building` | No parameters or authentication |
| GET `/schemas/address` | `schema("address")` | `schema address` | No parameters or authentication |
| GET `/schemas/enhanced_ownership` | `schema("enhanced_ownership")` | `schema enhanced_ownership` | No parameters or authentication |
| GET `/schemas/zoning` | `schema("zoning")` | `schema zoning` | No parameters or authentication |
| GET `/verse` | `verse` | `verse` | Optional `return_geometry` |
| GET `/usage` | `usage` | `usage` | U |
| GET `/usage/detailed` | `usage(detailed=True)` | `usage --detailed` | U |
| POST `/report` | `report` | `report` | Optional `path`, `ll_uuid`, `comment`, `details` |
| GET `/schemas/ca` | `schema("ca")` | `schema ca` | No parameters or authentication |
| GET `/ca/parcels/point` | `point(country="ca")` | `point --country ca` | Canada point GET |
| POST `/ca/parcels/point` | `point(country="ca", method="POST")` | `point --country ca --method POST` | Canada point POST |
| GET `/ca/parcels/area` | `area(country="ca")` | `area --country ca` | Canada area |
| POST `/ca/parcels/area` | `area(country="ca", method="POST")` | `area --country ca --method POST` | Canada area |
| GET `/ca/parcels/address` | `address(country="ca")` | `address --country ca` | Canada address |
| GET `/ca/parcels/{ll_uuid}` | `parcel(country="ca")` | `parcel --country ca` | UUID path argument + C |
| GET `/ca/parcels/apn` | `apn(country="ca")` | `apn --country ca` | Canada APN |
| GET `/ca/parcels/query` | `query(country="ca")` | `query --country ca --fields` | Canada query |
| GET `/ca/parcels/path` | `parcel_path(country="ca")` | `parcel-path --country ca` | Full `path` + C |
| GET `/ca/verse` | `verse(country="ca")` | `verse --country ca` | Optional `return_geometry` |
| GET `/ca/usage` | `usage(country="ca")` | `usage --country ca` | U |

## Complete Parameter Profiles

Every operation except the six `/schemas/*` operations authenticates with the client's `token` query parameter. Caller-supplied endpoint token overrides are rejected.

- **C:** `return_custom`, `return_field_labels`, `return_stacked`.
- **P:** `return_zoning`, `return_matched_buildings`, `return_matched_addresses`, `return_enhanced_ownership`, `return_parcels`.
- **S:** `radius`, `limit`, `return_count`.
- **G:** `offset_id`, `return_geometry`.
- **U:** `return_full_history`, `begin_date`, `end_date`, `return_by_token`, `return_by_this_token`.

| Profile | Documented inputs |
| --- | --- |
| US point GET | `lat`, `lon`, query `geojson`, C + P + S + G, `return_custom_id` |
| US point POST | `lat`, `lon`, JSON body `geojson`, C + P + S, `return_custom_id` |
| Canada point GET | `lat`, `lon`, query `geojson`, C + S + G |
| Canada point POST | `lat`, `lon`, JSON body `geojson`, C + S |
| US area GET/POST | Query/body `geojson`, C + P + S + G, `return_custom_id` |
| Canada area GET/POST | Query/body `geojson`, C + S + G |
| US address | Required `query`, optional geographic `path`, `limit`, C + P |
| Canada address | Required `query`, optional geographic `path`, `limit`, C |
| US APN | Required `parcelnumb`, optional geographic `path`, `limit`, C + P |
| Canada APN | Required `parcelnumb`, optional geographic `path`, `limit`, C |
| US owner | Required `owner`, optional geographic `path`, `limit`, C + P |
| US query | `fields[field][operator]`, query `geojson`, geographic `path`, C + P + S + G, `return_custom_id` |
| Canada query | `fields[field][operator]`, query `geojson`, geographic `path`, C + S + G |

The query methods accept up to four field names, with one or more operators per field. Field/operator names are serialized as individual query parameters; lists and other structured values are JSON-encoded. Supported server-side field names and operators depend on Regrid's separately maintained query-field documentation.

POST point intentionally has neither `offset_id` nor `return_geometry`: both are absent from the supplied POST parameter lists. They remain supported on GET point and both area methods. Canada has no documented owner, typeahead, or detailed-usage route; the SDK rejects those combinations rather than inventing endpoints. `confidence_score` is commented out as a future feature in the supplied specification and is not part of the implemented contract.

## Response Coverage and Compatibility

The raw SDK and CLI preserve response dictionaries and unknown fields. Typed response models cover the supplied envelopes: parcel features and count responses, typeahead centroids, public schemas, county metadata, usage/history/token breakdowns, detailed usage, report acknowledgements, and temporary tokens. Geometry is a discriminated union. County-specific parcel fields remain dynamic because the specification delegates their definitions to the schema endpoint.

Response-field modeling is independent of route coverage. Known premium and metadata properties can be modeled without restricting future fields: response models must continue allowing extras, preserving explicit nulls, and serializing aliases. Model-contract tests live separately from operation tests in `tests/test_models.py` and the typed-client tests.

## Deliberate Specification Resolutions

- Preserve APNs as strings despite their integer schema, because the description supports alphanumeric identifiers and leading zeros.
- Send `return_parcels=True` explicitly when supported unless the caller overrides it; the specification's description and default disagree.
- Use `YYYY-MM-DD` for usage dates, consistent with examples; the Canadian prose also contains a conflicting slash format.
- Accept Point/MultiPoint inputs according to endpoint descriptions instead of enforcing the overly narrow two-point POST example schema.
- Preserve the API's GeoJSON precedence when both geometry and latitude/longitude are supplied. Polygon topology and maximum search area remain server-validated.
- Do not turn sample query strings into literal URL paths or copy the malformed/unclosed polygon examples.

## Tileserver Scope

The separate Tileserver guide uses `https://tiles.regrid.com`, so its TileJSON, raster/vector tile, retina, and UTFGrid support is not part of the 33-operation OpenAPI count. Tileserver tests and documentation must be evaluated separately. No credential-bearing requests are needed for these mocked contract checks.

## Verification Boundaries

Run `.venv/bin/python -m pytest tests/test_api_contract.py` for the operation matrix. Run `make check` for integration with the rest of the suite. `make e2e` verifies local HTTPS and subprocess behavior when localhost binding is permitted. Actual Regrid access, account entitlements, source-data freshness, and billing semantics require separately authorized live checks and must not be inferred from mocks or coverage percentages.
