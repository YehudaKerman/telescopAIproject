#!/usr/bin/env python3
"""
find_landmarks.py — TelescopeAI Landmark Finder

Shows Az / Alt / distance for every landmark in config.yaml and scores
each one for calibration quality.  Use --add to interactively append a
new landmark (paste coordinates from Google Maps).

Usage:
    python find_landmarks.py
    python find_landmarks.py --add
"""
import argparse
from datetime import datetime
from pathlib import Path

import yaml

from utils.geometry import landmark_az_alt

CONFIG_PATH = Path("config.yaml")


def compute(obs: dict, lm: dict) -> tuple[float, float, float]:
    """Return (azimuth_deg, altitude_deg_apparent, distance_m) for a landmark."""
    return landmark_az_alt(obs, lm)


# ── calibration quality scoring ───────────────────────────────────────────────

def quality(existing_az: list[float], new_az: float,
            dist_m: float, alt_deg: float) -> tuple[int, str]:
    """
    Score a landmark for calibration suitability (0-100).
    Returns (score, reason_string).
    """
    notes = []
    score = 0

    # Distance: 500m–15km is ideal for alt-axis accuracy
    if 500 <= dist_m <= 15_000:
        score += 30
        notes.append("dist OK")
    elif dist_m > 15_000:
        score += 15
        notes.append("far")
    else:
        notes.append("too close")

    # Altitude angle: 2°–35° avoids refraction errors and zenith gimbal issues
    if 2 <= alt_deg <= 35:
        score += 30
        notes.append("alt OK")
    elif 0 <= alt_deg < 2:
        score += 10
        notes.append("low alt")
    elif alt_deg > 35:
        score += 15
        notes.append("high alt")
    else:
        notes.append("below horizon")

    # Angular separation from already-selected points
    if not existing_az:
        score += 40
        notes.append("first point")
    else:
        seps = [min(abs(new_az - a) % 360, 360 - abs(new_az - a) % 360)
                for a in existing_az]
        min_sep = min(seps)
        if min_sep >= 90:
            score += 40
            notes.append(f"sep {min_sep:.0f}°✓")
        elif min_sep >= 45:
            score += 20
            notes.append(f"sep {min_sep:.0f}°")
        else:
            score += 0
            notes.append(f"sep {min_sep:.0f}°✗")

    return score, ", ".join(notes)


def az_direction(az: float) -> str:
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
            "S","SSW","SW","WSW","W","WNW","NW","NNW"]
    return dirs[round(az / 22.5) % 16]


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="TelescopeAI Landmark Finder")
    parser.add_argument("--add", action="store_true",
                        help="Interactively add a new landmark to config.yaml")
    args = parser.parse_args()

    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    obs = cfg["location"]
    landmarks: list[dict] = cfg.get("landmarks", [])

    # ── print table ──────────────────────────────────────────────────────────
    print(f"\nObserver: {obs['latitude']:.5f}°N  {obs['longitude']:.5f}°E  "
          f"{obs['altitude_m']}m  |  {datetime.now().strftime('%H:%M')}")
    print()

    header = (f"{'#':>2}  {'Name':30s}  {'Dir':>4}  {'Az':>7}  "
              f"{'Alt':>7}  {'Dist':>8}  {'Score':>5}  Notes")
    print(header)
    print("-" * len(header))

    rows: list[tuple] = []
    for lm in landmarks:
        az, alt, dist = compute(obs, lm)
        rows.append((lm, az, alt, dist))

    # Score each landmark cumulatively (best selection order)
    selected_az: list[float] = []
    scores: list[tuple[int, str]] = []
    for _, az, alt, dist in rows:
        s, note = quality(selected_az, az, dist, alt)
        scores.append((s, note))

    for i, ((lm, az, alt, dist), (s, note)) in enumerate(zip(rows, scores)):
        stars = "★" * (s // 20) + "☆" * (5 - s // 20)
        print(f"{i+1:>2}. {lm['name']:30s}  {az_direction(az):>4}  "
              f"{az:7.2f}°  {alt:+7.2f}°  {dist/1000:6.2f}km  "
              f"{s:>5}  {stars}  {note}")

    print()
    print("Scoring: distance (30) + altitude angle (30) + Az separation (40)")
    print("Ideal calibration pair: two landmarks with Az separation > 90°")

    # Suggest best pair
    if len(rows) >= 2:
        best_pair = None
        best_sep  = 0
        for i in range(len(rows)):
            for j in range(i+1, len(rows)):
                sep = abs(rows[i][1] - rows[j][1]) % 360
                sep = min(sep, 360 - sep)
                if sep > best_sep:
                    best_sep  = sep
                    best_pair = (i, j)
        if best_pair:
            a, b = best_pair
            print(f"\nRecommended pair: #{a+1} '{landmarks[a]['name']}' + "
                  f"#{b+1} '{landmarks[b]['name']}' "
                  f"(Az separation {best_sep:.0f}°)")

    # ── add mode ─────────────────────────────────────────────────────────────
    if args.add:
        print("\n--- Add New Landmark ---")
        print("Tip: Google Maps → right-click on target → first line shows 'lat, lon'")
        name  = input("Name: ").strip()
        lat   = float(input("Latitude  (decimal degrees, e.g. 32.1234): "))
        lon   = float(input("Longitude (decimal degrees, e.g. 35.2345): "))
        alt_m = float(input("Altitude  (metres above sea level): "))
        notes = input("Notes (optional): ").strip()

        entry: dict = {"name": name, "lat": lat, "lon": lon, "alt_m": alt_m}
        if notes:
            entry["notes"] = notes

        # Preview before saving
        az, alt, dist = compute(obs, entry)
        print(f"\n  Az={az:.2f}°  Alt={alt:+.2f}°  Dist={dist/1000:.2f}km")
        ok = input("Save? (y/n): ").strip().lower()
        if ok == "y":
            landmarks.append(entry)
            cfg["landmarks"] = landmarks
            CONFIG_PATH.write_text(
                yaml.dump(cfg, allow_unicode=True, sort_keys=False),
                encoding="utf-8"
            )
            print(f"[OK] '{name}' saved to config.yaml")
        else:
            print("Cancelled.")


if __name__ == "__main__":
    main()
