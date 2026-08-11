import asyncio
import json
import time
from collections import deque

import ollama
import websockets

PLUGIN_PROTOCOL_VERSION = 1  # DO NOT TOUCH

PLUGIN_NAME = "AI Commercial Detector"
PLUGIN_ID = "ai-commercial-detector-ws"  # Must be unique
PLUGIN_VERSION = "1.2.0"

PORT = 64145

# Ollama settings.
# Install the Python package with: pip install ollama
# Make sure the Ollama desktop/service is running and this vision model is installed.
#OLLAMA_MODEL = "gemma3:4b"
OLLAMA_MODEL = "qwen2.5vl:7b"
OLLAMA_HOST = "http://127.0.0.1:11434"

# Default plugin preference values.
DEFAULT_LLM_CALL_FREQUENCY_SECONDS = 0
DEFAULT_CONSECUTIVE_YES_REQUIRED = 1
DEFAULT_DEBUG_MODE = False
DEFAULT_SCREENSHOT_BATCH_SIZE = 3
DEFAULT_SCREENSHOT_FREQUENCY_MILLISECONDS = 1500
DEFAULT_SCREENSHOT_MAX_WIDTH = 500
DEFAULT_SCREENSHOT_MAX_HEIGHT = 300

clients = set()

# One shared async Ollama client is enough for this plugin.
ollama_client = ollama.AsyncClient(host=OLLAMA_HOST)

# Per-WebSocket client state.
client_screenshot_buffers = {}
client_commercial_states = {}
client_llm_call_frequency_seconds = {}
client_consecutive_yes_required = {}
client_debug_modes = {}
client_screenshot_batch_sizes = {}
client_screenshot_frequency_milliseconds = {}
client_screenshot_max_widths = {}
client_screenshot_max_heights = {}
client_consecutive_yes_counts = {}
client_last_llm_call_times = {}
client_analysis_tasks = {}
client_screenshot_versions = {}
client_last_analyzed_screenshot_versions = {}


async def handle_client(websocket):
    print("Client connected")
    clients.add(websocket)

    client_screenshot_buffers[websocket] = deque(maxlen=DEFAULT_SCREENSHOT_BATCH_SIZE)
    client_commercial_states[websocket] = False
    client_llm_call_frequency_seconds[websocket] = DEFAULT_LLM_CALL_FREQUENCY_SECONDS
    client_consecutive_yes_required[websocket] = DEFAULT_CONSECUTIVE_YES_REQUIRED
    client_debug_modes[websocket] = DEFAULT_DEBUG_MODE
    client_screenshot_batch_sizes[websocket] = DEFAULT_SCREENSHOT_BATCH_SIZE
    client_screenshot_frequency_milliseconds[websocket] = DEFAULT_SCREENSHOT_FREQUENCY_MILLISECONDS
    client_screenshot_max_widths[websocket] = DEFAULT_SCREENSHOT_MAX_WIDTH
    client_screenshot_max_heights[websocket] = DEFAULT_SCREENSHOT_MAX_HEIGHT
    client_consecutive_yes_counts[websocket] = 0
    client_last_llm_call_times[websocket] = 0.0
    client_analysis_tasks[websocket] = None
    client_screenshot_versions[websocket] = 0
    client_last_analyzed_screenshot_versions[websocket] = -1

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                await handle_screenshot(websocket, message)
            else:
                msg = json.loads(message)
                await handle_message(websocket, msg)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        analysis_task = client_analysis_tasks.get(websocket)
        if analysis_task and not analysis_task.done():
            analysis_task.cancel()

        clients.discard(websocket)
        client_screenshot_buffers.pop(websocket, None)
        client_commercial_states.pop(websocket, None)
        client_llm_call_frequency_seconds.pop(websocket, None)
        client_consecutive_yes_required.pop(websocket, None)
        client_debug_modes.pop(websocket, None)
        client_screenshot_batch_sizes.pop(websocket, None)
        client_screenshot_frequency_milliseconds.pop(websocket, None)
        client_screenshot_max_widths.pop(websocket, None)
        client_screenshot_max_heights.pop(websocket, None)
        client_consecutive_yes_counts.pop(websocket, None)
        client_last_llm_call_times.pop(websocket, None)
        client_analysis_tasks.pop(websocket, None)
        client_screenshot_versions.pop(websocket, None)
        client_last_analyzed_screenshot_versions.pop(websocket, None)

        print("Client disconnected")


