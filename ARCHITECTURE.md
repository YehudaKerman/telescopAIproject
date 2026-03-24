# TelescopeAI — Project Architecture Map

> **תרשימים אינטראקטיביים:** פתח קובץ זה ב-GitHub — התרשימים מתרנדרים אוטומטית.
> לצפייה מיידית: העתק כל בלוק `mermaid` ל-[mermaid.live](https://mermaid.live)

---

## Diagram 1 — Runtime Process Flow

מה קורה בזמן ריצה: מ-boot ועד פקודת ציר.

```mermaid
flowchart TD
    BOOT([RPi Boot]) --> SVC[systemd: indiserver.service]
    SVC --> INDI[(indiserver :7624\nindi_celestron_gps)]

    BOOT --> RUN[".venv/bin/python main_rpi.py"]
    RUN --> CFG[load_config\nconfig.yaml]

    CFG --> STHREAD["StreamServer thread\nFlask :8080/video"]
    CFG --> HW[Hardware init]

    HW --> SCOPE["INDITelescopeDriver\nconnect → :7624"]
    SCOPE <-->|TCP PyIndi| INDI
    HW --> CAM["ZWOCamera\nopen SDK, start capture"]

    SCOPE & CAM --> LOOP["start_tracking()\nheadless=True"]

    LOOP --> Q{is_tracking?}

    Q -->|No — Scanning| DIFF["frame-diff\n→ contours\n→ largest blob"]
    DIFF --> MOVE{movement\n> 50px?}
    MOVE -->|No| Q
    MOVE -->|Yes| CSRT_INIT["CSRT tracker init\nis_tracking = True"]
    CSRT_INIT --> Q

    Q -->|Yes — Tracking| CSRT_UP["csrt.update(frame)"]
    CSRT_UP --> OK{success?}

    OK -->|Yes| ERR["pixel error\n→ deg (pixel_scale)"]
    ERR --> PID["PID az + alt\nerr_deg → rate_deg/s"]
    PID --> AXIS["scope.move_axis(0, rate_az)\nscope.move_axis(1, rate_alt)"]
    AXIS --> ANNOTATE["draw bbox + HUD\non_frame(frame)"]
    ANNOTATE --> QUEUE[/"frame_queue\n(maxsize=2)"/]
    QUEUE --> STHREAD
    ANNOTATE --> Q

    OK -->|No| PAT["patience_counter--"]
    PAT --> ZERO{= 0?}
    ZERO -->|No| Q
    ZERO -->|Yes| STOP["stop mount\nreset tracker"]
    STOP --> Q

    STHREAD -->|"MJPEG multipart\nhttp://kcg.local:8080/video"| WIN["main_remote.py\ncv2.imshow()"]

    style INDI fill:#2d4a6b,color:#fff
    style STHREAD fill:#1a5c38,color:#fff
    style WIN fill:#1a5c38,color:#fff
    style QUEUE fill:#5c3a1a,color:#fff
```

---

## Diagram 2 — Module Dependency Map

קשרים בין מודולים: מי מייבא את מי, ואיפה עוברת השליטה.

```mermaid
graph LR
    subgraph ENTRY["Entry Points"]
        MAIN["main.py\nWindows CLI"]
        MAINR["main_rpi.py\nRPi headless"]
        MAINW["main_remote.py\nWindows viewer"]
        CALIB["calibration.py"]
    end

    subgraph CORE["Core"]
        SESSION["core/session.py\nTelescopeSession"]
        TRACKER["core/tracker.py\nstart_tracking()"]
        PID["core/pid_controller.py\nPIDController"]
    end

    subgraph HW["Hardware (Mount)"]
        DFACT["hardware/__init__\ndriver_factory()"]
        BASE_D["hardware/base.py\nTelescopeDriver ABC"]
        ASCOM["ascom_driver.py\nWindows / CPWI"]
        INDI_D["indi_driver.py\nRPi / indiserver"]
        MOCK_D["mock_driver.py\ntests"]
    end

    subgraph CAM["Camera"]
        CFACT["camera/__init__\ncamera_factory()"]
        BASE_C["camera/base.py\nCameraDriver ABC"]
        OCV["opencv_camera.py\nUSB / webcam"]
        ZWO["zwo_camera.py\nZWO ASI183MC"]
        MOCK_C["mock_camera.py\ntests"]
    end

    subgraph RPI["RPi Streaming"]
        STREAM["rpi/stream_server.py\nStreamServer"]
    end

    subgraph UTILS["Utils"]
        CFG["utils/config.py\nload_config()"]
        LOG["utils/logger.py\nget_logger()"]
        GEO["utils/geometry.py\nlandmark_az_alt()"]
    end

    MAIN --> SESSION
    MAINR --> TRACKER
    MAINR --> STREAM
    MAINR --> DFACT
    MAINR --> CFACT

    SESSION --> TRACKER
    SESSION --> DFACT
    SESSION --> CFACT

    TRACKER --> PID
    TRACKER --> BASE_D
    TRACKER --> BASE_C

    DFACT --> ASCOM & INDI_D & MOCK_D
    ASCOM & INDI_D & MOCK_D --> BASE_D

    CFACT --> OCV & ZWO & MOCK_C
    OCV & ZWO & MOCK_C --> BASE_C

    CALIB --> DFACT & CFACT & GEO

    MAIN & MAINR & SESSION & CALIB --> CFG
    MAIN & MAINR & TRACKER & CALIB --> LOG
```

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        ENTRY POINTS                              │
│   main.py          — Windows interactive CLI (ASCOM + OpenCV)   │
│   main_rpi.py      — RPi headless (INDI + ZWO + MJPEG stream)  │
│   main_remote.py   — Windows viewer (receives RPi stream)       │
│   calibration.py   — Pixel scale + mount alignment wizard       │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│                  CORE ORCHESTRATION                              │
│   core/session.py  — TelescopeSession (context manager)         │
│     owns: scope + camera, slew_to(), start_tracking()           │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│                  TRACKING PIPELINE                               │
│   core/tracker.py  — start_tracking(scope, cam, cfg, ...)       │
│     Scanning mode: frame-diff → contours → CSRT init            │
│     Tracking mode: CSRT update → pixel error → PID → mount      │
│                              ↓                                   │
│   core/pid_controller.py — PIDController                        │
│     input: error (deg)  output: rate (deg/s), per axis          │
└──────────────────────────────────────────────────────────────────┘
          ↓ scope.move_axis()              ↓ camera.read()
┌─────────────────────┐        ┌──────────────────────────┐
│  HARDWARE / MOUNT   │        │       CAMERA             │
│  base.py (ABC)      │        │  base.py (ABC)           │
│  ├ ascom_driver.py  │        │  ├ opencv_camera.py      │
│  ├ indi_driver.py   │        │  ├ zwo_camera.py         │
│  └ mock_driver.py   │        │  └ mock_camera.py        │
│  __init__.py        │        │  __init__.py             │
│  driver_factory(cfg)│        │  camera_factory(cfg)     │
└─────────────────────┘        └──────────────────────────┘
```

---

## Module-by-Module Reference

### Entry Points

| File | Mode | Key function |
|------|------|-------------|
| [main.py](main.py) | Windows (ASCOM + OpenCV) | `run_telescope_control()` — menu: track, gps, north, moon, mars... |
| [main_rpi.py](main_rpi.py) | RPi headless | `main()` — tracker + MJPEG stream in threads |
| [main_remote.py](main_remote.py) | Windows viewer | `main()` — reads `http://kcg.local:8080/video`, shows cv2.imshow |
| [calibration.py](calibration.py) | Any | `main()` — pixel_scale, roll, alignment wizard |

### Core

| File | Class / Function | Purpose |
|------|-----------------|---------|
| [core/session.py](core/session.py) | `TelescopeSession` | Context manager owning scope + camera. `slew_to(name, az, alt)` with altitude safety. Wraps `start_tracking()`. |
| [core/tracker.py](core/tracker.py) | `start_tracking(scope, cam, cfg, on_frame, headless, stop_event)` | Full tracking loop. Scanning via frame-diff → locks with CSRT → feeds PID → calls `scope.move_axis()`. `on_frame` callback enables headless streaming. |
| [core/pid_controller.py](core/pid_controller.py) | `PIDController` | Standard PID with anti-windup and output limits. `.update(error_deg)` → rate_deg_s. Separate instance per axis. |

### Hardware Drivers (Mount)

| File | Class | Backend |
|------|-------|---------|
| [hardware/base.py](hardware/base.py) | `TelescopeDriver` (ABC) | Defines interface: `connect`, `disconnect`, `slew_to_altaz_async`, `move_axis`, `abort_slew`, `sync_to_altaz` |
| [hardware/ascom_driver.py](hardware/ascom_driver.py) | `ASCOMTelescopeDriver` | Windows COM via `win32com`. Used with CPWI / NexStar. |
| [hardware/indi_driver.py](hardware/indi_driver.py) | `INDITelescopeDriver` | PyIndi TCP to `indiserver` on RPi. Properties polled, not event-driven. |
| [hardware/mock_driver.py](hardware/mock_driver.py) | `MockTelescopeDriver` | In-memory, records all calls. For tests. |
| [hardware/\_\_init\_\_.py](hardware/__init__.py) | `driver_factory(cfg)` | Selects by `mount.backend`: `"ascom"` / `"indi"` / `"mock"` |

### Camera Drivers

| File | Class | Backend |
|------|-------|---------|
| [camera/base.py](camera/base.py) | `CameraDriver` (ABC) | Interface: `open`, `release`, `read()` → `(bool, BGR frame)`, `width`, `height` |
| [camera/opencv_camera.py](camera/opencv_camera.py) | `OpenCVCamera` | `cv2.VideoCapture` (DSHOW on Win, V4L2 on Linux) |
| [camera/zwo_camera.py](camera/zwo_camera.py) | `ZWOCamera` | `zwoasi` package. Outputs RGB24 → converted to BGR. |
| [camera/mock_camera.py](camera/mock_camera.py) | `MockCamera` | Generates frames with a synthetic moving dot (Lissajous). For PID tests. |
| [camera/\_\_init\_\_.py](camera/__init__.py) | `camera_factory(cfg)` | Selects by `camera.backend`: `"opencv"` / `"zwo"` / `"mock"` |

### RPi Streaming

| File | Class | Purpose |
|------|-------|---------|
| [rpi/stream_server.py](rpi/stream_server.py) | `StreamServer` | Flask MJPEG server. Reads `frame_queue`, encodes JPEG, serves on `/video`. |

### Utilities

| File | Functions | Purpose |
|------|-----------|---------|
| [utils/config.py](utils/config.py) | `load_config(path)`, `save_config(cfg, path)` | Read/write `config.yaml`. |
| [utils/logger.py](utils/logger.py) | `setup_logging(cfg)`, `get_logger(name)` | Unified logging (console + file). |
| [utils/geometry.py](utils/geometry.py) | `landmark_az_alt()`, `haversine()`, `true_bearing()`, `apply_refraction()` | GPS coordinates → Az/Alt for alignment. |

---

## Data Flow: Camera Frame → Mount Command

```
camera.read()
    │
    ▼ BGR numpy array (H × W × 3, uint8)
    │
    ├─ [SCANNING MODE — is_tracking=False]
    │   gray → Gaussian blur → absdiff with prev frame
    │   → threshold → dilate → find contours (area > 500px²)
    │   → track potential_target position
    │   → if movement > 50px: init CSRT, is_tracking=True
    │
    └─ [TRACKING MODE — is_tracking=True]
        csrt_tracker.update(frame) → (success, bbox)
        │
        obj_x, obj_y = bbox center
        err_x_deg = (obj_x - frame_cx) * pixel_scale   ← Az error
        err_y_deg = (frame_cy - obj_y) * pixel_scale   ← Alt error (flipped)
        │
        rate_az  = pid_az.update(err_x_deg)
        rate_alt = pid_alt.update(err_y_deg)
        │
        scope.move_axis(0, rate_az)    ← Azimuth
        scope.move_axis(1, rate_alt)   ← Altitude
        │
        on_frame(annotated_frame)      ← optional (RPi streaming)
```

---

## Axis & Rate Convention

```
axis 0 = Azimuth       rate > 0 → East,  rate < 0 → West
axis 1 = Altitude      rate > 0 → North, rate < 0 → South
units: degrees/second
```

---

## Config Structure (config.yaml)

```yaml
location:     lat/lon/alt — observer position (Skyfield + geometry)
landmarks:    GPS points for daytime alignment
tracking:     pixel_scale, pid_kp/ki/kd, movement_threshold_px
camera:       backend, index/sdk_path, width, height, exposure
mount:        backend, driver name, move/calibration rates
indi:         host, port, device_name (RPi only)
stream:       port, quality (RPi only)
rpi:          host (Windows viewer only)
logging:      level, file, file_level
calibration:  auto-written by calibration.py
```

---

## Deployment Modes

| Mode | Config | Run command |
|------|--------|-------------|
| Windows (full) | `mount.backend: ascom`, `camera.backend: opencv` | `python main.py` |
| RPi (headless) | `mount.backend: indi`, `camera.backend: zwo` | `.venv/bin/python main_rpi.py` |
| Windows viewer | — | `python main_remote.py` |
| Tests | `mount.backend: mock`, `camera.backend: mock` | `pytest tests/` |
