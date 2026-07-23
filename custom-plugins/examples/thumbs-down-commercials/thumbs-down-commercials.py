
import asyncio
import websockets
import json
import time
import os
import cv2
import base64
import platform
import aiohttp

from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import mediapipe as mp

PLUGIN_PROTOCOL_VERSION = 1 # DO NOT TOUCH

PLUGIN_NAME = "Thumbs Down Commercials"
PLUGIN_ID = "my-trigger-plugin-ws" # Must be unique
PLUGIN_VERSION = "1.1.0"

# --------------------------------------------------
# Configuration
# --------------------------------------------------

PORT = 64145

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "gesture_recognizer.task")
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "gesture_recognizer/gesture_recognizer/float16/latest/"
    "gesture_recognizer.task"
)

is_debug_mode = False
CAMERA_INDEX = 0
MIRROR_CAMERA = True

# default values
COMMERCIAL_GESTURE = "Thumb_Down"
CONTENT_GESTURE = "ILoveYou"
COMMERCIAL_GESTURE_COUNT = 2
CONTENT_GESTURE_COUNT = 1
TOTAL_HANDS_PROCESSED = 4

# MediaPipe Gesture Recognizer canned gesture names.
GESTURE_OPTIONS = {
    "Closed_Fist": {"label": "Closed Fist \u270A", "emoji": "\u270A"},
    "Open_Palm": {"label": "Open Palm \u270B", "emoji": "\u270B"},
    "Pointing_Up": {"label": "Pointing Up \u261D\uFE0F", "emoji": "\u261D\uFE0F"},
    "Thumb_Down": {"label": "Thumb Down \uD83D\uDC4E", "emoji": "\uD83D\uDC4E"},
    "Thumb_Up": {"label": "Thumb Up \uD83D\uDC4D", "emoji": "\uD83D\uDC4D"},
    "Victory": {"label": "Victory \u270C\uFE0F", "emoji": "\u270C\uFE0F"},
    "ILoveYou": {"label": "I Love You \uD83E\uDD1F", "emoji": "\uD83E\uDD1F"},
}

REQUIRED_GESTURE_COUNTS = {}
TARGET_GESTURES = {}

GREEN_SQUARE = "\uD83D\uDFE9"
CHECK_BUTTON = "\u2705"
HAND_PREFIX = ""
DEBUG_TRIGGER_DISPLAY_DURATION = 2.0

THRESHOLDS = [
    (0.90, 0.1),
    (0.80, 0.3),
    (0.57, 0.8),
]

VISIBILITY_THRESHOLD = 0.50
COOLDOWN = 1.0

SNAPSHOT_MAX_WIDTH = 400
SNAPSHOT_MAX_HEIGHT = 400

# --------------------------------------------------
# Global state
# --------------------------------------------------

clients = set()

camera_task = None
camera_active = asyncio.Event()

camera_options = None
default_camera = None

current_is_commercial = None
last_status_display = None

gesture_group_states = {}

any_trigger_display_until = time.time()

# --------------------------------------------------
# Model management
# --------------------------------------------------

