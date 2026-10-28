# Response Model Coverage

The typed client validates the response structures and field types defined by the supplied Regrid OpenAPI 3.0 document (API specification version 2.0.0). Enhanced ownership fields additionally follow Regrid's [Enhanced Ownership Schema](https://support.regrid.com/docs/enhanced-ownership-schema); their nested array location follows [Input and Output Formats](https://support.regrid.com/docs/input-and-output-formats).

## Model Inventory

| API structure | Python model | Coverage |
| --- | --- | --- |
| Parcel search response | `ParcelResponse`, `ParcelCollection`, `ParcelFeature`, `ParcelProperties` | Parcel envelope, identifiers, score, context, county fields, matched addresses, enhanced ownership, and premium collections |
| Matched secondary addresses | `MatchedAddress` | All 37 supplied address fields, including string-valued coordinates, postal codes, and identifiers |
| Enhanced ownership | `EnhancedOwnership` | All 60 documented fields; `eo_last_refresh` retains its date string |
| Matched buildings | `BuildingCollection`, `BuildingFeature`, `BuildingProperties` | All 19 supplied property fields, including parcel UUID lists and height-addon measures |
| Standardized zoning | `ZoningCollection`, `ZoningFeature`, `ZoningProperties` | All 26 supplied property fields, including nested `landuse_classes` and dimensional standards |
| Parcel count and area | `CountResponse`, `AreaMeasurements` | Nonnegative integer count and supplied area units |
| Typeahead | `TypeaheadResponse`, `TypeaheadCollection`, `TypeaheadFeature`, `TypeaheadProperties` | All five property fields and feature ID; Point and documented polygon geometries supported |
| Public field schemas | `SchemaResponse`, `SchemaField` | Typed wrapped and direct field maps through `field_definitions`; `schema_` and raw extras remain available |
| Usage | `UsageResponse` and nested cycle/history/token models | All supplied ordinary usage fields |
| Detailed usage | `DetailedUsageResponse` and nested rows/history models | Country/service grouping, parcel/addon counts, dates, and area |
| US and Canadian source metadata | `VerseResponse`, `VerseFeature`, `VerseProperties` | All supplied property names, including `admin2_slug`, `admin2_center`, and `shapefile_size_flag` |
| Temporary client token | `ClientTokenResponse` | Secret token and expiration; explicit export reveals token intentionally |
| Data issue report | `ReportResponse` | Message and report ID |
| TileJSON | `TileJSON` | Tile URLs and common metadata; unknown TileJSON extensions retained |
| GeoJSON | Discriminated `Geometry` union | Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon, and GeometryCollection |

## Compatibility and Deliberate Flexibility

All response models retain unknown fields and distinguish absent values from explicit nulls when using `to_dict()`. Known values are validated strictly rather than coerced; APNs, address coordinates, and ownership identifiers retain source strings. Optional property values permit null because source datasets can omit values. Date strings and URLs are retained without normalization.

The dynamic standard parcel `fields` dictionary is intentional: the supplied specification defines it as an open object, with county-specific and premium attributes obtained through the public schema endpoint. Its keys are not replaced with an invented fixed schema. Scalar metadata alongside direct schema maps remains untouched; direct map object entries are validated as `SchemaField`. Single-description schema responses remain lossless.

Building, zoning, matched-address, enhanced-ownership, and typeahead properties now expose typed attributes. To obtain their dictionary form, use `to_dict()`; the raw client and CLI still return dictionaries. This extends the initial typed client's formerly dynamic property objects.

Geometry nesting and numeric types are validated, but polygon closure, winding, geographic area, and topology remain server responsibilities. The centroid schema's Polygon/MultiPolygon declaration conflicts with its centroid purpose, so Point geometry is also supported. US/Canada population is preserved as integer or string because the supplied country schemas differ.

## Verification

`tests/test_complete_models.py` tests every documented addon property's type, nested typed-client decoding, schema-map variants, typeahead geometries, missing/null/empty distinctions, unknown-field roundtrips, and sanitized failures. These are mocked contract tests; they do not establish live account entitlements or real-service response compatibility.
