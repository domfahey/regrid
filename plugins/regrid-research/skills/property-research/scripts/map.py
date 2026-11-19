"""Offline parcel map renderer: validates a saved Regrid response and writes an HTML page.

Uses only the standard library, makes no network requests, and never reads credentials.
The generated page loads Leaflet and Esri imagery in the viewer's browser.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import math
import os
import re
import secrets
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

R = 6378137.0
SQFT_PER_SQM = 10.763910416709722
# Coarse (west, south, east, north) boxes that catch corrupted coordinates. They cannot
# separate border regions from Canada or Mexico; the parcel path enforces US scope.
US_BOUNDS: tuple[tuple[float, float, float, float], ...] = (
    (-125.0, 24.3, -66.5, 49.5),  # contiguous states
    (-180.0, 51.0, -129.9, 71.6),  # Alaska
    (172.0, 51.0, 180.0, 53.5),  # western Aleutians
    (-178.5, 18.8, -154.7, 28.5),  # Hawaii
    (-68.0, 17.6, -64.5, 18.6),  # Puerto Rico and US Virgin Islands
    (144.5, 13.0, 146.5, 21.0),  # Guam and Northern Mariana Islands
    (-171.2, -14.7, -168.0, -11.0),  # American Samoa
)
OUTSIDE_US = "Geometry lies outside the United States"


class MapError(ValueError):
    """A diagnostic containing only fixed invariants."""


def load_features(document: object) -> list[dict]:
    if not isinstance(document, dict):
        raise MapError("Expected a Regrid parcel response with parcels.features")
    parcels = document.get("parcels")
    features = parcels.get("features") if isinstance(parcels, dict) else None
    if not isinstance(features, list):
        raise MapError("Expected a Regrid parcel response with parcels.features")
    if not features:
        raise MapError("Response contains no parcels")
    return features


def _finite(value: object) -> float | None:
    if type(value) not in {int, float}:
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _parse_finite(value: object) -> float | None:
    """A finite number from a JSON number or numeric string; anything else is None."""
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    return _finite(value)


def _in_us(lon: float, lat: float) -> bool:
    return any(
        west <= lon <= east and south <= lat <= north for west, south, east, north in US_BOUNDS
    )


def _validate_position(position: object) -> None:
    # RFC 7946 positions may carry altitude after longitude and latitude; it is ignored.
    if not isinstance(position, list) or len(position) < 2:
        raise MapError("Geometry positions must start with longitude and latitude")
    if not all(_finite(value) is not None for value in position):
        raise MapError("Geometry coordinates must be finite numbers")
    if not _in_us(position[0], position[1]):
        raise MapError(OUTSIDE_US)


def _validate_ring(ring: object) -> None:
    if not isinstance(ring, list) or len(ring) < 4:
        raise MapError("Polygon rings need at least four positions")
    for position in ring:
        _validate_position(position)
    if ring[0] != ring[-1]:
        raise MapError("Polygon rings must be closed")


def _validate_polygon(polygon: object) -> None:
    if not isinstance(polygon, list) or not polygon:
        raise MapError("Invalid geometry coordinates")
    for ring in polygon:
        _validate_ring(ring)


def validate_geometry(geometry: object) -> None:
    if not isinstance(geometry, dict):
        raise MapError("Unsupported geometry type")
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "Polygon":
        _validate_polygon(coordinates)
    elif kind == "MultiPolygon":
        if not isinstance(coordinates, list) or not coordinates:
            raise MapError("Invalid geometry coordinates")
        for polygon in coordinates:
            _validate_polygon(polygon)
    else:
        raise MapError("Unsupported geometry type")


def _wrap(delta: float) -> float:
    """Shortest longitude step, so rings crossing 180 degrees are measured correctly."""
    return (delta + 180.0) % 360.0 - 180.0


def _ring_area_m2(ring: list[list[float]]) -> float:
    total = 0.0
    for (lon1, lat1, *_), (lon2, lat2, *_) in zip(ring, ring[1:]):
        total += math.radians(_wrap(lon2 - lon1)) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    return abs(total) * R * R / 2


def _polygon_area_m2(polygon: list[list[list[float]]]) -> float:
    outer, *holes = polygon
    return _ring_area_m2(outer) - sum(_ring_area_m2(hole) for hole in holes)


def geometry_area_sqft(geometry: dict) -> float:
    """Spherical area in square feet; callers must run validate_geometry first."""
    polygons = (
        geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    )
    return sum(_polygon_area_m2(polygon) for polygon in polygons) * SQFT_PER_SQM


def _recorded_sqft(value: Any) -> float | None:
    number = _parse_finite(value)
    return number if number is not None and number > 0 else None


def area_check(feature: dict, tolerance: float = 0.05) -> dict[str, Any]:
    """Compare computed and recorded area; callers must run validate_geometry first."""
    geometry = feature.get("geometry")
    fields = _fields(feature)
    recorded = _recorded_sqft(fields.get("ll_gissqft"))
    computed = None if geometry is None else geometry_area_sqft(geometry)
    if computed is None or recorded is None:
        return {
            "status": "unavailable",
            "computed_sqft": computed,
            "recorded_sqft": recorded,
            "ratio": None,
        }
    ratio = computed / recorded
    status = "ok" if abs(ratio - 1) <= tolerance else "mismatch"
    return {"status": status, "computed_sqft": computed, "recorded_sqft": recorded, "ratio": ratio}


LEAFLET_BASE = "https://unpkg.com/leaflet@1.9.4/dist/"
LEAFLET_CSS_SRI = "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
LEAFLET_JS_SRI = "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
MISSING = "not in record"
NO_BOUNDARY = "No boundary on file for this parcel"
FOOTER = (
    "Imagery date may differ from the parcel record. "
    "Recorded owner is not necessarily the beneficial owner."
)
TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
ATTRIBUTION = (
    "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, "
    "and the GIS User Community"
)
COLORS = ("#ffeb3b", "#ff5722", "#00e5ff", "#76ff03", "#e040fb", "#ff4081")


def select_features(features: list[dict], *, index: int | None, all_candidates: bool) -> list[dict]:
    if index is not None and all_candidates:
        raise MapError("Use --feature or --all-candidates, not both")
    if index is not None:
        if not 0 <= index < len(features):
            raise MapError(f"Feature index must be between 0 and {len(features) - 1}")
        return [features[index]]
    if all_candidates or len(features) == 1:
        return list(features)
    raise MapError("Response has several parcels; choose one with --feature or --all-candidates")


def _fields(feature: dict) -> dict:
    properties = feature.get("properties")
    fields = properties.get("fields") if isinstance(properties, dict) else None
    return fields if isinstance(fields, dict) else {}


def _text(value: object) -> str:
    return MISSING if value is None or value == "" else str(value)


def _fallback_point(feature: dict) -> list[float] | None:
    fields = _fields(feature)
    lat, lon = _parse_finite(fields.get("lat")), _parse_finite(fields.get("lon"))
    if lat is None or lon is None or not _in_us(lon, lat):
        return None
    return [lat, lon]


def _display_geometry(geometry: dict) -> dict:
    """Shift western longitudes east when a geometry spans 180 degrees, so Leaflet draws it
    as one small shape instead of a band around the globe."""
    polygons = (
        geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    )
    lons = [p[0] for polygon in polygons for ring in polygon for p in ring]
    if max(lons) - min(lons) <= 180:
        return geometry

    def shift(position: list[float]) -> list[float]:
        return [position[0] + 360 if position[0] < 0 else position[0], *position[1:]]

    shifted = [[[shift(p) for p in ring] for ring in polygon] for polygon in polygons]
    coordinates = shifted if geometry["type"] == "MultiPolygon" else shifted[0]
    return {**geometry, "coordinates": coordinates}


def _feature_data(feature: dict, label: str | None, retrieved_at: str | None) -> dict[str, Any]:
    properties = feature.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    fields = _fields(feature)
    facts = [
        ["Headline", _text(properties.get("headline"))],
        ["Owner", _text(fields.get("owner"))],
        ["Parcel number", _text(fields.get("parcelnumb"))],
        ["Path", _text(properties.get("path"))],
        ["Last refreshed", _text(fields.get("ll_last_refresh"))],
        ["GIS acres", _text(fields.get("ll_gisacre"))],
        ["Retrieved", _text(retrieved_at)],
    ]
    geometry = feature.get("geometry")
    point = None
    if geometry is None:
        point = _fallback_point(feature)
        if point is None:
            raise MapError(f"{label or 'Parcel'} has no boundary and no usable coordinates")
    return {
        "label": label,
        "title": _text(properties.get("headline")),
        "facts": facts,
        "geometry": None if geometry is None else _display_geometry(geometry),
        "point": point,
        "banner": (f"{label}: {NO_BOUNDARY}" if label else NO_BOUNDARY)
        if geometry is None
        else None,
    }


def _neighbour_data(feature: object) -> dict[str, Any]:
    if not isinstance(feature, dict):
        raise MapError("Neighbour is not a parcel feature")
    properties = feature.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    path = properties.get("path")
    if isinstance(path, str) and not path.startswith("/us/"):
        raise MapError(OUTSIDE_US)
    geometry = feature.get("geometry")
    if geometry is None:
        raise MapError("Neighbour has no boundary")
    validate_geometry(geometry)
    fields = _fields(feature)
    return {
        "title": _text(properties.get("headline")),
        "facts": [
            ["Address", _text(properties.get("headline"))],
            ["Owner", _text(fields.get("owner"))],
            ["Parcel number", _text(fields.get("parcelnumb"))],
        ],
        "geometry": _display_geometry(geometry),
    }


def load_neighbours(path: Path, subject_ids: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Drawable neighbour outlines and a warning for each skipped entry."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, RecursionError) as exc:
        raise MapError("Neighbours file is not valid JSON") from exc
    parcels = document.get("parcels") if isinstance(document, dict) else None
    features = parcels.get("features") if isinstance(parcels, dict) else None
    if not isinstance(features, list):
        raise MapError("Expected a Regrid parcel response with parcels.features")
    drawn: list[dict[str, Any]] = []
    warnings: list[str] = []
    for number, feature in enumerate(features):
        properties = feature.get("properties") if isinstance(feature, dict) else None
        uuid = properties.get("ll_uuid") if isinstance(properties, dict) else None
        if isinstance(uuid, str) and uuid in subject_ids:
            continue
        try:
            drawn.append(_neighbour_data(feature))
        except MapError as exc:
            warnings.append(f"Neighbour {number} skipped: {exc}")
    return drawn, warnings


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Parcel map</title>
<link rel="stylesheet" href="__BASE__leaflet.css" integrity="__CSS_SRI__" crossorigin="">
<style>
html, body { height: 100%; margin: 0; font-family: system-ui, sans-serif; }
body { display: flex; flex-direction: column; }
#map { flex: 1 1 auto; min-height: 0; }
#overlay { position: absolute; top: 8px; left: 56px; right: 8px; z-index: 1000;
  max-width: 28rem; display: flex; flex-direction: column; gap: 6px; }
.banner { background: #fff3cd; color: #5c4400; border: 1px solid #e0b400;
  padding: 6px 10px; border-radius: 4px; font-size: 14px; }
#panel { background: rgba(255, 255, 255, 0.95); padding: 8px 10px; border-radius: 4px;
  font-size: 13px; max-height: 45vh; overflow: auto; }
#panel h2 { font-size: 14px; margin: 6px 0 2px; }
#panel dl { margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 2px 8px; }
#panel dt { font-weight: 600; }
#panel dd { margin: 0; overflow-wrap: anywhere; }
footer { flex: none; background: #222; color: #fff; font-size: 12px; padding: 4px 8px; }
</style>
</head>
<body>
<div id="map"></div>
<div id="overlay">
__WARNINGS__<div id="banners"></div>
<div id="panel"></div>
</div>
<footer>__FOOTER__</footer>
<script src="__BASE__leaflet.js" integrity="__JS_SRI__" crossorigin=""></script>
<script type="application/json" id="neighbour-data">__NEIGHBOURS__</script>
<script type="application/json" id="parcel-data">__DATA__</script>
<script>
(function () {
  var items = JSON.parse(document.getElementById("parcel-data").textContent);
  var colors = __COLORS__;
  var map = L.map("map");
  L.tileLayer("__TILES__", {
    maxZoom: 19,
    attribution: "__ATTRIBUTION__"
  }).addTo(map);
  var neighbours = JSON.parse(document.getElementById("neighbour-data").textContent);
  neighbours.forEach(function (item) {
    var layer = L.geoJSON(item.geometry, {
      style: { color: "#ffffff", weight: 1, fillOpacity: 0.05 }
    });
    var popup = document.createElement("div");
    popup.appendChild(el("strong", item.title));
    popup.appendChild(factList(item));
    layer.bindPopup(popup);
    layer.addTo(map);
  });
  var group = L.featureGroup().addTo(map);
  var panel = document.getElementById("panel");
  var banners = document.getElementById("banners");

  function el(tag, text) {
    var node = document.createElement(tag);
    node.textContent = text;
    return node;
  }

  function factList(item) {
    var dl = document.createElement("dl");
    item.facts.forEach(function (fact) {
      dl.appendChild(el("dt", fact[0]));
      dl.appendChild(el("dd", fact[1]));
    });
    return dl;
  }

  items.forEach(function (item, i) {
    var color = item.label ? colors[i % colors.length] : colors[0];
    var heading = item.label ? item.label + ": " + item.title : item.title;
    var layer = null;
    if (item.geometry) {
      layer = L.geoJSON(item.geometry, {
        style: { color: color, weight: 3, fillOpacity: 0.15 }
      });
    } else if (item.point) {
      layer = L.marker(item.point);
    }
    if (layer) {
      var popup = document.createElement("div");
      popup.appendChild(el("strong", heading));
      popup.appendChild(factList(item));
      layer.bindPopup(popup);
      layer.addTo(group);
    }
    if (item.banner) {
      banners.appendChild(el("div", item.banner)).className = "banner";
    }
    panel.appendChild(el("h2", heading));
    panel.appendChild(factList(item));
  });

  map.fitBounds(group.getBounds().pad(0.1), { maxZoom: 18 });
})();
</script>
</body>
</html>
"""


