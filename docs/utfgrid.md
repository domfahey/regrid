# UTFGrid retrieval

Regrid's [Tileserver API documentation](https://support.regrid.com/docs/tileserver-api) advertises a `grid` endpoint in raster TileJSON. It does not publish a fixed UTFGrid path, so the SDK follows metadata rather than inventing an endpoint URL.

`RegridClient.grid(z, x, y, metadata=None)` validates tile indices, obtains raster TileJSON when needed, and requests one grid. Supplying previously fetched metadata avoids repeating discovery. It accepts a `grid` template string or list and the TileJSON `grids` list form; lists select their first endpoint. Templates can be absolute or relative to the configured tileserver base URL.

Only `{z}`, `{x}`, `{y}`, and an optional `{token}` placeholder are resolved. Retrieval requires the same HTTPS origin, including port, as the configured tileserver. Credentials, fragments, unknown placeholders, control characters, and cross-origin templates are rejected before the grid request. Metadata token values are discarded; the current client's token is injected by its normal transport. Other query parameters are preserved, including repeated values.

```python
with RegridClient(token=os.environ["REGRID_TOKEN"]) as client:
    metadata = client.tilejson(format="png")
    grid = client.grid(15, 8828, 12121, metadata=metadata)
```

The CLI equivalent is `regrid grid 15 8828 12121`; use `--metadata @tilejson.json` to reuse metadata. `TypedRegridClient.grid()` returns a strict `UTFGridResponse` with `grid`, `keys`, and `data` attributes and preserves unknown fields.

Raw grid JSON is returned unchanged. A typical UTFGrid response contains `grid` rows, `keys`, and a `data` map. Authentication, HTTP status handling, JSON validation, and disabled redirects/retries use the existing client transport. No live Regrid request is made by the unit tests.
