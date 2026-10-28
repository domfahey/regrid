# Regrid API reference

Reference saved October 27, 2026 from the Regrid OpenAPI specification and two guides supplied in conversation. This is a condensed reference, not a verbatim copy of the OpenAPI YAML. Account entitlements, prices, and live behavior have not been verified.

## Sources

- OpenAPI: version 3.0.0, Regrid specification version 2.0.0; supplied from https://dominic-fahey.regrid.com/profile/open_api
- Using an LLM with Regrid API; updated May 4, 2026.
- Tileserver API; updated March 23, 2026.
- Documentation: https://support.regrid.com/api
- Documentation index: https://support.regrid.com/llms.txt

## Parcel API

Base URL: `https://app.regrid.com/api/v2`

Authentication: `token` query parameter. Public schema endpoints explicitly disable authentication. Keep the main token server-side and redact it from logs and URLs shown to users.

| Endpoint | Purpose and notable parameters |
| --- | --- |
| GET or POST `/parcels/point` | Search by `lat` and `lon`, or Point/MultiPoint `geojson`; GeoJSON takes precedence. Optional radius in meters. |
| GET `/parcels/address` | Required `query`; restrict geography with `path`. |
| GET `/parcels/apn` | Required `parcelnumb`; use `path` to disambiguate geography. |
| GET `/parcels/owner` | Required `owner`; case-insensitive prefix matching, minimum four characters, Last, First format. Use `path` and `limit`. |
| GET `/parcels/query` | Up to four field filters using `fields[field_name][operator]`; optional geography and geometry filters. |
| GET or POST `/parcels/area` | Search by GeoJSON geometry, Feature, or FeatureCollection. Supports Polygon, MultiPolygon, Point, MultiPoint, LineString, and MultiLineString. Maximum area 80 square miles, including buffering. |
| GET `/parcels/typeahead` | Enterprise address autocomplete using `query`. |
| GET `/parcels/path` | Retrieve a single parcel by its canonical `path`. |
| GET `/parcels/{ll_uuid}` | Retrieve a single parcel by Regrid UUID. |
| GET `/client_token/typeahead` | Server generates a temporary typeahead-only client token. `exp` is a duration in seconds; default 86,400. Response includes `token` and `expires_at`. |
| GET `/usage` | Usage by billing cycle, date range, full history, or token. |
| GET `/usage/detailed` | Usage grouped by country and service. |
| GET `/verse` | County metadata, including refresh and source-data dates. |
| POST `/report` | Submit a data issue using `path` or `ll_uuid`, `comment`, and optional `details`. This creates an external report. |

Public schema endpoints: `/schemas/parcel`, `/schemas/building`, `/schemas/address`, `/schemas/enhanced_ownership`, `/schemas/zoning`, and `/schemas/ca`. The parcel schema accepts `premium_only`.

Canada equivalents include `/ca/parcels/point`, `/area`, `/address`, `/apn`, `/query`, `/path`, and `/{ll_uuid}`, plus `/ca/verse` and `/ca/usage`. Canadian paths use administrative divisions, for example `/ca/mb/division-no-22`. Available parameters and premium datasets differ from the US endpoints.

### Request controls

- `limit`: maximum parcel records returned. The LLM guide states a default of 20 and maximum of 1,000; the supplied schema does not encode those bounds.
- `offset_id`: cursor ID from a previous query for the next batch; documented on selected spatial and field-query endpoints.
- `return_count`: documented on point, area, and field-query endpoints, not address, APN, or owner searches. The specification does not establish whether count requests are unbilled or their exact interaction with record retrieval on every endpoint.
- `radius`: meters; documented default 0 and maximum 32,000.
- `path`: geographic restriction, such as `/us/tx/dallas`; `/parcels/path` instead takes a full parcel path.
- `return_custom`: default false; include county-specific fields.
- `return_field_labels`: default false; include readable field labels.
- `return_stacked`: default true; false returns the first parcel when geometries are identical. Suppressing stacked parcels can hide distinct records.
- `return_geometry`: controls geometry inclusion where supported; the description is malformed and should be verified.
- `return_custom_id`: default false; selected endpoints can associate results with input GeoJSON feature `properties.custom_id` values.
- `return_parcels`: set explicitly. Its description says default true, while its schema says default false.
- `return_zoning`, `return_matched_buildings`, `return_matched_addresses`, and `return_enhanced_ownership`: default true when supported by the account. Explicitly disable datasets that are not needed.