async def ensure_model_exists(ws):
    """
    Download the MediaPipe gesture model if it is not already present.

    Returns:
        True if the model exists and appears valid.
        False if the download or validation fails.
    """

    if os.path.isfile(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 0:
        print(f"Model found: {MODEL_PATH}")
        return True

    await send_status(
        ws,
        "Downloading AI model...",
        "Downloading MediaPipe Gesture Recognizer model..."
    )

    print("Gesture recognizer model was not found.")
    print("Downloading MediaPipe model...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(MODEL_URL) as response:
                response.raise_for_status()

                with open(MODEL_PATH, "wb") as f:
                    total = int(response.headers.get("Content-Length", 0))
                    downloaded = 0

                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        downloaded += len(chunk)
                        f.write(chunk)

                        if total:
                            percent = int(downloaded * 100 / total)

                            await send_status(
                                ws,
                                f"Downloading AI model... {percent}%",
                                f"Downloaded {downloaded:,} / {total:,} bytes"
                            )

        return True

    except Exception as error:
        print(f"Failed to download gesture model: {error}")

        return False

# --------------------------------------------------
# Preference helpers
# --------------------------------------------------

def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def rebuild_target_gestures():
    """Rebuild runtime gesture mappings from the current preferences."""
    global TARGET_GESTURES
    global REQUIRED_GESTURE_COUNTS
    global gesture_group_states

    TARGET_GESTURES = {
        COMMERCIAL_GESTURE: {
            "action": "commercial",
            "emoji": GESTURE_OPTIONS[COMMERCIAL_GESTURE]["emoji"],
        },
        CONTENT_GESTURE: {
            "action": "content",
            "emoji": GESTURE_OPTIONS[CONTENT_GESTURE]["emoji"],
        },
    }

    REQUIRED_GESTURE_COUNTS = {
        COMMERCIAL_GESTURE: COMMERCIAL_GESTURE_COUNT,
        CONTENT_GESTURE: CONTENT_GESTURE_COUNT,
    }

    gesture_group_states.clear()


def get_video_capture_backend():
    # DirectShow generally avoids slow camera probing on Windows.
    if platform.system() == "Windows":
        return cv2.CAP_DSHOW
    return cv2.CAP_ANY


def get_available_cameras(max_index=10):
    """Return camera options OpenCV can successfully open."""
    cameras = []
    backend = get_video_capture_backend()

    for index in range(max_index):
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            success, _ = cap.read()
            if success:
                cameras.append({
                    "label": f"Camera {index}",
                    "value": str(index),
                })
        cap.release()

    # Always provide a usable option even if probing is blocked by another app.
    if not cameras:
        cameras.append({"label": "Camera 0", "value": "0"})

    return cameras


def apply_plugin_preferences(preferences):
    global CAMERA_INDEX
    global MIRROR_CAMERA
    global COMMERCIAL_GESTURE
    global CONTENT_GESTURE
    global COMMERCIAL_GESTURE_COUNT
    global CONTENT_GESTURE_COUNT
    global VISIBILITY_THRESHOLD
    global COOLDOWN
    global TOTAL_HANDS_PROCESSED

    print(preferences)

    available_gestures = set(GESTURE_OPTIONS)

    try:
        CAMERA_INDEX = max(0, int(preferences.get("cameraIndex", CAMERA_INDEX)))
    except (TypeError, ValueError):
        print("Invalid cameraIndex preference; keeping", CAMERA_INDEX)

    MIRROR_CAMERA = bool(preferences.get("mirrorCamera", MIRROR_CAMERA))

    commercial_gesture = preferences.get(
        "commercialGesture",
        COMMERCIAL_GESTURE,
    )
    content_gesture = preferences.get(
        "contentGesture",
        CONTENT_GESTURE,
    )

    if commercial_gesture in available_gestures:
        COMMERCIAL_GESTURE = commercial_gesture

    if content_gesture in available_gestures:
        CONTENT_GESTURE = content_gesture

    # Using the same gesture for both actions would make state changes ambiguous.
    if CONTENT_GESTURE == COMMERCIAL_GESTURE:
        fallback = "Thumb_Up" if COMMERCIAL_GESTURE != "Thumb_Up" else "Thumb_Down"
        print(
            "Commercial and content gestures matched; "
            f"using {fallback} for content instead."
        )
        CONTENT_GESTURE = fallback

    try:
        COMMERCIAL_GESTURE_COUNT = int(clamp(
            int(preferences.get(
                "commercialGestureCount",
                COMMERCIAL_GESTURE_COUNT,
            )),
            1,
            4,
        ))
    except (TypeError, ValueError):
        print("Invalid commercialGestureCount preference")

    try:
        CONTENT_GESTURE_COUNT = int(clamp(
            int(preferences.get(
                "contentGestureCount",
                CONTENT_GESTURE_COUNT,
            )),
            1,
            4,
        ))
    except (TypeError, ValueError):
        print("Invalid contentGestureCount preference")

    try:
        TOTAL_HANDS_PROCESSED = int(preferences.get("totalHandsProcessed", TOTAL_HANDS_PROCESSED))
    except (TypeError, ValueError):
        print("Invalid totalHandsProcessed preference")

    try:
        VISIBILITY_THRESHOLD = float(clamp(
            float(preferences.get(
                "minimumGestureConfidence",
                VISIBILITY_THRESHOLD,
            )),
            0.0,
            1.0,
        ))
    except (TypeError, ValueError):
        print("Invalid minimumGestureConfidence preference")

    try:
        COOLDOWN = float(clamp(
            float(preferences.get("cooldownSeconds", COOLDOWN)),
            0.0,
            10.0,
        ))
    except (TypeError, ValueError):
        print("Invalid cooldownSeconds preference")

    rebuild_target_gestures()

    print(
        "Applied plugin preferences:",
        {
            "cameraIndex": CAMERA_INDEX,
            "mirrorCamera": MIRROR_CAMERA,
            "commercialGesture": COMMERCIAL_GESTURE,
            "commercialGestureCount": COMMERCIAL_GESTURE_COUNT,
            "contentGesture": CONTENT_GESTURE,
            "contentGestureCount": CONTENT_GESTURE_COUNT,
            "minimumGestureConfidence": VISIBILITY_THRESHOLD,
            "cooldownSeconds": COOLDOWN,
        },
    )


rebuild_target_gestures()

# --------------------------------------------------
# Display helpers
# --------------------------------------------------

def get_gesture_for_action(action):
    for gesture_name, config in TARGET_GESTURES.items():
        if config["action"] == action:
            return gesture_name
    return None

def get_expected_action():
    # If currently commercial, expect content action.
    # If currently content or unknown, expect commercial action.
    if current_is_commercial is True:
        return "content"
    return "commercial"

def get_expected_gesture_name():
    return get_gesture_for_action(get_expected_action())

def build_gesture_display(gesture_name, detected_count=0, triggered=False):
    config = TARGET_GESTURES[gesture_name]
    required_count = REQUIRED_GESTURE_COUNTS.get(gesture_name, 1)

    detected_count = max(0, min(detected_count, required_count))

    if triggered:
        slots = [CHECK_BUTTON] * required_count
    else:
        slots = (
            [GREEN_SQUARE] * detected_count +
            [config["emoji"]] * (required_count - detected_count)
        )

    return HAND_PREFIX + " " + " ".join(slots)

async def send_expected_resting_status(ws, debug="Ready"):
    expected_gesture = get_expected_gesture_name()

    if not expected_gesture:
        return

    display = build_gesture_display(
        expected_gesture,
        detected_count=0,
        triggered=False
    )

    await send_status_if_changed(ws, display, debug)

async def send_progress_status(ws, gesture_name, detected_count):
    display = build_gesture_display(
        gesture_name,
        detected_count=detected_count,
        triggered=False
    )

    await send_status_if_changed(
        ws,
        display,
        f"Detected {detected_count} of {REQUIRED_GESTURE_COUNTS.get(gesture_name, 1)} required {gesture_name}"
    )

async def send_trigger_status(ws, gesture_name):
    display = build_gesture_display(
        gesture_name,
        detected_count=REQUIRED_GESTURE_COUNTS.get(gesture_name, 1),
        triggered=True
    )

    await send_status_if_changed(
        ws,
        display,
        f"{gesture_name} trigger confirmed"
    )

async def send_status_if_changed(ws, display, debug):
    global last_status_display

    if display == last_status_display:
        return

    last_status_display = display
    await send_status(ws, display, debug)

# --------------------------------------------------
# Image helpers
# --------------------------------------------------

def frame_to_base64(frame, max_width=SNAPSHOT_MAX_WIDTH, max_height=SNAPSHOT_MAX_HEIGHT):
    if frame is None:
        return None

    frame = frame.copy()

    height, width = frame.shape[:2]

    scale = min(
        max_width / width,
        max_height / height,
        1.0
    )

    new_width = int(width * scale)
    new_height = int(height * scale)

    if scale < 1.0:
        frame = cv2.resize(
            frame,
            (new_width, new_height),
            interpolation=cv2.INTER_AREA
        )

    success, buffer = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, 98]
    )

    if not success or buffer is None:
        return None

    base64_data = base64.b64encode(
        buffer.tobytes()
    ).decode("utf-8")

    return f"data:image/jpeg;base64,{base64_data}"