async def handle_message(ws, msg):
    message_type = msg["type"]
    data = msg.get("data", {})
    preferences = data.get("preferences", {})
    custom_trigger_plugin_preferences = (
        preferences.get("pluginTriggerPreferences", {}).get("preferences", {})
    )

    if message_type == "plugin_manifest":
        print("Plugin Manifest Requested. Sending Manifest.")
        await send_manifest(ws)

    elif message_type == "init":
        print("Extension initiated")
        print("Full preferences:")
        print(preferences)
        print("Your custom requested plugin preferences:")
        print(custom_trigger_plugin_preferences)

        llm_frequency = get_float_preference(
            custom_trigger_plugin_preferences,
            "llm-call-frequency-seconds",
            DEFAULT_LLM_CALL_FREQUENCY_SECONDS,
            minimum=0,
        )
        consecutive_yes_required = get_int_preference(
            custom_trigger_plugin_preferences,
            "consecutive-yes-required",
            DEFAULT_CONSECUTIVE_YES_REQUIRED,
            minimum=1,
        )
        debug_mode = get_bool_preference(
            custom_trigger_plugin_preferences,
            "debug-mode",
            DEFAULT_DEBUG_MODE,
        )
        screenshot_batch_size = get_int_preference(
            custom_trigger_plugin_preferences,
            "screenshot-batch-size",
            DEFAULT_SCREENSHOT_BATCH_SIZE,
            minimum=1,
        )
        screenshot_frequency_milliseconds = get_int_preference(
            custom_trigger_plugin_preferences,
            "screenshot-frequency-milliseconds",
            DEFAULT_SCREENSHOT_FREQUENCY_MILLISECONDS,
            minimum=1,
        )
        screenshot_max_width = get_int_preference(
            custom_trigger_plugin_preferences,
            "screenshot-max-width",
            DEFAULT_SCREENSHOT_MAX_WIDTH,
            minimum=1,
        )
        screenshot_max_height = get_int_preference(
            custom_trigger_plugin_preferences,
            "screenshot-max-height",
            DEFAULT_SCREENSHOT_MAX_HEIGHT,
            minimum=1,
        )

        client_llm_call_frequency_seconds[ws] = llm_frequency
        client_consecutive_yes_required[ws] = consecutive_yes_required
        client_debug_modes[ws] = debug_mode
        client_screenshot_batch_sizes[ws] = screenshot_batch_size
        client_screenshot_frequency_milliseconds[ws] = screenshot_frequency_milliseconds
        client_screenshot_max_widths[ws] = screenshot_max_width
        client_screenshot_max_heights[ws] = screenshot_max_height

        # Rebuild the rolling buffer using the user's selected batch size.
        client_screenshot_buffers[ws] = deque(maxlen=screenshot_batch_size)
        client_consecutive_yes_counts[ws] = 0
        client_last_llm_call_times[ws] = 0.0
        client_screenshot_versions[ws] = 0
        client_last_analyzed_screenshot_versions[ws] = -1

        # If the init message provides the current commercial state, use it.
        if "isCommercialState" in data:
            client_commercial_states[ws] = bool(data["isCommercialState"])

        print(f"LLM call frequency: every {llm_frequency:g} second(s) minimum")
        print(f"Consecutive YES responses required: {consecutive_yes_required}")
        print(f"Debug mode: {debug_mode}")
        print(f"Screenshot batch size: {screenshot_batch_size}")
        print(f"Screenshot frequency: {screenshot_frequency_milliseconds} ms")
        print(f"Screenshot max dimensions: {screenshot_max_width}x{screenshot_max_height}")

        await send_status(
            ws,
            "Initializing local AI model...",
            (
                f"{PLUGIN_NAME} ready. LLM frequency={llm_frequency:g}s, "
                f"consecutive YES required={consecutive_yes_required}, "
                f"debug mode={debug_mode}, batch size={screenshot_batch_size}, "
                f"screenshot frequency={screenshot_frequency_milliseconds}ms, "
                f"max dimensions={screenshot_max_width}x{screenshot_max_height}"
            ),
        )

        print("Requesting extension starts sending screenshots")
        await request_screenshots(ws)

    elif message_type == "commercial_state_change":
        is_commercial = bool(data["isCommercialState"])
        commercial_state_trigger = data["utilities"][
            "triggerOfLastCommercialStateChange"
        ]

        # Always synchronize our state with the extension. This matters when
        # another trigger changes the commercial state.
        old_state = client_commercial_states.get(ws, False)
        client_commercial_states[ws] = is_commercial

        # Any confirmed state change starts a fresh YES streak.
        if old_state != is_commercial:
            client_consecutive_yes_counts[ws] = 0

        print(
            "Commercial state confirmed by extension. "
            f"is_commercial={is_commercial}, "
            f"commercial_state_trigger={commercial_state_trigger}"
        )

    elif message_type == "browser_fullscreen_state_change":
        is_fullscreen = data["isFullscreen"]
        print(f"Fullscreen state changed on browser. is_fullscreen={is_fullscreen}")


