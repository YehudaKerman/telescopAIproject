import win32com.client

def check_where_am_i():
    scope = win32com.client.Dispatch("ASCOM.CPWI.Telescope")
    scope.Connected = True

    print("--- Telescope Brain Check ---")
    print("PHYSICALLY: You should be pointing North and Level (Horizon).")
    print(f"COMPUTER THINKS: Azimuth: {scope.Azimuth:.2f}, Altitude: {scope.Altitude:.2f}")

    if abs(scope.Altitude) > 5:
        print("\n>>> DIAGNOSIS: Alignment Offset Detected!")
        print(f"The telescope thinks 'Level' is {scope.Altitude:.2f} degrees off.")
    else:
        print("\n>>> DIAGNOSIS: Alignment looks good.")

if __name__ == "__main__":
    check_where_am_i()