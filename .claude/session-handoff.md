# Session Handoff — 2026-03-19

## 🎯 Next Session — RPi Deploy (B+ architecture)

## ✅ Completed
ריפקטורינג מלא + git commit `b963a0a` על main.
ענף `pre-refactor` → `d837b81` שמור ב-GitHub.

## 🏗️ Architecture Decision (סגור)

**B+: tracker רץ ב-RPi, Windows רואה בלבד**

```
RPi:     ZWO → tracker → PID → indiserver → Celestron
                  ↓ (annotated frames)
         Flask MJPEG stream (port 8080)
                  ↓ חד-כיווני
Windows: cv2.imshow()  ← רואה ריבוע מעקב בלבד
```

- Loop control: ~30-80ms (מקומי ב-RPi)
- WiFi lag: משפיע רק על תצוגה, לא על מעקב
- תומך ברחפן/מטוס (latency מספיק נמוך)

## ❗ מה לבנות הסשן הבא

### שלב 1 — הגדרת RPi
```bash
ssh pi@<IP>
sudo apt install indiserver indi-celestron libindi-dev
pip3 install pyindi-client zwoasi flask opencv-python pyyaml skyfield
```

### שלב 2 — קבצים חדשים לכתוב
| קובץ | תפקיד |
|------|-------|
| `rpi/stream_server.py` | Flask MJPEG — שולח פריימים מוערחים |
| `main_rpi.py` | entry point ל-RPi (INDI + ZWO + tracker + stream) |
| `main_remote.py` | entry point ל-Windows (תצוגה + פקודות) |
| `rpi/requirements_rpi.txt` | deps ל-RPi |

### שלב 3 — עדכון config.yaml
```yaml
mount:
  backend: "indi"
indi:
  host: "localhost"
  device_name: "Celestron GPS"   # לוודא עם indiserver

camera:
  backend: "zwo"
  sdk_path: "/usr/lib/libASICamera2.so"

stream:
  port: 8080
  quality: 70       # JPEG quality 0-100
  fps_limit: 20     # לא לעמיס את הרשת
```

## ❓ שאלה פתוחה לתחילת הסשן
רשת בשדה: RPi כ-hotspot עצמאי, או שניהם על ראוטר?

## 📁 State
```
telescopAIproject/
├── main_rpi.py        ← לכתוב
├── main_remote.py     ← לכתוב
├── rpi/               ← לכתוב
│   ├── stream_server.py
│   └── requirements_rpi.txt
├── core/tracker.py    ✅ מוכן (יפעל ב-RPi ללא שינוי)
├── hardware/indi_driver.py ✅ מוכן
├── camera/zwo_camera.py    ✅ מוכן (לבדוק על RPi)
└── tests/             ✅ 30/30
```
