# Parcel Schema Guidance

Reviewed October 27, 2026 against the [schema landing page](https://support.regrid.com/docs/regrid-parcel-schemas) and its category references. This supplements the supplied July 9 table with interpretation and metadata; it does not establish live API compatibility or account entitlement.

## Inventory and Scope

The category counts total **169**, not 179. Treat these as the website's advertised counts, not an independent count of distinct API fields. The reviewed category headings did not identify a clearly new field absent from the supplied table. Preserve the supplied SQL datatypes when category prose uses abbreviations such as `timestamptz` or simplifies `bigint` to integer.

| Category reference | Advertised fields | Catalog concern |
| --- | ---: | --- |
| [Identification](https://support.regrid.com/docs/identification) | 15 | Stable keys and identifiers |
| [Land Use & Zoning](https://support.regrid.com/docs/land-use-zoning) | 16 | Local versus standardized classifications |
| [Buildings & Structures](https://support.regrid.com/docs/buildings-structures) | 18 | Counts, floor area, and footprint distinctions |
| [Assessment & Tax](https://support.regrid.com/docs/assessment-tax) | 8 | Valuation method and tax year |
| [Sales & Transfers](https://support.regrid.com/docs/sales-transfers) | 3 | Market sales versus other transfers |
| [Ownership](https://support.regrid.com/docs/ownership) | 11 | Owner names and ownership categories |
| [Addresses](https://support.regrid.com/docs/addresses) | 41 | Situs, mailing, and postal validation |
| [Parcel Geometry & Area](https://support.regrid.com/docs/parcel-geometry-area-fields) | 10 | Geometry-derived and recorded area |
| [Legal Description & Subdivision](https://support.regrid.com/docs/legal-description-subdivision) | 7 | Local record references |
| [Related Geographies](https://support.regrid.com/docs/related-geographies) | 12 | Geographic joins and local neighborhoods |
| [Environment & Risk](https://support.regrid.com/docs/environment-risk) | 13 | Source dates, scale, and applicability |
| [Public Lands & Access](https://support.regrid.com/docs/public-lands-access) | 1 | Access designation |
| [Infrastructure & Proximity](https://support.regrid.com/docs/infrastructure-proximity) | 2 | Right-of-way flags and distance units |
| [Socioeconomics & Markets](https://support.regrid.com/docs/socioeconomics-markets) | 8 | Blockgroup metrics and percentage units |
| [Source & Lineage](https://support.regrid.com/docs/source-lineage) | 4 | Dataset refresh versus row modification |

## Recommended Catalog Additions

These are design recommendations, not a claim that every item is implemented:

- Record category, units, documentation URL, and coverage-report column alongside type and tier. Keep missing metadata explicitly unknown.
- Represent standardization as `yes`, `no`, `some`, or `not_applicable`, with null for unknown. For example, `owner` is partially standardized; `ll_updated_at` is marked not applicable. A boolean loses information.
- Keep preferred alternatives separate from related fields. A related field may answer a different question rather than replace the original.
- Track queryability independently from response availability. Premium status does not imply query support. Store the evidence source and review date for query rules.
- Preserve human-readable aliases for local catalog search only; do not silently rewrite them into API field names.

The [landing page](https://support.regrid.com/docs/regrid-parcel-schemas) defines the metadata vocabulary and `{fieldname}_pct` coverage convention. The [ownership](https://support.regrid.com/docs/ownership) and [lineage](https://support.regrid.com/docs/source-lineage) entries demonstrate why standardization needs more than two states.

## Interpretation Rules

| Question | Recommended interpretation |
| --- | --- |
| Track a parcel across updates | Use `ll_uuid`; APNs, `ogc_fid`, and `path` are not guaranteed persistent nationwide keys. `ll_stack_uuid` groups coincident geometries, not primary parcels. [Identification](https://support.regrid.com/docs/identification) |
| Compare land use or zoning across counties | Prefer LBCS classifications for land use and `zoning_type`/`zoning_subtype` for standardized zoning. Local `usecode`, `usedesc`, and `zoning` retain jurisdiction-specific meaning. [Land Use & Zoning](https://support.regrid.com/docs/land-use-zoning) |
| Measure parcel size | Prefer `ll_gisacre` or `ll_gissqft` for consistent geometry-derived area. Deeded acreage is a legal-record value; county acreage can use different methods. [Parcel Geometry & Area](https://support.regrid.com/docs/parcel-geometry-area-fields) |
| Count houses or measure buildings | `ll_bldg_count` includes outbuildings. `ll_bldg_footprint_sqft` measures ground footprint. `recrdareano` describes habitable/taxable area across floors; check `area_building_definition` before comparisons. [Buildings & Structures](https://support.regrid.com/docs/buildings-structures) |
| Estimate market value | Inspect `parvaltype` before interpreting `parval`. Assessment methods differ; the figure is not necessarily a resale estimate. [Assessment & Tax](https://support.regrid.com/docs/assessment-tax) |
| Identify a market sale | Keep `saledate` separate from `last_ownership_transfer_date`. Nominal sale prices may represent administrative transfers. [Sales & Transfers](https://support.regrid.com/docs/sales-transfers) |
| Find the site city | Use `scity`; `city` is a Census subdivision. Mailing addresses may differ from parcel addresses. [Addresses](https://support.regrid.com/docs/addresses) |
| Interpret vacancy or missing risk values | Preserve nulls and codes. A FEMA NRI “No Rating” value is not null; CDL availability is limited to parcels of at least ten acres. [Environment & Risk](https://support.regrid.com/docs/environment-risk) |
| Interpret demographic growth | Metrics describe the Census blockgroup, not the individual parcel. Growth values are already percentages: `0.15` means 0.15%, not 15%. [Socioeconomics & Markets](https://support.regrid.com/docs/socioeconomics-markets) |
| Check freshness | `ll_last_refresh` describes the county refresh; `ll_updated_at` changes for any row edit. Neither proves every attribute was newly observed. [Source & Lineage](https://support.regrid.com/docs/source-lineage) |

## Query and Coverage Follow-ups

The [query guide](https://support.regrid.com/docs/filter-parcels-query-by-field) and category pages overlap but are not perfectly consistent. For example, the [building page](https://support.regrid.com/docs/buildings-structures) explicitly marks `struct` queryable, although it is absent from the guide's main field table; the guide includes a boolean example and restricts boolean-like fields to `eq`, `ne`, and `isnull`. Keep an explicit validation escape hatch for upstream additions and document evidence-based exceptions.

A future coverage helper should request one state or county, locate columns by header name, retain the retrieval date, and distinguish zero fill from missing coverage. Avoid fetching the entire spreadsheet by default. This is a separate enhancement from parcel retrieval; the published fill rate does not establish the accuracy or availability of a particular parcel value. [Coverage access instructions](https://support.regrid.com/docs/regrid-parcel-schemas)

Do not add automatic billing calls, coverage fetches, data conversions, or inferred classifications during response validation. Catalog guidance should inform callers without changing raw API values.