Parameter support varies by endpoint; do not append every flag indiscriminately.

### Responses

Parcel results are under `parcels.features`. Each feature can contain geometry and these properties:

- `headline`: display address, falling back to parcel number.
- `path` and `ll_uuid`: parcel identifiers.
- `fields`: standard parcel attributes and optional county-specific attributes.
- `field_labels`, `context`, and optionally matched `addresses`.
- `score`: present in the supplied US response schema; do not assume a calibrated confidence probability.

Matched buildings and zoning are separate top-level FeatureCollections when available. Count responses contain `count` and area measurements in square meters, acres, and square miles.

Usage includes requests, results, tiles, features, typeahead, addresses, buildings, ownership, zoning, and area. Detailed usage exposes parcel counts by country and service. These are consumption statistics, not a documented remaining-balance field. Allowances and spending ceilings must be obtained separately.

Usage filters: `return_full_history`, `begin_date`, `end_date`, `return_by_token`, and `return_by_this_token`. US date examples use `YYYY-MM-DD`; the Canadian descriptions and examples disagree on formatting.

## Tileserver API

Host: `https://tiles.regrid.com`. Each request requires `token`. The guide recommends separate Parcel API and Tileserver tokens.

| Resource | Path |
| --- | --- |
| Raster TileJSON | `/api/v1/parcels?token=<token>` |
| Vector TileJSON | `/api/v1/parcels?token=<token>&format=mvt` |
| Vector tile | `/api/v1/parcels/{z}/{x}/{y}.mvt?token=<token>` |
| Raster tile | `/api/v1/parcels/{z}/{x}/{y}.png?token=<token>` |
| Retina raster tile | `/api/v1/parcels/{z}/{x}/{y}@2x.png?token=<token>` |

Use the TileJSON `tiles` URLs. Metadata also includes a `vector` endpoint and a `grid` endpoint for raster UTF grids. PNG tiles have Regrid's default style; MVT supports application styling.

Zoom levels are 10 through 21. Outside this range, the guide says the service returns HTTP 200 with no content. Standard raster tiles are 256 pixels; `@2x` tiles are 512 pixels.

The supplied material does not specify vector source-layer names, vector feature fields, or exact tile billing rules.

## LLM usage and cost controls

The supplied LLM guide says parcel usage is billed by records returned, not merely requests. It describes self-serve allowances of 2,000 parcel records and 200,000 tiles, possible overages, an 80 percent parcel-usage notification, and a dashboard monthly-spend control. Verify the actual account configuration before relying on those amounts or controls.

Recommended application controls derived from the guide:

1. Enforce limits in tool code: typically one result for a specific address and two to five for general lookups.
2. Require geographic scope for broad owner and field searches.
3. Use supported count requests before broad retrieval; require user approval for more than 50 records. Verify count behavior and billing first.
4. Enforce per-task call and record budgets, bounded pagination, duplicate-query suppression, and bounded search expansion.
5. Monitor usage before expensive operations and periodically; compare consumption against the configured allowance.
6. Constrain geometry and radius. For spatial address lookup, geocode first and use a small radius; the guide gives 10 meters as an example.
7. Cache reusable results. The guide suggests 30 days; confirm applicable retention and licensing permissions.
8. Use tiles for map display and bounded Parcel API retrieval for a selected property.

`limit=1` limits retrieval but does not establish a unique or correct match. Ambiguous addresses, boundary points, and stacked parcels require explicit handling.

## Specification issues to resolve before implementation

- Preserve APNs as application strings despite the specification's integer type, to retain leading zeros, alphanumeric identifiers, and numeric precision.
- Set `return_parcels` explicitly because its documented and schema defaults conflict.
- Several polygon examples omit the closing coordinate. Valid rings must repeat the first coordinate and contain at least four positions.
- Example query strings are embedded in several OpenAPI path keys; normalize these to the actual endpoint with separate query parameters before client generation.
- Some request schemas constrain arrays more narrowly than endpoint descriptions, and some examples have inconsistent types.
- Typeahead centroid geometry is modeled as Polygon/MultiPolygon; verify the actual response before choosing a geometry model.
- `return_geometry` wording and some nullability declarations need review before generating strict response validators.
- Trial-token county restrictions and premium entitlement descriptions are not proof of this account's access.

No credentials are included in this reference.
