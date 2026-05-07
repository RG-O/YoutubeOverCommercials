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

from PIL import Image
import io

# --------------------------------------------------
# Configuration
# --------------------------------------------------

PORT = 64145

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "gesture_recognizer.task")

# Enable webcam preview window and screenshot sending
DEBUG_MODE = True

# Camera index
CAMERA_INDEX = 0

# Number of matching gestures required simultaneously
# Example:
#   1 = one thumbs up triggers
#   2 = two thumbs ups required to trigger
REQUIRED_GESTURE_COUNTS = {
    "Thumb_Up": 1,
    "Thumb_Down": 1
}

# Gesture config
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

# Confidence and duration thresholds
# (confidence, required duration seconds)
THRESHOLDS = [
    (0.95, 0.5),
    (0.80, 1.0),
    (0.55, 1.5),
]

VISIBILITY_THRESHOLD = 0.50
COOLDOWN = 1.0

# --------------------------------------------------
# Global state
# --------------------------------------------------

clients = set()

camera_task = None
camera_active = asyncio.Event()

current_is_commercial = None

# Tracks gesture timing/group state
gesture_group_states = {}

# --------------------------------------------------
# Helpers
# --------------------------------------------------

def get_all_emojis_for_action(action):
    return " ".join(
        config["emoji"]
        for config in TARGET_GESTURES.values()
        if config.get("action") == action
    )

def find_gesture_config(gesture_name):
    return TARGET_GESTURES.get(gesture_name)

def passes_threshold(confidence, duration):
    for min_confidence, min_duration in THRESHOLDS:
        if confidence >= min_confidence and duration >= min_duration:
            return True
    return False

def frame_to_base64(frame):
    # frame_copy = frame.copy()
    # success, buffer = cv2.imencode(".jpg", frame_copy)

    success, buffer = cv2.imencode(".jpg", frame)

    # debug_path = os.path.join(BASE_DIR, "debug_original.jpg")

    # cv2.imwrite(debug_path, frame)

    # print(debug_path)

    # frame_copy = frame.copy()

    # debug_copy_path = os.path.join(BASE_DIR, "debug_copy.jpg")

    # cv2.imwrite(debug_copy_path, frame_copy)

    # if frame is None:
    #     print("ERROR: frame is None")

    # print(frame.shape)

    if not success:
        return None


    #image = Image.open(io.BytesIO(buffer))
    # encodingbuffer = io.BytesIO()
    # image.save(encodingbuffer, format="JPEG")
    # base64_data = base64.b64encode(encodingbuffer.getvalue()).decode('utf-8')

    base64_data = base64.b64encode(buffer.tobytes()).decode("utf-8")
    print(base64_data)

    return f"data:image/jpeg;base64,{base64_data}"
    #return "data:image/jpg;base64," + base64.b64encode(buffer.getvalue()).decode()

# --------------------------------------------------
# Trigger handling
# --------------------------------------------------

async def handle_trigger(
    ws,
    gesture_name,
    config,
    confidence,
    duration,
    frame
):
    global current_is_commercial

    new_is_commercial = config["action"] == "commercial"

    # Ignore if already in desired state
    if (
        current_is_commercial is not None and
        current_is_commercial == new_is_commercial
    ):
        print(
            f"IGNORED: {gesture_name} "
            f"(already in desired state)"
        )
        return

    print(
        f"TRIGGERED: {gesture_name} | "
        f"confidence={confidence:.2f} | "
        f"duration={duration:.2f}s"
    )

    current_is_commercial = new_is_commercial

    display = f"\u270B {config['emoji']}"

    debug_text = f"{gesture_name} detected"

    if DEBUG_MODE:
        debug_text = frame_to_base64(frame)

        # raw_base64 = debug_text.split(",", 1)[1]

        # decoded = base64.b64decode(raw_base64)

        # with open("test.jpg", "wb") as f:
        #     f.write(decoded)

    await send_commercial_state_change(
        ws,
        new_is_commercial,
        display,
        debug_text,
    )

# --------------------------------------------------
# Gesture processing
# --------------------------------------------------

