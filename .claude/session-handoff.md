# Session Handoff — 2026-03-19

## 🎯 Current Task
חיבור Raspberry Pi + deploy של TelescopeAI עליו

## ✅ Completed (סשנים קודמים)
ריפקטורינג מלא הושלם ונדחף ל-GitHub:
- `hardware/` — ASCOM + INDI + Mock backends
- `camera/` — OpenCV + ZWO + Mock backends
- `core/` — tracker, session, PID
- `utils/` — geometry, logger, config
- `tests/` — 30/30 passing
- `main.py` — שוכתב מחדש
- קומיט: `7245167` על `main`
- ענף `pre-refactor` → `d837b81` (קוד ישן שמור)

## ❗ Next Session — Raspberry Pi Setup

### מה צריך לדעת לפני:
- הקוד כבר תומך ב-INDI (`hardware/indi_driver.py`) — רק צריך להגדיר `config.yaml`
- ה-RPi צריך: Python 3.10+, indiserver, opencv, pyyaml, skyfield

### שלבים לביצוע:

#### 1. בדיקת חיבור RPi
```bash
ssh pi@<RPi_IP>
python3 --version
```

#### 2. Clone הקוד ל-RPi
```bash
git clone https://github.com/YehudaKerman/telescopAIproject.git
cd telescopAIproject
pip3 install -r requirements.txt
# אם ZWO: pip3 install zwoasi
```

#### 3. עדכון config.yaml ל-INDI
```yaml
mount:
  backend: "indi"

indi:
  host: "localhost"    # או IP של RPi אם מריצים מרחוק
  port: 7624
  device_name: "Telescope Simulator"  # לשנות לשם האמיתי

camera:
  backend: "opencv"
  index: 0
```

#### 4. הרצת indiserver על RPi
```bash
indiserver -v indi_eqmod_telescope   # או הדרייבר הנכון לטלסקופ
```

#### 5. בדיקת חיבור INDI
```python
from utils.config import load_config
from hardware import driver_factory
cfg = load_config()
d = driver_factory(cfg)
d.connect()
print(d.azimuth, d.altitude)
```

#### 6. הרצה מלאה
```bash
python3 main.py
```

### ❓ שאלות פתוחות לברר עם המשתמש:
- איזה mount בדיוק? (EQ5? EQMod? CelestronCGX?)
- איזה דרייבר INDI? (indi_eqmod_telescope? indi_celestron_gps?)
- ה-RPi ו-Windows על אותו רשת? (לבדיקת INDI over network)
- ZWO ASI183MC מחובר ל-RPi או ל-Windows?

## 📁 Important Files
- `hardware/indi_driver.py` — INDI driver מלא, צריך לוודא device_name
- `config.yaml` — לשנות backend ל-"indi" ולמלא indi.device_name
- `requirements.txt` — תקין, pyindi-client מוגדר כהערה (uncomment ב-RPi)
