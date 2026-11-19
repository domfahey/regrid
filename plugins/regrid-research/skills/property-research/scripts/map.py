"""Offline parcel map renderer: validates a saved Regrid response and writes an HTML page.

Uses only the standard library, makes no network requests, and never reads credentials.
The generated page loads Leaflet and Esri imagery in the viewer's browser.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

R = 6378137.0
SQFT_PER_SQM = 10.763910416709722
US_BOUNDS: tuple[tuple[float, float, float, float], ...] = (
    (-180.0, 17.5, -64.0, 72.0),
    (172.0, 51.0, 180.0, 53.5),
    (144.5, 13.0, 146.5, 21.0),
    (-171.2, -14.7, -168.0, -11.0),
)


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
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _validate_position(position: object) -> None:
    if not isinstance(position, list) or len(position) != 2:
        raise MapError("Geometry positions must be [longitude, latitude] pairs")
    if not all(_finite(value) is not None for value in position):
        raise MapError("Geometry coordinates must be finite numbers")
    lon, lat = position
    if not any(
        west <= lon <= east and south <= lat <= north for west, south, east, north in US_BOUNDS
    ):
        raise MapError("Geometry lies outside the United States")


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


def _ring_area_m2(ring: list[list[float]]) -> float:
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(ring, ring[1:]):
        total += math.radians(lon2 - lon1) * (
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
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    number = _finite(value)
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
FACT_FIELDS = (
    ("Owner", "owner"),
    ("Parcel number", "parcelnumb"),
    ("Last refreshed", "ll_last_refresh"),
    ("GIS acres", "ll_gisacre"),
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
    point: list[float] = []
    for key in ("lat", "lon"):
        value = fields.get(key)
        try:
            number = _finite(float(value.strip()) if isinstance(value, str) else value)
        except ValueError:
            number = None
        if number is None:
            return None
        point.append(number)
    lat, lon = point
    inside = any(
        west <= lon <= east and south <= lat <= north for west, south, east, north in US_BOUNDS
    )
    return point if inside else None


def _feature_data(feature: dict, label: str | None, retrieved_at: str | None) -> dict[str, Any]:
    properties = feature.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    fields = _fields(feature)
    facts = [["Headline", _text(properties.get("headline"))]]
    facts += [[name, _text(fields.get(key))] for name, key in FACT_FIELDS[:2]]
    facts.append(["Path", _text(properties.get("path"))])
    facts += [[name, _text(fields.get(key))] for name, key in FACT_FIELDS[2:]]
    facts.append(["Retrieved", _text(retrieved_at)])
    geometry = feature.get("geometry")
    return {
        "label": label,
        "title": _text(properties.get("headline")),
        "facts": facts,
        "geometry": geometry,
        "point": None if geometry is not None else _fallback_point(feature),
        "banner": (f"{label}: {NO_BOUNDARY}" if label else NO_BOUNDARY)
        if geometry is None
        else None,
    }


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


def render_html(
    features: list[dict],
    *,
    candidates: bool,
    retrieved_at: str | None,
    warnings: Sequence[str] = (),
) -> str:
    items = [
        _feature_data(feature, f"Candidate {number}" if candidates else None, retrieved_at)
        for number, feature in enumerate(features, 1)
    ]
    data = (
        json.dumps(items, ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
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
        "__DATA__": data,
    }
    page = _PAGE
    for marker, value in replacements.items():
        page = page.replace(marker, value)
    return page


def _write_atomic(path: Path, content: str, *, replace: bool) -> None:
    if not replace and os.path.lexists(path):
        raise MapError("Output file exists; pass --replace to overwrite it")
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=".map-", suffix=".tmp", delete=False
    )
    try:
        with handle:
            handle.write(content)
            umask = os.umask(0)
            os.umask(umask)
        os.chmod(handle.name, 0o666 & ~umask)
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def render(
    response_path: Path,
    output_path: Path,
    *,
    index: int | None = None,
    all_candidates: bool = False,
    retrieved_at: str | None = None,
    replace: bool = False,
) -> dict[str, Any]:
    try:
        document = json.loads(Path(response_path).read_text(encoding="utf-8"))
    except (ValueError, RecursionError) as exc:
        raise MapError("Response file is not valid JSON") from exc
    features = load_features(document)
    if not all(isinstance(feature, dict) for feature in features):
        raise MapError("Expected a Regrid parcel response with parcels.features")
    chosen = select_features(features, index=index, all_candidates=all_candidates)
    candidates = all_candidates
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    for number, feature in enumerate(chosen, 1):
        name = f"Candidate {number}" if candidates else "Parcel"
        geometry = feature.get("geometry")
        if geometry is None:
            if _fallback_point(feature) is None:
                raise MapError(f"{name} has no boundary and no usable coordinates")
        else:
            validate_geometry(geometry)
        check = area_check(feature)
        checks.append(check)
        if check["status"] == "mismatch":
            warnings.append(
                f"{name}: boundary area differs from the recorded parcel area "
                f"({check['computed_sqft']:,.0f} vs {check['recorded_sqft']:,.0f} sq ft)"
            )
    page = render_html(chosen, candidates=candidates, retrieved_at=retrieved_at, warnings=warnings)
    output = Path(output_path)
    _write_atomic(output, page, replace=replace)
    return {
        "output": str(output),
        "features": len(chosen),
        "area_checks": checks,
        "warnings": warnings,
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
    args = parser.parse_args(argv)
    try:
        summary = render(
            args.response,
            args.output,
            index=args.feature,
            all_candidates=args.all_candidates,
            retrieved_at=args.retrieved_at,
            replace=args.replace,
        )
    except (MapError, OSError) as exc:
        message = " ".join(str(exc).split())
        print(f"error: {message}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
