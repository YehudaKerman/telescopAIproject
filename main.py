import win32com.client
from skyfield.api import load, Topos
import time
LAT, LON = '32.0616 N', '35.1222 E'
print("1. Attempting to initialize ASCOM...")
try:
    scope = win32com.client.Dispatch("ASCOM.CPWI.Telescope")
    print("2. Driver Dispatched. Now connecting to telescope (make sure CPWI is open)...")

    scope.Connected = True
    print("3. SUCCESS! Telescope is connected and ready.")

except Exception as e:
    print(f"!!! ERROR: {e}")
def run_telescope_control():
    scope = win32com.client.Dispatch("ASCOM.CPWI.Telescope")
    scope.Connected = True

    planets = load('de421.bsp')
    earth = planets['earth']
    ts = load.timescale()

    while True:
        user_input = input("\nלאן לכוון? (moon, sun, north, or exit): ").strip().lower()

        if user_input == 'exit':
            break

        # טיפול מיוחד בפקודת צפון
        if user_input == 'north':
            print("Moving to Home Position (North & Horizon)...")
            scope.SlewToAltAz(0.0, 0.0) # פקודה ישירה למיקום פיזי
            while scope.Slewing:
                print(f"Slewing to North... Current Alt: {scope.Altitude:.2f}")
                time.sleep(1)
            print("Telescope is now facing North!")
            continue # חוזר לתחילת הלולאה לבקש יעד חדש

        # התאמת שם הגוף לקובץ הנתונים עבור גרמי שמיים
        if user_input == 'moon':
            target_key = 'moon'
            tracking_type = 1 # Lunar
        elif user_input == 'sun':
            target_key = 'sun'
            tracking_type = 2 # Solar
        else:
            target_key = f"{user_input} barycenter"
            tracking_type = 0 # Sidereal

        try:
            target_obj = planets[target_key] # שינינו ל-target_obj כדי למנוע בלבול
            t = ts.now()
            # חישוב מיקום בשמיים
            alt, az, _ = (earth + Topos(LAT, LON)).at(t).observe(target_obj).apparent().altaz()

            if alt.degrees < 0:
                print(f"היעד {user_input} נמצא כרגע מתחת לאופק ({alt.degrees:.2f} מעלות).")
                continue

            scope.TrackingRate = tracking_type
            print(f"מכוון ל-{user_input} (Az: {az.degrees:.2f}, Alt: {alt.degrees:.2f})...")
            scope.SlewToAltAzAsync(az.degrees, alt.degrees)

            stop_input = input("הקלד 'stop' לעצירה: ").strip().lower()
            if stop_input == 'stop':
                scope.AbortSlew()
                print("נעצר.")

        except Exception as e:
            print(f"שגיאה: {e}. וודא שהשם נכון (למשל 'jupiter' ולא 'jupitrr')")
if __name__ == "__main__":
    run_telescope_control()