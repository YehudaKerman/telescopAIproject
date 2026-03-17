# Session Handoff — 2026-03-17

## 🎯 Current Task
ניתוח פרויקט TelescopeAI לפי מסמך האפיון (SRS) — זיהוי פערים והצעות שיפור

## ✅ Completed This Session
- קריאת כל קבצי הפרויקט (tracker.py, main.py, config.yaml, calibration.py, find_landmarks.py, pid_controller.py)
- ניתוח מעמיק מול מסמך האפיון
- זיהוי בעיות קריטיות, שיפורי ארכיטקטורה, ופיצ'רים חסרים
- כתיבת תוכנית שיפור מלאה

## 🔧 Key Decisions Made
- לא בוצעו שינויים בקוד בסשן זה — רק ניתוח
- עדיפות #1: config unification
- עדיפות #2: geometry.py משותף

## 📁 Important Files Touched
- `.claude/session-handoff.md` — קובץ זה

## ❗ Open Issues / Next Steps

### 🔴 קריטי
1. **Config Unification** — `main.py` ו-`tracker.py` מכילים hardcoded values שלא מסונכרנות עם `config.yaml`:
   - `main.py`: `MY_LAT = 32.1065`, `MY_LON = 35.2070`, `MY_ALT = 713`
   - `tracker.py`: `PIXEL_SCALE = 0.094`, `MOVEMENT_THRESHOLD = 50`, `MAX_PATIENCE = 60`
   - **פתרון:** לטעון ערכים מ-`config.yaml` בתחילת כל קובץ

2. **כפילות גיאומטריה** — `haversine()`, `true_bearing()`, `apply_refraction()` כתובות פעמיים:
   - **פתרון:** קובץ `utils/geometry.py` משותף

### 🟡 חשוב
3. **Logging** — להחליף `print()` ב-`logging` (עם רמות, timestamps, קבצי לוג)
4. **TelescopeDriver ABC** — שכבת הפשטה לתמיכה ב-ASCOM (Windows) + INDI (RPi/Linux) + MockDriver (בדיקות)

### 🟢 שיפורים מהאפיון
5. Smart Auto-Exposure (חשיפה קבועה כרגע)
6. Virtual Binning/Scaling
7. מעקב אסטרונומי רציף (כרגע רק Slew, אין תיקון תנועה)
8. Web GUI (Streamlit / Flask)

## 🐛 Errors Encountered & Solutions
- אין שגיאות — סשן ניתוח בלבד

## 💬 Context for Next Session
הבעיה הכי דחופה: `main.py` ו-`tracker.py` מכילים ערכי קונפיגורציה hardcoded שלא מסונכרנים עם `config.yaml`. שינוי ב-config.yaml **לא ישפיע** על ריצה בפועל! זה הצעד הראשון שצריך לתקן.

מבנה תיקיות מוצע לעתיד:
```
telescopAIproject/
├── core/          (tracker.py, pid_controller.py, astronomical.py)
├── hardware/      (ascom_driver.py, indi_driver.py, mock_driver.py)
├── utils/         (config.py, geometry.py, logger.py)
├── calibration/   (calibration.py, find_landmarks.py)
└── tests/
```
