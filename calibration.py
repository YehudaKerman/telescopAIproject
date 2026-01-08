import win32com.client

def check_camera():
    try:
        # ניסיון גישה דרך הדרייבר של ASCOM
        camera = win32com.client.Dispatch("ASCOM.ASICamera2.Camera")
        camera.Connected = True
        print(f"המצלמה מזוהה ועובדת! דגם: {camera.Name}")
        camera.Connected = False
    except Exception as e:
        print(f"המצלמה לא נמצאה ב-ASCOM. וודא שהתקנת ASI ASCOM Driver. שגיאה: {e}")

check_camera()