# --------------------------------------------------
# Gesture helpers
# --------------------------------------------------

def find_gesture_config(gesture_name):
    return TARGET_GESTURES.get(gesture_name)

def passes_threshold(confidence, duration):
    for min_confidence, min_duration in THRESHOLDS:
        if confidence >= min_confidence and duration >= min_duration:
            return True
    return False

# --------------------------------------------------
# Trigger handling
# --------------------------------------------------

async def handle_trigger(ws, gesture_name, config, confidence, duration, frame):
    global current_is_commercial

    new_is_commercial = config["action"] == "commercial"

    if current_is_commercial is not None and current_is_commercial == new_is_commercial:
        print(f"IGNORED: {gesture_name} already matches current state")
        return False

    print(
        f"TRIGGERED: {gesture_name} | "
        f"confidence={confidence:.2f} | "
        f"duration={duration:.2f}s"
    )

    current_is_commercial = new_is_commercial

    debug_text = f"{gesture_name} detected"

    if is_debug_mode:
        debug_text = frame_to_base64(frame)

    trigger_display = build_gesture_display(
        gesture_name,
        detected_count=REQUIRED_GESTURE_COUNTS.get(gesture_name, 1),
        triggered=True
    )

    await send_commercial_state_change(
        ws,
        new_is_commercial,
        trigger_display,
        debug_text,
    )

    #await send_trigger_status(ws, gesture_name)

    return True

