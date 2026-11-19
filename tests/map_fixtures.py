"""Shared parcel-response builders for map tests."""

import json
import math


def square(lon=-75.03, lat=39.9, size=0.001):
    ring = [[lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat + size], [lon, lat]]
    return {"type": "Polygon", "coordinates": [ring]}


def expected_sqft(lon=-75.03, lat=39.9, size=0.001):
    r = 6378137.0
    m2 = (
        r
        * r
        * math.radians(size)
        * (math.sin(math.radians(lat + size)) - math.sin(math.radians(lat)))
    )
    return m2 * 10.763910416709722


def feature(geometry, **fields):
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "headline": "12 Example Ave",
            "path": "/us/nj/camden/haddonfield/1",
            "ll_uuid": "00000000-0000-4000-8000-000000000001",
            "fields": fields,
        },
    }


def write_response(path, *features):
    path.write_text(json.dumps({"parcels": {"features": list(features)}}), encoding="utf-8")
    return path


def good_feature(**fields):
    fields.setdefault("ll_gissqft", expected_sqft())
    return feature(square(), **fields)