def get_float_preference(preferences, key, default, minimum=None):
    """Read a numeric preference safely and fall back to its default."""
    try:
        value = float(preferences.get(key, default))
    except (TypeError, ValueError):
        value = default

    if minimum is not None:
        value = max(minimum, value)

    return value


def get_int_preference(preferences, key, default, minimum=None):
    """Read an integer preference safely and fall back to its default."""
    try:
        value = int(float(preferences.get(key, default)))
    except (TypeError, ValueError):
        value = default

    if minimum is not None:
        value = max(minimum, value)

    return value


def get_bool_preference(preferences, key, default):
    """Read a checkbox/boolean preference safely."""
    value = preferences.get(key, default)

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")

    return bool(value)


async def handle_screenshot(ws, screenshot_bytes):
    print(f"Received screenshot as JPEG: {len(screenshot_bytes)} bytes")

    screenshot_buffer = client_screenshot_buffers.get(ws)
    if screenshot_buffer is None:
        return

    screenshot_buffer.append(screenshot_bytes)
    client_screenshot_versions[ws] = client_screenshot_versions.get(ws, 0) + 1

    batch_size = client_screenshot_batch_sizes.get(ws, DEFAULT_SCREENSHOT_BATCH_SIZE)
    print(f"Screenshot buffer: {len(screenshot_buffer)}/{batch_size}")

    # We cannot analyze until the first full rolling batch exists.
    if len(screenshot_buffer) < batch_size:
        return

    await maybe_start_analysis(ws)


async def maybe_start_analysis(ws):
    screenshot_buffer = client_screenshot_buffers.get(ws)
    if screenshot_buffer is None:
        return

    batch_size = client_screenshot_batch_sizes.get(ws, DEFAULT_SCREENSHOT_BATCH_SIZE)
    if len(screenshot_buffer) < batch_size:
        return

    # Never allow more than one Ollama request at a time for this client.
    existing_task = client_analysis_tasks.get(ws)
    if existing_task and not existing_task.done():
        return

    # Require at least one newly received screenshot since the previous LLM
    # analysis started. This prevents frequency=0 from re-analyzing the exact
    # same batch repeatedly.
    screenshot_version = client_screenshot_versions.get(ws, 0)
    last_analyzed_version = client_last_analyzed_screenshot_versions.get(ws, -1)
    if screenshot_version <= last_analyzed_version:
        return

    # Respect the user's configured minimum time between the START of calls.
    now = time.monotonic()
    last_call_time = client_last_llm_call_times.get(ws, 0.0)
    call_frequency = client_llm_call_frequency_seconds.get(
        ws,
        DEFAULT_LLM_CALL_FREQUENCY_SECONDS,
    )

    if now - last_call_time < call_frequency:
        return

    screenshots = list(screenshot_buffer)
    state_at_start = client_commercial_states.get(ws, False)

    client_last_llm_call_times[ws] = now
    client_last_analyzed_screenshot_versions[ws] = screenshot_version
    client_analysis_tasks[ws] = asyncio.create_task(
        analyze_screenshot_batch(ws, screenshots, state_at_start)
    )