# --------------------------------------------------
# Gesture processing
# --------------------------------------------------

async def process_gesture_group(ws, gesture_name, hands, now, frame):
    global any_trigger_display_until
    config = find_gesture_config(gesture_name)

    if not config:
        return

    expected_gesture = get_expected_gesture_name()

    # Only show progress and trigger for the gesture that would change state.
    if gesture_name != expected_gesture:
        return

    required_count = REQUIRED_GESTURE_COUNTS.get(gesture_name, 1)

    matching_hands = [
        hand for hand in hands
        if hand["gesture_name"] == gesture_name
        and hand["confidence"] >= VISIBILITY_THRESHOLD
    ]

    current_count = len(matching_hands)

    if gesture_name not in gesture_group_states:
        gesture_group_states[gesture_name] = {
            "start_time": now,
            "triggered": False,
            "visible": False,
            "last_trigger_time": 0,
            "last_count": 0,
        }

    state = gesture_group_states[gesture_name]

    if current_count < required_count:
        if state["visible"]:
            print(f"HIDDEN GROUP: {gesture_name} count={current_count}")

        state["visible"] = False
        state["start_time"] = now
        state["triggered"] = False
        state["last_count"] = current_count

        if current_count > 0:

            await send_progress_status(
                ws,
                gesture_name,
                current_count
            )

        else:

            # Keep showing trigger checkmarks briefly
            if (
                is_debug_mode and
                now < any_trigger_display_until
            ):
                return

            await send_expected_resting_status(
                ws,
                "Waiting for gesture"
            )

        return

    avg_confidence = sum(
        hand["confidence"] for hand in matching_hands
    ) / current_count

    if not state["visible"]:
        state["visible"] = True
        state["start_time"] = now
        state["triggered"] = False

        print(
            f"VISIBLE GROUP: {gesture_name} "
            f"count={current_count} "
            f"confidence={avg_confidence:.2f}"
        )

    if state["last_count"] != current_count:
        await send_progress_status(ws, gesture_name, current_count)
        state["last_count"] = current_count

    duration = now - state["start_time"]

    if state["triggered"]:
        return

    if now - state["last_trigger_time"] < COOLDOWN:
        return

    if passes_threshold(avg_confidence, duration):
        did_trigger = await handle_trigger(
            ws,
            gesture_name,
            config,
            avg_confidence,
            duration,
            frame
        )

        if did_trigger:
            state["triggered"] = True
            state["last_trigger_time"] = now
            any_trigger_display_until = (now + DEBUG_TRIGGER_DISPLAY_DURATION)

