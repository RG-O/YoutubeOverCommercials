import asyncio
import websockets
import json
import time
import os
import cv2
import base64

from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import mediapipe as mp

# --------------------------------------------------
# Configuration
# --------------------------------------------------

PORT = 64145

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "gesture_recognizer.task")

is_debug_mode = False
CAMERA_INDEX = 0

REQUIRED_GESTURE_COUNTS = {
    "Thumb_Up": 2,
    "Thumb_Down": 2
}

TARGET_GESTURES = {
    "Thumb_Up": {
        "action": "content",
        "emoji": "\uD83D\uDC4D"
    },
    "Thumb_Down": {
        "action": "commercial",
        "emoji": "\uD83D\uDC4E"
    }
}

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

current_is_commercial = None
last_status_display = None

gesture_group_states = {}

any_trigger_display_until = time.time()

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
    try:
        if not os.path.exists(MODEL_PATH):
            print("Model not found:", MODEL_PATH)
            return

        print("Loading MediaPipe model...")

        base_options = python.BaseOptions(
            model_asset_path=MODEL_PATH
        )

        options = vision.GestureRecognizerOptions(
            base_options=base_options,
            num_hands=4
        )

        recognizer = vision.GestureRecognizer.create_from_options(options)

        cap = cv2.VideoCapture(CAMERA_INDEX)

        if not cap.isOpened():
            print("Failed to open webcam")
            return

        print("Camera started")

        await send_expected_resting_status(ws, "Ready")

        while True:
            await camera_active.wait()

            success, frame = cap.read()

            if not success:
                await asyncio.sleep(0.01)
                continue

            frame = cv2.flip(frame, 1)

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

        cap.release()
        cv2.destroyAllWindows()

    except asyncio.CancelledError:
        print("camera_loop shutting down")
        raise

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
        clients.remove(websocket)

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
        is_debug_mode = msg["data"]["preferences"]["isDebugMode"]
        
        current_is_commercial = (
            msg.get("data", {})
            .get("isCommercialState")
        )

        last_status_display = None

        await send_status(
            ws,
            "Starting up...",
            "Starting up..."
        )

        camera_active.set()

        if not camera_task:
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
    try:
        await ws.send(json.dumps({
            "type": "plugin_manifest",
            "timestamp": time.time(),
            "data": {
                "name": "Thumbs Down Commercials",
                "id": "my-trigger-plugin-ws", # Must be unique
                "version": "1.0.0",
                "description": "My trigger plugin description.", # Optional
                "primaryColor": "#12384d", # Optional
                "secondaryColor": "#dadcdc", # Optional
                "capabilities": ["detection"], #TODO: delete this?
            },
            "meta": {
                "display": "Sending Manifest",
                "debug": "Sending Manifest",
            },
        }))
    except websockets.exceptions.ConnectionClosed:
        print("send_status send stopped: client disconnected")

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