async def analyze_screenshot_batch(ws, screenshots, state_at_start):
    try:
        print(
            f"Sending {len(screenshots)} screenshots to Ollama. "
            f"Current commercial state={state_at_start}"
        )

        debug_mode = client_debug_modes.get(ws, DEFAULT_DEBUG_MODE)
        transition_detected, llm_response = await ask_ollama_about_transition(
            screenshots,
            state_at_start,
            debug_mode,
        )

        print(f"Ollama response: {llm_response!r}")

        # The commercial state may have changed while Ollama was thinking. If
        # so, this answer was produced for an outdated question and is ignored.
        current_state = client_commercial_states.get(ws, False)
        if current_state != state_at_start:
            print("Ignoring Ollama response because commercial state changed during analysis")
            client_consecutive_yes_counts[ws] = 0
            return

        if transition_detected:
            client_consecutive_yes_counts[ws] = (
                client_consecutive_yes_counts.get(ws, 0) + 1
            )
        else:
            # A NO breaks the streak. The requested confirmations must be
            # consecutive YES responses.
            client_consecutive_yes_counts[ws] = 0

        yes_count = client_consecutive_yes_counts[ws]
        yes_required = client_consecutive_yes_required.get(
            ws,
            DEFAULT_CONSECUTIVE_YES_REQUIRED,
        )

        answer_text = "YES" if transition_detected else "NO"
        print(
            f"Transition answer={answer_text}; "
            f"consecutive YES count={yes_count}/{yes_required}"
        )

        # In debug mode, surface every decision that has not yet triggered a
        # state change. The full LLM response is placed in meta.debug.
        if yes_count < yes_required:
            if debug_mode:
                await send_status(
                    ws,
                    f"AI decision: {answer_text} ({yes_count}/{yes_required} YES)",
                    llm_response,
                )
            return

        # Enough consecutive YES responses were received. A YES means the
        # desired transition depends on our current state:
        #   normal program -> commercial
        #   commercial     -> normal program
        new_commercial_state = not state_at_start

        # Update immediately so another completed analysis cannot send the same
        # change again before the extension echoes the confirmed state back.
        client_commercial_states[ws] = new_commercial_state
        client_consecutive_yes_counts[ws] = 0

        if new_commercial_state:
            display = "AI detected commercial break"
        else:
            display = "AI detected return to programming"

        # In debug mode, pass Ollama's full YES/NO + reason response through.
        # Outside debug mode, keep the debug value concise.
        if debug_mode:
            debug = llm_response
        else:
            debug = (
                f"Ollama returned YES {yes_required} time(s) in a row. "
                f"New commercial state={new_commercial_state}"
            )

        print(f"Sending commercial state change: {new_commercial_state}")
        await send_commercial_state_change(
            ws,
            new_commercial_state,
            display,
            debug,
        )

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(f"Ollama analysis failed: {exc}")

        if ws in clients:
            await send_status(
                ws,
                "AI commercial detection error",
                f"Ollama analysis failed: {exc}",
            )
    finally:
        # Only clear the slot if this is still the registered analysis task.
        current_task = asyncio.current_task()
        if client_analysis_tasks.get(ws) is current_task:
            client_analysis_tasks[ws] = None

        # Important for frequency=0: if at least one screenshot arrived while
        # Ollama was working, immediately check whether another analysis can be
        # started using the newest rolling batch.
        if ws in clients:
            await maybe_start_analysis(ws)


async def ask_ollama_about_transition(screenshots, currently_commercial, debug_mode):
    if currently_commercial:
        # question = (
        #     f"You are examining {len(screenshots)} consecutive screenshots from a TV broadcast. "
        #     "They are ordered from oldest to newest. The broadcast is currently "
        #     "considered to be in a commercial break. Determine whether these "
        #     "screenshots indicate that the commercial break has ended OR is "
        #     "transitioning back into the normal program. Consider the sequence "
        #     "across all images, not just one image. Do not say YES merely "
        #     "because one advertisement changes to another advertisement. "
        # )
        question = (
            f"You are examining {len(screenshots)} consecutive screenshots from a TV broadcast. "
            "Do all of "
            "these screenshots appear to NOT be part of a commercial "
            "and instead seem to be part of regular programming? "
            #"Small text promotions appearing within seemingly regular programming do not count as a commercial. " #TODO: get rid of this? add this last not after a minute or so of commercial?
        )
    else:
        # question = (
        #     f"You are examining {len(screenshots)} consecutive screenshots from a TV broadcast. "
        #     "They are ordered from oldest to newest. The broadcast is currently "
        #     "considered to be normal programming. Determine whether these "
        #     "screenshots indicate that the broadcast is now in a commercial "
        #     "break OR is transitioning into a commercial break. Consider the "
        #     "sequence across all images, not just one image. Normal program "
        #     "scene changes, sports replays, scoreboards, studio segments, and "
        #     "broadcast graphics should not by themselves be treated as a commercial. "
        # )
        question = (
            f"You are examining {len(screenshots)} consecutive screenshots from a TV broadcast. "
            "Determine if "
            "all these screenshots are showing advertisements and/or commercials. "
        )

    if debug_mode:
        question += (
            "Respond with YES or NO on the first line. On the second line, give "
            "one short reason for the decision. Keep the reason concise."
        )
    else:
        question += "Respond with exactly YES or NO and nothing else."

    response = await ollama_client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {
                "role": "user",
                "content": question,
                # Ollama's Python client accepts raw image bytes here, so the
                # JPEGs received from the browser do not need manual base64 work.
                "images": screenshots,
            }
        ],
        options={
            "temperature": 0,
        },
    )

    llm_response = response.message.content.strip()
    transition_detected = parse_yes_no_response(llm_response, debug_mode)

    return transition_detected, llm_response


