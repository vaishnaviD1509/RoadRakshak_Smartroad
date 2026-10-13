"""Spot complaints that may be reports of the same damage."""
from math import asin, cos, radians, sin, sqrt

from models.complaint import Complaint

DUPLICATE_RADIUS_METERS = 50
CLOSED_STATUSES = ("Resolved", "Rejected")
EARTH_RADIUS_M = 6_371_000
METERS_PER_DEGREE_LAT = 111_320


def distance_meters(lat1, lng1, lat2, lng2) -> float:
    """Great-circle distance between two points in metres (haversine)."""
    p1, p2 = radians(lat1), radians(lat2)
    d_lat = p2 - p1
    d_lng = radians(lng2 - lng1)
    a = sin(d_lat / 2) ** 2 + cos(p1) * cos(p2) * sin(d_lng / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def find_possible_duplicates(complaint, radius_m: int = DUPLICATE_RADIUS_METERS, limit: int = 10) -> list:
    """Open complaints within `radius_m` metres of this one, nearest first.

    Each result is {"complaint", "distance", "same_category"}. A complaint with
    no map pin has nothing to compare, so it returns an empty list. Resolved and
    rejected complaints are skipped: a repaired road that is damaged again is a
    new problem, and a rejected report is already dealt with.
    """
    if complaint.latitude is None or complaint.longitude is None:
        return []

    # Cheap box filter in the database first, exact distance in Python after.
    lat_delta = radius_m / METERS_PER_DEGREE_LAT
    lng_delta = radius_m / (METERS_PER_DEGREE_LAT * max(cos(radians(complaint.latitude)), 0.01))

    candidates = (
        Complaint.query
        .filter(
            Complaint.id != complaint.id,
            Complaint.status.notin_(CLOSED_STATUSES),
            Complaint.latitude.isnot(None),
            Complaint.longitude.isnot(None),
            Complaint.latitude.between(complaint.latitude - lat_delta, complaint.latitude + lat_delta),
            Complaint.longitude.between(complaint.longitude - lng_delta, complaint.longitude + lng_delta),
        )
        .all()
    )

    matches = []
    for other in candidates:
        d = distance_meters(complaint.latitude, complaint.longitude, other.latitude, other.longitude)
        if d <= radius_m:
            matches.append({
                "complaint": other,
                "distance": round(d),
                "same_category": other.damage_category == complaint.damage_category,
            })

    matches.sort(key=lambda m: (not m["same_category"], m["distance"]))
    return matches[:limit]