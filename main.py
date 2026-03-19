"""
main.py — TelescopeAI entry point

Interactive CLI for controlling the telescope.
Reads config.yaml for mount/camera backend, location, and logging settings.

Commands:
    track       — start camera tracker (locks onto moving target)
    gps         — slew to a GPS coordinate (lat/lon/alt)
    north       — slew to North at minimum safe altitude
    moon        — slew to Moon (sets Lunar tracking rate)
    mars / jupiter / saturn / venus — slew to solar system body
    exit        — disconnect and quit

Run:
    python main.py
"""
from skyfield.api import load, Topos

from utils.config import load_config
from utils.logger import setup_logging, get_logger
from core.session import TelescopeSession

# ── Boot ──────────────────────────────────────────────────────────────────────

cfg = load_config()
setup_logging(cfg)
logger = get_logger(__name__)

MY_LAT = cfg['location']['latitude']
MY_LON = cfg['location']['longitude']
MY_ALT = cfg['location']['altitude_m']


# ── Skyfield helpers ──────────────────────────────────────────────────────────

def _load_skyfield():
    planets  = load('de421.bsp')
    earth    = planets['earth']
    ts       = load.timescale()
    observer = earth + Topos(
        latitude_degrees=MY_LAT,
        longitude_degrees=MY_LON,
        elevation_m=MY_ALT,
    )
    return planets, observer, ts


# ── Main control loop ─────────────────────────────────────────────────────────

def run_telescope_control() -> None:
    logger.info("TelescopeAI starting")
    print("Loading Skyfield ephemeris...")
    planets, observer, ts = _load_skyfield()

    with TelescopeSession(cfg) as session:
        while True:
            print("\n==============================")
            print("--- TELESCOPE CONTROL MENU ---")
            print("Commands: track  gps  north  moon  mars  jupiter  saturn  venus  exit")
            user_input = input("Command: ").strip().lower()

            if user_input == "exit":
                logger.info("User requested exit")
                break

            # ── Camera tracker ────────────────────────────────────────────────
            if user_input == "track":
                print("\n>>> Starting Camera Tracker...")
                session.start_tracking()
                continue

            # ── GPS coordinate slew ───────────────────────────────────────────
            if user_input == "gps":
                try:
                    lat   = float(input("Target Latitude:   "))
                    lon   = float(input("Target Longitude:  "))
                    alt_m = float(input("Target Altitude (m): "))

                    target = planets['earth'] + Topos(
                        latitude_degrees=lat,
                        longitude_degrees=lon,
                        elevation_m=alt_m,
                    )
                    t = ts.now()
                    alt_obj, az_obj, dist = observer.at(t).observe(target).apparent().altaz()
                    print(f"Calculated: Az={az_obj.degrees:.2f}°  Alt={alt_obj.degrees:.2f}°  "
                          f"Dist={dist.km:.1f} km")

                    if alt_obj.degrees < 0:
                        print("ERROR: Target is below the horizon.")
                        continue

                    if input("Slew? (y/n): ").strip().lower() == "y":
                        session.slew_to("GPS Target", az_obj.degrees, alt_obj.degrees)

                except ValueError as exc:
                    print(f"Invalid input: {exc}")
                except Exception as exc:
                    logger.error("GPS slew error: %s", exc)
                    print(f"Error: {exc}")
                continue

            # ── North ─────────────────────────────────────────────────────────
            if user_input == "north":
                session.slew_to("North", az=0.0, alt=10.0)
                continue

            # ── Solar system bodies ───────────────────────────────────────────
            BODY_KEYS = {
                "moon":    ("moon",              1),   # (skyfield key, tracking rate)
                "mars":    ("mars barycenter",   0),
                "jupiter": ("jupiter barycenter", 0),
                "saturn":  ("saturn barycenter", 0),
                "venus":   ("venus",              0),
            }
            if user_input in BODY_KEYS:
                body_key, track_rate = BODY_KEYS[user_input]
                try:
                    t = ts.now()
                    alt_obj, az_obj, _ = (
                        observer.at(t).observe(planets[body_key]).apparent().altaz()
                    )
                    print(f"  {user_input.upper()}  Az={az_obj.degrees:.2f}°  "
                          f"Alt={alt_obj.degrees:.2f}°")

                    if alt_obj.degrees <= 0:
                        print("Target is below the horizon.")
                        continue

                    session.scope.tracking_rate = track_rate

                    if input("Slew? (y/n): ").strip().lower() == "y":
                        session.slew_to(user_input.upper(), az_obj.degrees, alt_obj.degrees)

                except Exception as exc:
                    logger.error("Body slew error (%s): %s", user_input, exc)
                    print(f"Error: {exc}")
                continue

            print(f"Unknown command: '{user_input}'")


if __name__ == "__main__":
    run_telescope_control()
