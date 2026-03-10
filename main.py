import win32com.client
from skyfield.api import load, Topos
import time
import threading
import tracker  # וודא שהקובץ tracker.py באותה תיקייה

# --- הגדרות מיקום ---
MY_LAT = 32.1065
MY_LON = 35.2070
MY_ALT = 713

# --- הגדרות בטיחות ---
MIN_SAFE_ALTITUDE = 10.0


def safe_move(scope, az, alt, target_name="Target"):
    """
    פונקציה שמבצעת תנועה (Slew) ומאפשרת למשתמש לכתוב stop כדי לעצור באמצע.
    """
    # בדיקת בטיחות: לא לכוון מתחת לגובה מינימלי
    if alt < MIN_SAFE_ALTITUDE:
        print(f"ERROR: Alt={alt:.1f}° is below MIN_SAFE_ALTITUDE ({MIN_SAFE_ALTITUDE}°). Slew aborted.")
        return

    try:
        print(f"\n>>> Moving to {target_name} (Az: {az:.2f}, Alt: {alt:.2f})...")

        if scope.AtPark:
            scope.Unpark()

        if not scope.Tracking:
            scope.Tracking = True

        scope.SlewToAltAzAsync(float(az), float(alt))
        time.sleep(1.0)

        stop_flag = []

        def wait_for_stop():
            print("   [Type 'stop' + Enter to ABORT, or wait for arrival]")
            user_text = input()
            if user_text.strip().lower() == 'stop':
                stop_flag.append(True)

        t = threading.Thread(target=wait_for_stop)
        t.daemon = True
        t.start()

        aborted = False
        while scope.Slewing:
            if stop_flag:
                print("\n!!! STOP COMMAND RECEIVED !!!")
                scope.AbortSlew()
                aborted = True
                break
            time.sleep(0.2)

        if not aborted:
            print(f"\n[V] Reached {target_name}.")
            print("(Press Enter to continue back to menu...)")

    except Exception as e:
        print(f"Error during movement: {e}")
        try: scope.AbortSlew()
        except: pass


def run_telescope_control():
    print("1. Initializing ASCOM...")
    try:
        scope = win32com.client.Dispatch("ASCOM.CPWI.Telescope")
        scope.Connected = True
        print("2. SUCCESS! Telescope connected.")
    except Exception as e:
        print(f"!!! ERROR: {e}")
        return

    print("Loading Skyfield data...")
    planets = load('de421.bsp')
    earth = planets['earth']
    ts = load.timescale()
    my_location = earth + Topos(latitude_degrees=MY_LAT, longitude_degrees=MY_LON, elevation_m=MY_ALT)

    while True:
        print("\n==============================")
        print("--- TELESCOPE CONTROL MENU ---")
        print("Options: track, gps, north, moon, mars/jupiter..., exit")
        user_input = input("Command: ").strip().lower()

        if user_input == 'exit':
            try: scope.AbortSlew()
            except: pass
            break

        if user_input == 'track':
            print("\n>>> Starting Camera Tracker...")
            tracker.start_tracking(scope)
            continue

        if user_input == 'gps':
            try:
                lat = float(input("Target Latitude: "))
                lon = float(input("Target Longitude: "))
                alt_m = float(input("Target Altitude (m): "))

                target = earth + Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=alt_m)
                t = ts.now()
                alt, az, distance = my_location.at(t).observe(target).apparent().altaz()

                print(f"Calculated: Az={az.degrees:.2f}, Alt={alt.degrees:.2f}, Dist={distance.km:.2f}km")

                if alt.degrees < 0:
                    print("ERROR: Target is BELOW HORIZON.")
                    continue

                if input("Slew? (y/n): ") == 'y':
                    safe_move(scope, az.degrees, alt.degrees, "GPS Target")

            except Exception as e:
                print(f"Error: {e}")
            continue

        if user_input == 'north':
            safe_move(scope, 0.0, MIN_SAFE_ALTITUDE, "North")
            continue

        if user_input in ['moon', 'mars', 'jupiter', 'saturn', 'venus']:
            try:
                target_key = 'moon' if user_input == 'moon' else f"{user_input} barycenter"
                t = ts.now()
                alt, az, _ = my_location.at(t).observe(planets[target_key]).apparent().altaz()

                print(f"Target: {user_input.upper()} (Alt: {alt.degrees:.2f})")
                if alt.degrees <= 0:
                    print("Target is below horizon.")
                    continue

                if user_input == 'moon':
                    try: scope.TrackingRate = 1  # Lunar
                    except: pass
                else:
                    try: scope.TrackingRate = 0  # Sidereal
                    except: pass

                if input("Slew? (y/n): ") == 'y':
                    safe_move(scope, az.degrees, alt.degrees, user_input.upper())

            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    run_telescope_control()