async def process_gesture_group(
    ws,
    gesture_name,
    hands,
    now,
    frame
):
    """
    Handles:
    - simultaneous hand requirements
    - timing
    - confidence thresholds
    """

    config = find_gesture_config(gesture_name)

    if not config:
        return

    required_count = REQUIRED_GESTURE_COUNTS.get(
        gesture_name,
        1
    )

    matching_hands = []

    for hand in hands:
        if hand["gesture_name"] != gesture_name:
            continue

        if hand["confidence"] < VISIBILITY_THRESHOLD:
            continue

        matching_hands.append(hand)

    current_count = len(matching_hands)

    # Not enough simultaneous gestures
    if current_count < required_count:

        if gesture_name in gesture_group_states:
            state = gesture_group_states[gesture_name]

            if state["visible"]:
                state["visible"] = False

                print(
                    f"HIDDEN GROUP: {gesture_name} "
                    f"count={current_count}"
                )

        return

    # Average confidence across matching hands
    avg_confidence = (
        sum(h["confidence"] for h in matching_hands)
        / current_count
    )

    # Create group state if missing
    if gesture_name not in gesture_group_states:
        gesture_group_states[gesture_name] = {
            "start_time": now,
            "triggered": False,
            "visible": False,
            "last_trigger_time": 0
        }

    state = gesture_group_states[gesture_name]

    # Visibility logging
    if not state["visible"]:
        state["visible"] = True

        print(
            f"VISIBLE GROUP: {gesture_name} "
            f"count={current_count} "
            f"confidence={avg_confidence:.2f}"
        )

    duration = now - state["start_time"]

    # Already triggered
    if state["triggered"]:
        return

    # Cooldown
    if now - state["last_trigger_time"] < COOLDOWN:
        return

    # Threshold passed
    if passes_threshold(avg_confidence, duration):

        await handle_trigger(
            ws,
            gesture_name,
            config,
            avg_confidence,
            duration,
            frame
        )

        state["triggered"] = True
        state["last_trigger_time"] = now

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

        recognizer = (
            vision.GestureRecognizer
            .create_from_options(options)
        )

        cap = cv2.VideoCapture(CAMERA_INDEX)

        if not cap.isOpened():
            print("Failed to open webcam")
            return

        print("Camera started")

        await send_status(
            ws,
            "\u270B " +
            get_all_emojis_for_action("commercial"),
            "Ready"
        )

        while True:

            await camera_active.wait()

            success, frame = cap.read()

            if not success:
                await asyncio.sleep(0.01)
                continue

            # Mirror webcam
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

            # --------------------------------------------------
            # Parse hands
            # --------------------------------------------------

            if result.gestures:

                for hand_index, gesture_list in enumerate(result.gestures):

                    if not gesture_list:
                        continue

                    top_gesture = gesture_list[0]

                    gesture_name = top_gesture.category_name
                    confidence = top_gesture.score

                    # Get landmarks for drawing
                    landmarks = result.hand_landmarks[hand_index]

                    xs = [lm.x for lm in landmarks]
                    ys = [lm.y for lm in landmarks]

                    h, w, _ = frame.shape

                    x1 = int(min(xs) * w)
                    y1 = int(min(ys) * h)

                    x2 = int(max(xs) * w)
                    y2 = int(max(ys) * h)

                    # Draw debug rectangle
                    if DEBUG_MODE:
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
                            (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 255, 0),
                            2
                        )

                    detected_hands.append({
                        "gesture_name": gesture_name,
                        "confidence": confidence
                    })

            # --------------------------------------------------
            # Process gesture groups
            # --------------------------------------------------

            for gesture_name in TARGET_GESTURES.keys():

                await process_gesture_group(
                    ws,
                    gesture_name,
                    detected_hands,
                    now,
                    frame
                )

            # --------------------------------------------------
            # Debug webcam preview
            # --------------------------------------------------

            if DEBUG_MODE:
                cv2.imshow(
                    "MediaPipe Gesture Debug",
                    frame
                )

                # ESC closes window
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

    message_type = msg["type"]

    # --------------------------------------------------
    # Init
    # --------------------------------------------------

    if message_type == "init":

        current_is_commercial = (
            msg.get("data", {})
            .get("isCommercialState")
        )

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

    # --------------------------------------------------
    # Commercial state updates
    # --------------------------------------------------

    elif message_type == "commercial_state_change":

        current_is_commercial = (
            msg["data"]["isCommercialState"]
        )

        display = (
            "\u270B " +
            get_all_emojis_for_action("commercial")
        )

        if current_is_commercial:
            display = (
                "\u270B " +
                get_all_emojis_for_action("content")
            )

        await send_status(
            ws,
            display,
            "update display"
        )

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

async def send_status(
    ws,
    display,
    debug
):
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