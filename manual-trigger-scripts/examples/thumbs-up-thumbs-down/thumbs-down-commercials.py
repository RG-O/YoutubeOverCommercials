import asyncio
import websockets
import json
import time
import cv2
import mediapipe as mp
import os
from collections import deque

# --------------------------------------------------
# Configuration
# --------------------------------------------------

# Confidence and duration thresholds for triggering an event.
# Higher confidence requires less time.
THRESHOLDS = [
    (0.95, 0.5),
    (0.80, 1.0),
    (0.60, 2.0),
]

# Time (in seconds) after losing a gesture before resetting its state
RESET_TIMEOUT = 0.3

# Number of recent frames used to smooth confidence values
SMOOTHING_WINDOW = 5

# Gestures we care about
TARGET_GESTURES = ["Thumb_Up", "Thumb_Down"]

# --------------------------------------------------
# Model path (location independent)
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
model_path = os.path.join(BASE_DIR, "gesture_recognizer.task")

# --------------------------------------------------
# MediaPipe setup
# --------------------------------------------------

BaseOptions = mp.tasks.BaseOptions
GestureRecognizer = mp.tasks.vision.GestureRecognizer
GestureRecognizerOptions = mp.tasks.vision.GestureRecognizerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

# num_hands increased to allow multiple hands to be detected
options = GestureRecognizerOptions(
    base_options=BaseOptions(model_asset_path=model_path),
    running_mode=VisionRunningMode.VIDEO,
    num_hands=4
)

recognizer = GestureRecognizer.create_from_options(options)

# --------------------------------------------------
# WebSocket server
# --------------------------------------------------

connected_clients = set()

async def handler(websocket):
    connected_clients.add(websocket)
    print("Extension connected")
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.remove(websocket)
        print("Extension disconnected")

async def send_event(event):
    if connected_clients:
        message = json.dumps(event)
        await asyncio.gather(*(ws.send(message) for ws in connected_clients))

# --------------------------------------------------
# Per-hand gesture tracking
# --------------------------------------------------

# Each hand gets its own tracking state.
# Since MediaPipe does not give a persistent ID per hand,
# we approximate using the index of the detected hand.

gesture_states = {}
confidence_buffers = {}
above_50_flags = {}

def create_empty_state():
    return {
        "current": None,
        "start_time": None,
        "last_seen": None,
        "triggered": False
    }

# --------------------------------------------------
# Main loop
# --------------------------------------------------

async def main():
    global gesture_states, confidence_buffers, above_50_flags

    server = await websockets.serve(handler, "localhost", 8765)
    print("WebSocket server running on ws://localhost:8765")

    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    print("Starting gesture detection (press q to quit)")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        now = time.time()

        # Convert frame to MediaPipe format
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        timestamp_ms = int(now * 1000)

        result = recognizer.recognize_for_video(mp_image, timestamp_ms)

        # Keep track of which hand indices are active this frame
        active_indices = set()

        if result.gestures:
            for i, hand_gestures in enumerate(result.gestures):
                if not hand_gestures:
                    continue

                top = hand_gestures[0]
                name = top.category_name
                confidence = top.score

                # Initialize structures for this hand index if needed
                if i not in gesture_states:
                    gesture_states[i] = create_empty_state()
                    confidence_buffers[i] = deque(maxlen=SMOOTHING_WINDOW)
                    above_50_flags[i] = False

                state = gesture_states[i]
                buffer = confidence_buffers[i]

                active_indices.add(i)

                # Only process gestures we care about
                if name in TARGET_GESTURES:
                    buffer.append(confidence)
                    smoothed_conf = sum(buffer) / len(buffer)

                    # ------------------------------------------
                    # 50 percent threshold logging
                    # ------------------------------------------

                    if smoothed_conf >= 0.5 and not above_50_flags[i]:
                        print(f"Hand {i}: {name} rose above 50 percent ({smoothed_conf:.2f})")
                        above_50_flags[i] = True

                    elif smoothed_conf < 0.5 and above_50_flags[i]:
                        print(f"Hand {i}: {name} fell below 50 percent ({smoothed_conf:.2f})")
                        above_50_flags[i] = False

                    # ------------------------------------------
                    # Gesture state tracking
                    # ------------------------------------------

                    if state["current"] != name:
                        # New gesture detected for this hand
                        state["current"] = name
                        state["start_time"] = now
                        state["triggered"] = False

                    state["last_seen"] = now

                    duration = now - state["start_time"]

                    # ------------------------------------------
                    # Threshold based triggering
                    # ------------------------------------------

                    trigger = False
                    for min_conf, min_time in THRESHOLDS:
                        if smoothed_conf >= min_conf and duration >= min_time:
                            trigger = True
                            break

                    if trigger and not state["triggered"]:
                        print(f"TRIGGERED: Hand {i} {name} (conf={smoothed_conf:.2f}, time={duration:.2f}s)")

                        await send_event({
                            "type": "gesture",
                            "gesture": name,
                            "confidence": smoothed_conf,
                            "duration": duration,
                            "hand_index": i,
                            "timestamp": now
                        })

                        state["triggered"] = True

        # ------------------------------------------
        # Handle hands that disappeared
        # ------------------------------------------

        for i in list(gesture_states.keys()):
            if i not in active_indices:
                state = gesture_states[i]

                if state["last_seen"] and (now - state["last_seen"] > RESET_TIMEOUT):

                    # If a gesture had triggered, send an end event
                    if state["current"] and state["triggered"]:
                        await send_event({
                            "type": "gesture_end",
                            "gesture": state["current"],
                            "hand_index": i,
                            "timestamp": now
                        })

                    # Reset all tracking for this hand
                    gesture_states[i] = create_empty_state()
                    confidence_buffers[i].clear()
                    above_50_flags[i] = False

        # Show webcam feed
        cv2.imshow("Gesture Recognition", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        # Allow async tasks to run
        await asyncio.sleep(0)

    # Cleanup resources
    cap.release()
    cv2.destroyAllWindows()
    server.close()
    await server.wait_closed()

# --------------------------------------------------
# Entry point
# --------------------------------------------------

if __name__ == "__main__":
    asyncio.run(main())