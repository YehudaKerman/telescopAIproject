import cv2
import numpy as np
import math

print("Initializing Robust Tracker (Brightness + Patience)...")

def calculate_distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def start_robust_tracking_test():
    print("--- ROBUST TRACKER ---")
    print("1. Exposure adjusted for indoor lighting.")
    print("2. 'Patience' added: Waits before switching targets.")

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    if not cap.isOpened():
        print("Error: Camera not found.")
        return

    # --- תיקון 1: הגדרות מצלמה (בהירות וגודל) ---
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # חשיפה: -3 או -4 זה בהיר וטוב לחדר. -6 או -7 זה חשוך וטוב לשמש.
    # תשחק עם המספר הזה אם עדיין חשוך/בהיר מדי.
    cap.set(cv2.CAP_PROP_EXPOSURE, -3)

    # משתנים למעקב
    tracker = None
    is_tracking = False
    prev_gray = None

    # לוגיקת סינון תנועה (כמו קודם)
    potential_target_center = None
    frames_consistently_tracked = 0
    MOVEMENT_THRESHOLD = 50

    # --- תיקון 2: מנגנון סבלנות (Patience) ---
    # כמה פריימים לחכות כשהמטרה הולכת לאיבוד לפני שמתייאשים?
    # 30 פריימים = בערך שניה אחת. רוצה יותר? שנה ל-60 או 90.
    MAX_PATIENCE = 60
    patience_counter = 0

    while True:
        ret, frame = cap.read()
        if not ret: break

        height, width, _ = frame.shape
        center_x, center_y = width // 2, height // 2

        # -------------------------------------------------------
        # מצב מעקב (Tracking Mode)
        # -------------------------------------------------------
        if is_tracking:
            success, box = tracker.update(frame)

            if success:
                # הטרקר רואה את המטרה - הכל מצוין
                patience_counter = MAX_PATIENCE # מאפסים את מונה הסבלנות למקסימום

                (x, y, w, h) = [int(v) for v in box]
                obj_x = x + w // 2
                obj_y = y + h // 2

                # ירוק = נעול ויציב
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.circle(frame, (obj_x, obj_y), 5, (0, 0, 255), -1)
                cv2.line(frame, (center_x, center_y), (obj_x, obj_y), (0, 255, 255), 2)

                cv2.putText(frame, "LOCKED", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                # --- המטרה אבדה! נכנסים למצב "סבלנות" ---
                if patience_counter > 0:
                    patience_counter -= 1

                    # מציירים ריבוע כתום איפה שהיא הייתה לאחרונה
                    cv2.putText(frame, f"LOST... Waiting: {patience_counter}", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                else:
                    # נגמרה הסבלנות - חוזרים לסריקה
                    print("Target permanently lost. Rescanning...")
                    is_tracking = False
                    tracker = None
                    prev_gray = None
                    potential_target_center = None

        # -------------------------------------------------------
        # מצב סריקה (Scanning Mode)
        # -------------------------------------------------------
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            if prev_gray is None:
                prev_gray = gray
                continue

            frame_delta = cv2.absdiff(prev_gray, gray)
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
            thresh = cv2.dilate(thresh, None, iterations=2)
            contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            best_contour = None
            max_area = 0

            for c in contours:
                if cv2.contourArea(c) < 500: continue # סינון רעש
                if cv2.contourArea(c) > max_area:
                    max_area = cv2.contourArea(c)
                    best_contour = c

            if best_contour is not None:
                (x, y, w, h) = cv2.boundingRect(best_contour)
                current_center = (x + w//2, y + h//2)

                if potential_target_center is None:
                    potential_target_center = current_center
                else:
                    dist = calculate_distance(current_center, potential_target_center)

                    # כחול = זיהוי תנועה ראשוני
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)

                    if dist > MOVEMENT_THRESHOLD:
                        print(f"Movement confirmed ({int(dist)}px). Locking!")
                        tracker = cv2.TrackerCSRT_create()
                        tracker.init(frame, (x, y, w, h))
                        is_tracking = True
                        patience_counter = MAX_PATIENCE # טוענים סבלנות להתחלה

            else:
                potential_target_center = None
                cv2.putText(frame, "Scanning...", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            prev_gray = gray

        # כוונת
        cv2.line(frame, (center_x, 0), (center_x, height), (100, 100, 100), 1)
        cv2.line(frame, (0, center_y), (width, center_y), (100, 100, 100), 1)

        cv2.imshow('Robust Tracker', frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'): break
        if key == ord('r'):
            is_tracking = False
            tracker = None
            potential_target_center = None

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    start_robust_tracking_test()