# --------------------------------------------------
# Camera loop
# --------------------------------------------------

async def camera_loop(ws):
    cap = None
    recognizer = None
    debug_window_created = False

    try:
        if not await ensure_model_exists(ws):
            await send_status(
                ws,
                "Model unavailable",
                "The gesture recognition model could not be downloaded."
            )
            return

        print("Loading MediaPipe model...")
        await send_status(
            ws,
            "Loading MediaPipe model...",
            "Loading MediaPipe model..."
        )

        base_options = python.BaseOptions(
            model_asset_path=MODEL_PATH
        )

        options = vision.GestureRecognizerOptions(
            base_options=base_options,
            num_hands=max(
                TOTAL_HANDS_PROCESSED,
                COMMERCIAL_GESTURE_COUNT,
                CONTENT_GESTURE_COUNT,
            )
        )

        recognizer = vision.GestureRecognizer.create_from_options(options)

        cap = cv2.VideoCapture(CAMERA_INDEX, get_video_capture_backend())

        #TODO: add advanced/troubleshooting option for this
        # cap.set(
        #     cv2.CAP_PROP_FOURCC,
        #     cv2.VideoWriter_fourcc(*"MJPG")
        # )

        #TODO: add advanced/troubleshooting option for this
        # cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        #TODO: add advanced/troubleshooting option for this
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

        #TODO: add advanced/troubleshooting option for this
        # cap.set(cv2.CAP_PROP_FPS, 30)

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(f"Camera resolution: {width}x{height}")

        if not cap.isOpened():
            print("Failed to open webcam")
            return

        print("Camera started")

        if is_debug_mode:
            cv2.namedWindow(
                "MediaPipe Gesture Debug",
                cv2.WINDOW_NORMAL
            )
            debug_window_created = True

        await send_expected_resting_status(ws, "Ready")

        while True:
            await camera_active.wait()

            success, frame = cap.read()

            if not success:
                await asyncio.sleep(0.01)
                continue

            if MIRROR_CAMERA:
                frame = cv2.flip(frame, 1)

            #TODO: add option for this
            # display_frame = frame

            # processing_frame = cv2.resize(
            #     frame,
            #     None,
            #     fx=0.5,
            #     fy=0.5,
            #     interpolation=cv2.INTER_AREA
            # )

            # rgb_frame = cv2.cvtColor(
            #     processing_frame,
            #     cv2.COLOR_BGR2RGB
            # )

            rgb_frame = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=rgb_frame
            )

            result = recognizer.recognize(mp_image)

            now = time.time()
            detected_hands = []

            if result.gestures:
                for hand_index, gesture_list in enumerate(result.gestures):
                    if not gesture_list:
                        continue

                    top_gesture = gesture_list[0]

                    gesture_name = top_gesture.category_name
                    confidence = top_gesture.score

                    landmarks = result.hand_landmarks[hand_index]

                    xs = [lm.x for lm in landmarks]
                    ys = [lm.y for lm in landmarks]

                    h, w, _ = frame.shape

                    x1 = int(min(xs) * w)
                    y1 = int(min(ys) * h)
                    x2 = int(max(xs) * w)
                    y2 = int(max(ys) * h)

                    if is_debug_mode:
                        cv2.rectangle(
                            frame,
                            (x1, y1),
                            (x2, y2),
                            (0, 255, 0),
                            2
                        )

                        cv2.putText(
                            frame,
                            f"{gesture_name} {confidence:.2f}",
                            (x1, max(y1 - 10, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 255, 0),
                            2
                        )

                    detected_hands.append({
                        "gesture_name": gesture_name,
                        "confidence": confidence
                    })

            expected_gesture = get_expected_gesture_name()

            if expected_gesture:
                await process_gesture_group(
                    ws,
                    expected_gesture,
                    detected_hands,
                    now,
                    frame
                )

            if is_debug_mode:
                cv2.imshow(
                    "MediaPipe Gesture Debug",
                    frame
                )

                if cv2.waitKey(1) & 0xFF == 27:
                    break

            await asyncio.sleep(0)

    except asyncio.CancelledError:
        print("camera_loop shutting down")
        raise

    except Exception as error:
        print(f"Camera loop error: {error}")

    finally:
        print("Cleaning up camera resources")

        if cap is not None:
            cap.release()

        if debug_window_created:
            try:
                cv2.destroyAllWindows()

                # Let OpenCV process the window-close event.
                cv2.waitKey(1)

            except cv2.error:
                pass

        if recognizer is not None:
            try:
                recognizer.close()
                print("Recognizer closed")
            except Exception:
                pass

        print("Camera resources released")

# --------------------------------------------------
# WebSocket handling
# --------------------------------------------------

async def handle_client(websocket):
    global camera_task

    print("Client connected")
    clients.add(websocket)

    try:
        async for message in websocket:
            msg = json.loads(message)
            await handle_message(websocket, msg)

    except websockets.exceptions.ConnectionClosed:
        pass

    finally:
        clients.discard(websocket)

        if len(clients) == 0:
            print("Stopping camera")

            camera_active.clear()

            if camera_task:
                camera_task.cancel()

                try:
                    await camera_task
                except asyncio.CancelledError:
                    print("Camera task cancelled")

                camera_task = None

        print("Client disconnected")

# --------------------------------------------------
# Message handling
# --------------------------------------------------

async def handle_message(ws, msg):
    global camera_task
    global current_is_commercial
    global last_status_display
    global is_debug_mode

    message_type = msg["type"]

    if message_type == "plugin_manifest":
        await send_manifest(ws)

    if message_type == "init":
        data = msg.get("data", {})
        general_preferences = data.get("preferences", {})

        is_debug_mode = bool(
            general_preferences.get(
                "isDebugMode",
                data.get("isDebugMode", False),
            )
        )

        custom_trigger_plugin_preferences = general_preferences.get("pluginTriggerPreferences", {}).get("preferences", {})
        apply_plugin_preferences(custom_trigger_plugin_preferences)

        current_is_commercial = data.get("isCommercialState")

        last_status_display = None

        await send_status(
            ws,
            "Starting up...",
            "Starting up..."
        )

        camera_active.set()

        # Restart the camera task so camera, hand-count, and related settings
        # are guaranteed to take effect if a second init message is received.
        if camera_task:
            camera_task.cancel()
            try:
                await camera_task
            except asyncio.CancelledError:
                pass
            camera_task = None

        print("Starting camera task")
        camera_task = asyncio.create_task(
            camera_loop(ws)
        )

    elif message_type == "commercial_state_change":
        current_is_commercial = msg["data"]["isCommercialState"]

        last_status_display = None

        if is_debug_mode:
            print("waiting to send Commercial state updated")
            await asyncio.sleep(3)

        print("sending Commercial state updated")
        await send_expected_resting_status(
            ws,
            "Commercial state updated"
        )

    elif message_type == "browser_fullscreen_state_change":
        print("Fullscreen:", msg["data"]["isFullscreen"])

# --------------------------------------------------
# Send helpers
# --------------------------------------------------

async def send_commercial_state_change(
    ws,
    is_commercial,
    display,
    debug,
):
    global PLUGIN_PROTOCOL_VERSION

    try:
        await ws.send(json.dumps({
            "type": "commercial_state_change",
            "timestamp": time.time(),
            "data": {
                "isCommercial": is_commercial
            },
            "meta": {
                "display": display,
                "debug": debug,
            }
        }))

    except websockets.exceptions.ConnectionClosed:
        print("send_commercial_state_change failed")

async def send_status(ws, display, debug):
    global PLUGIN_PROTOCOL_VERSION

    try:
        await ws.send(json.dumps({
            "type": "status",
            "timestamp": time.time(),
            "data": {},
            "meta": {
                "display": display,
                "debug": debug
            }
        }))

    except websockets.exceptions.ConnectionClosed:
        pass

async def send_manifest(ws):
    global camera_options
    global default_camera

    # only get list of cameras if not already running and if it is, only set it if it isn't already cached
    if not camera_task:
        camera_options = get_available_cameras()
    elif not camera_options:
        camera_options = [{"label": "Camera 0", "value": "0"}]

    if not default_camera:
        default_camera = camera_options[-1]["value"]

    gesture_options = [
        {"label": config["label"], "value": gesture_name}
        for gesture_name, config in GESTURE_OPTIONS.items()
    ]

    try:
        await ws.send(json.dumps({
            "type": "plugin_manifest",
            "timestamp": time.time(),
            "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
            "data": {
                "name": PLUGIN_NAME,
                "id": PLUGIN_ID,
                "version": PLUGIN_VERSION,
                "description": (
                    "Use configurable MediaPipe hand gestures to switch "
                    "between commercial and content states."
                ),
                "primaryColor": "#12384d",
                "secondaryColor": "#dadcdc",
                "capabilities": ["detection"],
                "preferences": [
                    {
                        "key": "cameraIndex",
                        "label": "Camera",
                        "description": "Camera used for gesture recognition.",
                        "type": "select",
                        "options": camera_options,
                        "default": default_camera,
                    },
                    {
                        "key": "commercialGesture",
                        "label": "Commercial Gesture",
                        "description": (
                            "Gesture that changes the stream state to commercial."
                        ),
                        "type": "select",
                        "options": gesture_options,
                        "default": "Thumb_Down",
                    },
                    {
                        "key": "commercialGestureCount",
                        "label": "Commercial Gesture Count",
                        "description": (
                            "Number of matching hands required to trigger commercial (1-5)."
                        ),
                        "type": "number",
                        "default": 2,
                        "min": 1,
                        "max": 4,
                    },
                    {
                        "key": "contentGesture",
                        "label": "Content Gesture",
                        "description": (
                            "Gesture that changes the stream state back to content."
                        ),
                        "type": "select",
                        "options": gesture_options,
                        "default": "Thumb_Up",
                    },
                    {
                        "key": "contentGestureCount",
                        "label": "Content Gesture Count",
                        "description": (
                            "Number of matching hands required to trigger content (1-5)."
                        ),
                        "type": "number",
                        "default": 2,
                        "min": 1,
                        "max": 4,
                    },
                    {
                        "key": "totalHandsProcessed",
                        "label": "Total Hands Processed",
                        "description": (
                            "Total number of hands the model will recognize at a time (Recommended use less if can. Use more for crowded room.)."
                        ),
                        "type": "number",
                        "default": 4,
                    },
                    {
                        "key": "mirrorCamera",
                        "label": "Mirror Camera",
                        "description": (
                            "Flip the camera horizontally like a selfie preview."
                        ),
                        "type": "checkbox",
                        "default": True,
                    },
                    {
                        "key": "minimumGestureConfidence",
                        "label": "Minimum Gesture Confidence",
                        "description": (
                            "Ignore recognized gestures below this confidence, "
                            "from 0.0 to 1.0."
                        ),
                        "type": "number",
                        "default": 0.5,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.05,
                    },
                    {
                        "key": "cooldownSeconds",
                        "label": "Trigger Cooldown (Seconds)",
                        "description": (
                            "Minimum delay before the same gesture group can "
                            "trigger again."
                        ),
                        "type": "number",
                        "default": 1.0,
                        "min": 0.0,
                        "max": 10.0,
                        "step": 0.1,
                    },
                ],
            },
            "meta": {
                "display": "Sending Manifest",
                "debug": "Sending Manifest",
            },
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_manifest stopped: client disconnected")

# --------------------------------------------------
# Main
# --------------------------------------------------

async def main():
    async with websockets.serve(
        handle_client,
        "localhost",
        PORT
    ):
        print(f"Server running on ws://localhost:{PORT}")
        await asyncio.Future()

asyncio.run(main())