def _json_for_script(value: object) -> str:
    """JSON safe to embed in a script element: <, > and & never appear literally."""
    return (
        json.dumps(value, ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def render_html(
    features: list[dict],
    *,
    candidates: bool,
    retrieved_at: str | None,
    warnings: Sequence[str] = (),
    neighbours: Sequence[dict[str, Any]] = (),
) -> str:
    items = [
        _feature_data(feature, f"Candidate {number}" if candidates else None, retrieved_at)
        for number, feature in enumerate(features, 1)
    ]
    data = _json_for_script(items)
    neighbour_data = _json_for_script(list(neighbours))
    banners = "".join(
        f'<div class="banner" role="alert">{html.escape(text)}</div>\n' for text in warnings
    )
    replacements = {
        "__BASE__": LEAFLET_BASE,
        "__CSS_SRI__": LEAFLET_CSS_SRI,
        "__JS_SRI__": LEAFLET_JS_SRI,
        "__WARNINGS__": banners,
        "__FOOTER__": html.escape(FOOTER),
        "__COLORS__": json.dumps(list(COLORS)),
        "__TILES__": TILE_URL,
        "__ATTRIBUTION__": ATTRIBUTION,
        "__NEIGHBOURS__": neighbour_data,
        "__DATA__": data,
    }
    page = _PAGE
    for marker, value in replacements.items():
        page = page.replace(marker, value)
    return page


EXISTS = "Output file exists; pass --replace to overwrite it"


def _temp_file(directory: Path) -> tuple[int, Path]:
    # os.open applies the caller's umask to 0o666, matching a normally created file, without
    # changing the process-wide umask.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    while True:
        name = directory / f".map-{secrets.token_hex(8)}.tmp"
        try:
            return os.open(name, flags, 0o666), name
        except FileExistsError:
            continue


def _write_atomic(path: Path, content: str, *, replace: bool) -> None:
    _write_atomic_bytes(path, content.encode("utf-8"), replace=replace)


def _write_atomic_bytes(path: Path, data: bytes, *, replace: bool) -> None:
    if not replace and os.path.lexists(path):
        raise MapError(EXISTS)
    fd, temp = _temp_file(path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        if replace:
            os.replace(temp, path)
            return
        try:
            os.link(temp, path)  # atomic and never overwrites
        except FileExistsError:
            raise MapError(EXISTS) from None
        except OSError:  # hard links unsupported: exclusive create still never overwrites
            try:
                with open(path, "xb") as handle:
                    handle.write(data)
            except FileExistsError:
                raise MapError(EXISTS) from None
    finally:
        temp.unlink(missing_ok=True)


def render(
    response_path: Path,
    output_path: Path,
    *,
    index: int | None = None,
    all_candidates: bool = False,
    retrieved_at: str | None = None,
    replace: bool = False,
    neighbours_path: Path | None = None,
) -> dict[str, Any]:
    try:
        document = json.loads(Path(response_path).read_text(encoding="utf-8"))
    except (ValueError, RecursionError) as exc:
        raise MapError("Response file is not valid JSON") from exc
    features = load_features(document)
    if not all(isinstance(feature, dict) for feature in features):
        raise MapError("Expected a Regrid parcel response with parcels.features")
    chosen = select_features(features, index=index, all_candidates=all_candidates)
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    for number, feature in enumerate(chosen, 1):
        name = f"Candidate {number}" if all_candidates else "Parcel"
        properties = feature.get("properties")
        path = properties.get("path") if isinstance(properties, dict) else None
        if isinstance(path, str) and not path.startswith("/us/"):
            raise MapError(f"{name}: {OUTSIDE_US}")
        if "geometry" not in feature:
            raise MapError(f"{name}: response omits geometry; it was requested without boundaries")
        geometry = feature["geometry"]
        if geometry is not None:
            validate_geometry(geometry)
        check = area_check(feature)
        checks.append(check)
        if check["status"] == "mismatch":
            warnings.append(
                f"{name}: area mismatch: boundary area differs from the recorded parcel area "
                f"({check['computed_sqft']:,.0f} vs {check['recorded_sqft']:,.0f} sq ft)"
            )
    neighbours: list[dict[str, Any]] = []
    if neighbours_path is not None:
        subject_ids = set()
        for feature in chosen:
            props = feature.get("properties")
            uuid = props.get("ll_uuid") if isinstance(props, dict) else None
            if isinstance(uuid, str):
                subject_ids.add(uuid)
        try:
            neighbours, skipped = load_neighbours(neighbours_path, subject_ids)
            warnings.extend(skipped)
        except MapError as exc:
            warnings.append(f"Neighbours skipped: {' '.join(str(exc).split())}")
        except OSError as exc:
            reason = " ".join(str(exc.strerror or "unreadable").split())
            warnings.append(f"Neighbours skipped: Neighbours file could not be read ({reason})")
    # Raises before anything is written when a parcel has neither a boundary nor a point.
    page = render_html(
        chosen,
        candidates=all_candidates,
        retrieved_at=retrieved_at,
        warnings=warnings,
        neighbours=neighbours,
    )
    output = Path(output_path)
    _write_atomic(output, page, replace=replace)
    return {
        "output": str(output),
        "features": len(chosen),
        "neighbours": len(neighbours),
        "area_checks": checks,
        "warnings": warnings,
    }


CORE_COLUMNS = (
    "headline",
    "path",
    "ll_uuid",
    "owner",
    "parcelnumb",
    "ll_last_refresh",
    "ll_gisacre",
    "ll_gissqft",
    "lat",
    "lon",
)
_PROPERTY_COLUMNS = frozenset({"headline", "path", "ll_uuid"})
NO_OUTPUT = "Choose --csv and/or --geojson"


_PLAIN_NUMBER = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")


def _csv_cell(value: object) -> str:
    """A CSV cell: missing is empty, and spreadsheet formula prefixes are neutralised."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    if text[:1] not in {"=", "+", "-", "@", "\t", "\r"}:
        return text
    if _PLAIN_NUMBER.fullmatch(text) and math.isfinite(float(text)):
        return text
    return "'" + text


def _core_value(feature: dict, name: str) -> Any:
    properties = feature.get("properties")
    source = properties if name in _PROPERTY_COLUMNS and isinstance(properties, dict) else None
    return (source if source is not None else _fields(feature)).get(name)


def export(
    response_path: Path,
    *,
    csv_path: Path | None = None,
    geojson_path: Path | None = None,
    all_fields: bool = False,
    replace: bool = False,
) -> dict[str, Any]:
    """Write a saved parcel response as CSV and/or GeoJSON; makes no requests."""
    if csv_path is None and geojson_path is None:
        raise MapError(NO_OUTPUT)
    targets = [Path(p) for p in (csv_path, geojson_path) if p is not None]
    if len(targets) == 2 and (
        targets[0] == targets[1]
        or os.path.abspath(targets[0]) == os.path.abspath(targets[1])
        or targets[0].resolve() == targets[1].resolve()
    ):
        raise MapError("CSV and GeoJSON outputs must be different files")
    for target in targets:
        if not target.parent.is_dir():
            raise MapError("Output directory does not exist")
    try:
        document = json.loads(Path(response_path).read_text(encoding="utf-8"))
    except (ValueError, RecursionError) as exc:
        raise MapError("Response file is not valid JSON") from exc
    features = load_features(document)
    for number, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise MapError("Expected a Regrid parcel response with parcels.features")
        name = f"Feature {number}"
        properties = feature.get("properties")
        path = properties.get("path") if isinstance(properties, dict) else None
        if isinstance(path, str) and not path.startswith("/us/"):
            raise MapError(f"{name}: {OUTSIDE_US}")
        if geojson_path is not None and "geometry" not in feature:
            raise MapError(f"{name}: response omits geometry; it was requested without boundaries")
        if feature.get("geometry") is not None:
            validate_geometry(feature["geometry"])
    if not replace:
        for target in targets:
            if os.path.lexists(target):
                raise MapError(EXISTS)
    columns = list(CORE_COLUMNS)
    if all_fields:
        extras = {key for feature in features for key in _fields(feature)}
        columns += sorted(extras - set(CORE_COLUMNS))
    csv_data = geojson_data = None
    if csv_path is not None:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(_csv_cell(name) for name in columns)
        for feature in features:
            writer.writerow(
                _csv_cell(
                    _core_value(feature, name)
                    if name in CORE_COLUMNS
                    else _fields(feature).get(name)
                )
                for name in columns
            )
        csv_data = buffer.getvalue().encode("utf-8-sig")
    if geojson_path is not None:
        collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": feature["geometry"],
                    "properties": {name: _core_value(feature, name) for name in CORE_COLUMNS},
                }
                for feature in features
            ],
        }
        geojson_data = (json.dumps(collection, ensure_ascii=False, allow_nan=False) + "\n").encode(
            "utf-8"
        )
    if csv_path is not None and csv_data is not None:
        _write_atomic_bytes(Path(csv_path), csv_data, replace=replace)
    if geojson_path is not None and geojson_data is not None:
        _write_atomic_bytes(Path(geojson_path), geojson_data, replace=replace)
    return {
        "features": len(features),
        "csv": None if csv_path is None else str(csv_path),
        "geojson": None if geojson_path is None else str(geojson_path),
        "columns": columns,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    cmd = commands.add_parser("render", help="render a saved parcel response as a satellite map")
    cmd.add_argument("response", type=Path)
    cmd.add_argument("output", type=Path)
    cmd.add_argument("--feature", type=int, metavar="N", help="zero-based feature index")
    cmd.add_argument("--all-candidates", action="store_true")
    cmd.add_argument("--retrieved-at", metavar="ISO")
    cmd.add_argument("--replace", action="store_true")
    cmd.add_argument("--neighbours", type=Path, metavar="FILE", help="neighbouring parcels")
    exp = commands.add_parser("export", help="export a saved parcel response to CSV and/or GeoJSON")
    exp.add_argument("response", type=Path)
    exp.add_argument("--csv", type=Path, metavar="FILE")
    exp.add_argument("--geojson", type=Path, metavar="FILE")
    exp.add_argument("--all-fields", action="store_true")
    exp.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            summary = export(
                args.response,
                csv_path=args.csv,
                geojson_path=args.geojson,
                all_fields=args.all_fields,
                replace=args.replace,
            )
        else:
            summary = render(
                args.response,
                args.output,
                index=args.feature,
                all_candidates=args.all_candidates,
                retrieved_at=args.retrieved_at,
                replace=args.replace,
                neighbours_path=args.neighbours,
            )
    except (MapError, OSError, ValueError) as exc:
        message = " ".join(str(exc).split())
        print(f"error: {message}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