def parse_yes_no_response(response, debug_mode=False):
    """Convert an Ollama response into a strict True/False decision."""
    if debug_mode:
        # Debug responses may contain a reason after the first line, but the
        # first non-empty line must still be an unambiguous YES or NO.
        first_line = next(
            (line.strip() for line in response.splitlines() if line.strip()),
            "",
        )
        cleaned = first_line.upper().strip(" .,!?:;\"'`\n\r\t")
    else:
        cleaned = response.strip().upper()
        cleaned = cleaned.strip(" .,!?:;\"'`\n\r\t")

    if cleaned == "YES":
        return True

    if cleaned == "NO":
        return False

    expected = "YES/NO on the first line" if debug_mode else "only YES or NO"
    raise ValueError(
        f"Expected Ollama to return {expected}, got: {response!r}"
    )


async def send_commercial_state_change(ws, is_commercial, display, debug):
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "commercial_state_change",
                    "timestamp": time.time(),
                    "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
                    "data": {
                        "isCommercial": is_commercial,
                    },
                    "meta": {
                        "display": display,
                        "debug": debug,
                    },
                }
            )
        )
    except websockets.exceptions.ConnectionClosed:
        print("send_commercial_state_change stopped: client disconnected")


# This can be used to disable or enable any auto commercial detection that the
# browser extension is doing.
async def send_auto_commercial_blocked_state_change(
    ws,
    is_auto_commercial_blocked,
    display,
    debug,
):
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "auto_commercial_blocked_state_change",
                    "timestamp": time.time(),
                    "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
                    "data": {
                        "isAutoCommercialBlocked": is_auto_commercial_blocked,
                    },
                    "meta": {
                        "display": display,
                        "debug": debug,
                    },
                }
            )
        )
    except websockets.exceptions.ConnectionClosed:
        print("send_auto_commercial_blocked_state_change stopped: client disconnected")


async def send_status(ws, display, debug):
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "status",
                    "timestamp": time.time(),
                    "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
                    "data": {},
                    "meta": {
                        "display": display,
                        "debug": debug,
                    },
                }
            )
        )
    except websockets.exceptions.ConnectionClosed:
        print("send_status stopped: client disconnected")


async def request_screenshots(ws):
    frequency_milliseconds = client_screenshot_frequency_milliseconds.get(
        ws,
        DEFAULT_SCREENSHOT_FREQUENCY_MILLISECONDS,
    )
    max_width = client_screenshot_max_widths.get(ws, DEFAULT_SCREENSHOT_MAX_WIDTH)
    max_height = client_screenshot_max_heights.get(ws, DEFAULT_SCREENSHOT_MAX_HEIGHT)

    try:
        await ws.send(
            json.dumps(
                {
                    "type": "request_screenshots",
                    "timestamp": time.time(),
                    "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
                    "data": {
                        "shouldSendScreenshots": True,
                        "frequencyMilliseconds": frequency_milliseconds,
                        "maxDimensionsPixels": {
                            "height": max_height,
                            "width": max_width,
                        },
                        "trimOptionsPercentages": {
                            "top": 0,
                            "right": 0,
                            "bottom": 0,
                            "left": 0,
                        },
                    },
                    "meta": {},
                }
            )
        )
    except websockets.exceptions.ConnectionClosed:
        print("request_screenshots stopped: client disconnected")


