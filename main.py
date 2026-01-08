import win32com.client
from skyfield.api import load, Topos
import time

LAT, LON = '32.0853 N', '34.7818 E'

def run_telescope_control():
    scope = win32com.client.Dispatch("ASCOM.CPWI.Telescope")
    scope.Connected = True

    planets = load('de421.bsp')
    earth = planets['earth']
    ts = load.timescale()

    while True:
        user_input = input("\nלאן לכוון? (moon, sun, jupiter...) או 'exit': ").strip().lower()
        if user_input == 'exit': break

        # התאמת שם הגוף לקובץ הנתונים
        if user_input == 'moon':
            target_key = 'moon'
            tracking_type = 1 # Lunar
        elif user_input == 'sun':
            target_key = 'sun'
            tracking_type = 2 # Solar
        else:
            target_key = f"{user_input} barycenter"
            tracking_type = 0 # Sidereal (לכוכבי לכת)

        try:
            target = planets[target_key]
            t = ts.now()
            alt, az, _ = (earth + Topos(LAT, LON)).at(t).observe(target).apparent().altaz()

            if alt.degrees < 0:
                print("היעד מתחת לאופק.")
                continue

            # הגדרת קצב העקיבה המתאים
            scope.TrackingRate = tracking_type

            print(f"מכוון ל-{user_input} (קצב עקיבה: {tracking_type})...")
            scope.SlewToAltAzAsync(az.degrees, alt.degrees)

            # המתנה לפקודת עצירה
            stop_input = input("הקלד 'stop' לעצירה: ").strip().lower()
            if stop_input == 'stop':
                scope.AbortSlew()
                print("נעצר.")

        except Exception as e:
            print(f"שגיאה: {e}. וודא שהשם נכון (למשל 'mars' ולא 'marz')")

if __name__ == "__main__":
    run_telescope_control()