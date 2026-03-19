"""
utils/geometry.py — TelescopeAI Shared Geometry Functions

All telescope geometry calculations in one place.  Used by calibration.py,
find_landmarks.py, and any future module that needs coordinate math.

Functions:
    haversine()       — great-circle distance between two GPS points
    true_bearing()    — compass bearing from observer to target
    elevation_angle() — geometric look-up angle to a target
    apply_refraction()— atmospheric refraction correction (Bennett's formula)
    landmark_az_alt() — convenience wrapper: GPS → (Az, Alt, distance)

All angles are in degrees.  All distances are in metres.
"""
import math


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance between two WGS-84 points.

    Args:
        lat1, lon1: Observer position in decimal degrees
        lat2, lon2: Target position in decimal degrees

    Returns:
        Distance in metres
    """
    R = 6_371_000  # Earth mean radius (metres)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def true_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    True (geographic) bearing from observer to target.

    Args:
        lat1, lon1: Observer position in decimal degrees
        lat2, lon2: Target position in decimal degrees

    Returns:
        Bearing in degrees, 0 = North, 90 = East, clockwise
    """
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2r)
    y = (math.cos(lat1r) * math.sin(lat2r)
         - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon))
    return math.degrees(math.atan2(x, y)) % 360


def elevation_angle(dist_m: float, h_diff_m: float) -> float:
    """
    Geometric elevation angle from observer to target (ignores atmosphere).

    Args:
        dist_m:   Horizontal great-circle distance in metres
        h_diff_m: Altitude difference (target_alt - observer_alt) in metres

    Returns:
        Elevation angle in degrees.  Positive = target is above observer.
    """
    return math.degrees(math.atan2(h_diff_m, dist_m))


def apply_refraction(alt_deg: float) -> float:
    """
    Atmospheric refraction correction using Bennett's formula.

    Adds a small upward shift to the apparent altitude (the atmosphere bends
    light toward the horizon, making objects appear higher than they are).
    Effect is largest near the horizon (~34 arcmin at 0°, ~0 at 90°).

    Args:
        alt_deg: Geometric (true) altitude in degrees

    Returns:
        Apparent altitude in degrees.  Unmodified if alt_deg < -0.5°.
    """
    if alt_deg < -0.5:
        return alt_deg
    r = 1.02 / math.tan(math.radians(alt_deg + 10.3 / (alt_deg + 5.11)))
    return alt_deg + r / 60.0


def landmark_az_alt(
    observer: dict,
    landmark: dict,
) -> tuple[float, float, float]:
    """
    Calculate apparent Az/Alt and distance from observer to a landmark.

    Combines haversine + true_bearing + elevation_angle + apply_refraction
    into a single convenience call.

    Args:
        observer: dict with keys 'latitude', 'longitude', 'altitude_m'
                  (matches the config.yaml 'location' section)
        landmark: dict with keys 'lat', 'lon', 'alt_m'
                  (matches a config.yaml 'landmarks' entry)

    Returns:
        (azimuth_deg, apparent_altitude_deg, distance_m)
        azimuth_deg          — 0=North, 90=East, clockwise
        apparent_altitude_deg— includes atmospheric refraction
        distance_m           — great-circle distance in metres
    """
    dist = haversine(
        observer["latitude"], observer["longitude"],
        landmark["lat"],      landmark["lon"],
    )
    az   = true_bearing(
        observer["latitude"], observer["longitude"],
        landmark["lat"],      landmark["lon"],
    )
    h_diff = landmark["alt_m"] - observer["altitude_m"]
    alt    = apply_refraction(elevation_angle(dist, h_diff))
    return az, alt, dist