async def send_manifest(ws):
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "plugin_manifest",
                    "timestamp": time.time(),
                    "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
                    "data": {
                        "name": PLUGIN_NAME,
                        "id": PLUGIN_ID,
                        "version": PLUGIN_VERSION,
                        "description": (
                            "Uses Ollama and a rolling screenshot window to detect "
                            "TV commercial transitions."
                        ),
                        "primaryColor": "#12384d",
                        "secondaryColor": "#dadcdc",
                        "capabilities": [
                            "trigger",
                            "screenshots",
                        ],
                        "preferences": [
                            {
                                "key": "llm-call-frequency-seconds",
                                "label": "LLM Call Frequency (Seconds)",
                                "description": (
                                    "Minimum number of seconds between the start of "
                                    "Ollama analysis calls. Set to 0 to analyze again "
                                    "as soon as the previous call finishes and at least "
                                    "one new screenshot has arrived."
                                ),
                                "type": "number",
                                "default": DEFAULT_LLM_CALL_FREQUENCY_SECONDS,
                                "min": 0,
                            },
                            {
                                "key": "consecutive-yes-required",
                                "label": "Consecutive YES Responses Required",
                                "description": (
                                    "Number of YES answers Ollama must return in a row "
                                    "before changing the commercial state. Any NO "
                                    "resets the count to zero."
                                ),
                                "type": "number",
                                "default": DEFAULT_CONSECUTIVE_YES_REQUIRED,
                                "min": 1,
                            },
                            {
                                "key": "debug-mode",
                                "label": "Debug Mode",
                                "description": (
                                    "Ask Ollama for YES/NO plus a short reason. Before "
                                    "the required YES streak is reached, the full LLM "
                                    "response is sent through status debug messages. "
                                    "When a state changes, the full response is sent "
                                    "in the commercial state change debug value."
                                ),
                                "type": "checkbox",
                                "default": DEFAULT_DEBUG_MODE,
                            },
                            {
                                "key": "screenshot-batch-size",
                                "label": "Screenshot Batch Size",
                                "description": (
                                    "Number of rolling screenshots sent to Ollama for "
                                    "each analysis."
                                ),
                                "type": "number",
                                "default": DEFAULT_SCREENSHOT_BATCH_SIZE,
                                "min": 1,
                            },
                            {
                                "key": "screenshot-frequency-milliseconds",
                                "label": "Screenshot Frequency (Milliseconds)",
                                "description": (
                                    "How frequently the browser extension should capture "
                                    "and send a screenshot to this plugin."
                                ),
                                "type": "number",
                                "default": DEFAULT_SCREENSHOT_FREQUENCY_MILLISECONDS,
                                "min": 1,
                            },
                            {
                                "key": "screenshot-max-width",
                                "label": "Screenshot Max Width (Pixels)",
                                "description": (
                                    "Maximum screenshot width sent by the browser. The "
                                    "extension should preserve the screenshot aspect ratio."
                                ),
                                "type": "number",
                                "default": DEFAULT_SCREENSHOT_MAX_WIDTH,
                                "min": 1,
                            },
                            {
                                "key": "screenshot-max-height",
                                "label": "Screenshot Max Height (Pixels)",
                                "description": (
                                    "Maximum screenshot height sent by the browser. The "
                                    "extension should preserve the screenshot aspect ratio."
                                ),
                                "type": "number",
                                "default": DEFAULT_SCREENSHOT_MAX_HEIGHT,
                                "min": 1,
                            },
                            #TODO add prompts as preferences
                            #TODO separate commercial vs non commercial settings
                            #TODO grab downloaded models from ollama and add them as dropdown, default to qwen2.5vl:7b
                        ],
                    },
                    "meta": {
                        "display": "Sending Manifest",
                        "debug": "Sending Manifest",
                    },
                }
            )
        )
    except websockets.exceptions.ConnectionClosed:
        print("send_manifest stopped: client disconnected")


async def main():
    async with websockets.serve(handle_client, "localhost", PORT):
        print(f"Server running on ws://localhost:{PORT}")
        print(f"Ollama host: {OLLAMA_HOST}")
        print(f"Ollama model: {OLLAMA_MODEL}")
        await asyncio.Future()


asyncio.run(main())