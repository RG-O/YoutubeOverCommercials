import asyncio
import json
import subprocess
import time
from collections import deque

import ollama
import websockets

PLUGIN_PROTOCOL_VERSION = 1  # DO NOT TOUCH

PLUGIN_NAME = "AI Commercial Detector"
PLUGIN_ID = "ai-commercial-detector-ws"  # Must be unique
PLUGIN_VERSION = "1.5.0"

PORT = 64145

# Ollama settings.
# Install the Python package with: pip install ollama
# Make sure the Ollama desktop/service is running.
DEFAULT_OLLAMA_MODEL = "qwen2.5vl:7b"
OLLAMA_HOST = "http://127.0.0.1:11434"

# Default plugin preference values.
DEFAULT_LLM_CALL_FREQUENCY_SECONDS = 0
DEFAULT_CONSECUTIVE_YES_REQUIRED = 1
DEFAULT_DEBUG_MODE = False
DEFAULT_SCREENSHOT_BATCH_SIZE = 3
DEFAULT_SCREENSHOT_FREQUENCY_MILLISECONDS = 1500
DEFAULT_SCREENSHOT_MAX_WIDTH = 500
DEFAULT_SCREENSHOT_MAX_HEIGHT = 300

DEFAULT_COMMERCIAL_PROMPT = (
    "You are examining consecutive screenshots from a TV broadcast. "
    "Determine if all these screenshots are showing advertisements and/or commercials. "
)

DEFAULT_NON_COMMERCIAL_PROMPT = (
    "You are examining consecutive screenshots from a TV broadcast. "
    "Do all of these screenshots appear to NOT be part of a commercial "
    "and instead seem to be part of regular programming? "
)

# One shared async Ollama client is enough for this plugin.
ollama_client = ollama.AsyncClient(host=OLLAMA_HOST)

# This plugin is intentionally designed for one WebSocket connection at a time.
# handle_client() stores the active connection here so it does not need to be
# passed through every function.
websocket = None

# Current plugin state.
screenshot_buffer = deque(maxlen=DEFAULT_SCREENSHOT_BATCH_SIZE)
commercial_state = False
llm_call_frequency_seconds = DEFAULT_LLM_CALL_FREQUENCY_SECONDS
consecutive_yes_required = DEFAULT_CONSECUTIVE_YES_REQUIRED
debug_mode = DEFAULT_DEBUG_MODE
screenshot_batch_size = DEFAULT_SCREENSHOT_BATCH_SIZE
screenshot_frequency_milliseconds = DEFAULT_SCREENSHOT_FREQUENCY_MILLISECONDS
screenshot_max_width = DEFAULT_SCREENSHOT_MAX_WIDTH
screenshot_max_height = DEFAULT_SCREENSHOT_MAX_HEIGHT
consecutive_yes_count = 0
last_llm_call_time = 0.0
analysis_task = None
screenshot_version = 0
last_analyzed_screenshot_version = -1
ollama_model = DEFAULT_OLLAMA_MODEL
commercial_prompt = DEFAULT_COMMERCIAL_PROMPT
non_commercial_prompt = DEFAULT_NON_COMMERCIAL_PROMPT
gpu_checked = False
preference_version = 0


async def handle_client(connection):
    """Handle the one WebSocket connection used by this plugin."""
    global websocket

    # The plugin is only intended to have one active extension connection.
    # Refuse an unexpected second connection rather than replacing the global
    # websocket underneath the current one.
    if websocket is not None:
        print("Second WebSocket connection rejected; plugin already has a client")
        await connection.close(code=1013, reason="Plugin already has an active client")
        return

    websocket = connection
    reset_runtime_state()
    print("Client connected")

    try:
        async for message in connection:
            if isinstance(message, bytes):
                await handle_screenshot(message)
            else:
                msg = json.loads(message)
                await handle_message(msg)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        await cancel_analysis_task()
        websocket = None
        print("Client disconnected")


def reset_runtime_state():
    """Reset connection-specific runtime state back to plugin defaults."""
    global screenshot_buffer
    global commercial_state
    global llm_call_frequency_seconds
    global consecutive_yes_required
    global debug_mode
    global screenshot_batch_size
    global screenshot_frequency_milliseconds
    global screenshot_max_width
    global screenshot_max_height
    global consecutive_yes_count
    global last_llm_call_time
    global analysis_task
    global screenshot_version
    global last_analyzed_screenshot_version
    global ollama_model
    global commercial_prompt
    global non_commercial_prompt
    global gpu_checked
    global preference_version

    screenshot_buffer = deque(maxlen=DEFAULT_SCREENSHOT_BATCH_SIZE)
    commercial_state = False
    llm_call_frequency_seconds = DEFAULT_LLM_CALL_FREQUENCY_SECONDS
    consecutive_yes_required = DEFAULT_CONSECUTIVE_YES_REQUIRED
    debug_mode = DEFAULT_DEBUG_MODE
    screenshot_batch_size = DEFAULT_SCREENSHOT_BATCH_SIZE
    screenshot_frequency_milliseconds = DEFAULT_SCREENSHOT_FREQUENCY_MILLISECONDS
    screenshot_max_width = DEFAULT_SCREENSHOT_MAX_WIDTH
    screenshot_max_height = DEFAULT_SCREENSHOT_MAX_HEIGHT
    consecutive_yes_count = 0
    last_llm_call_time = 0.0
    analysis_task = None
    screenshot_version = 0
    last_analyzed_screenshot_version = -1
    ollama_model = DEFAULT_OLLAMA_MODEL
    commercial_prompt = DEFAULT_COMMERCIAL_PROMPT
    non_commercial_prompt = DEFAULT_NON_COMMERCIAL_PROMPT
    gpu_checked = False
    preference_version = 0


async def cancel_analysis_task():
    """Cancel the current Ollama analysis task, if one is running."""
    global analysis_task

    if analysis_task and not analysis_task.done():
        analysis_task.cancel()
        try:
            await analysis_task
        except asyncio.CancelledError:
            pass

    analysis_task = None


async def handle_message(msg):
    global commercial_state
    global consecutive_yes_count

    message_type = msg["type"]
    data = msg.get("data", {})
    preferences = data.get("preferences", {})
    custom_trigger_plugin_preferences = (
        preferences.get("pluginTriggerPreferences", {}).get("preferences", {})
    )

    if message_type == "plugin_manifest":
        print("Plugin Manifest Requested. Sending Manifest.")
        await send_manifest()

    elif message_type == "init":
        print("Extension initiated")
        print("Full preferences:")
        print(preferences)
        print("Your custom requested plugin preferences:")
        print(custom_trigger_plugin_preferences)

        apply_plugin_preferences(
            custom_trigger_plugin_preferences,
            initialize=True,
        )

        # If the init message provides the current commercial state, use it.
        if "isCommercialState" in data:
            commercial_state = bool(data["isCommercialState"])

        print_current_preferences()

        await send_status(
            "Initializing local AI model...",
            build_current_preferences_debug(),
        )

        print("Requesting extension starts sending screenshots")
        await request_screenshots()

    elif message_type == "commercial_state_change":
        is_commercial = bool(data["isCommercialState"])
        commercial_state_trigger = data["utilities"][
            "triggerOfLastCommercialStateChange"
        ]

        # Always synchronize our state with the extension. This matters when
        # another trigger changes the commercial state.
        old_state = commercial_state
        commercial_state = is_commercial

        # Any confirmed state change starts a fresh YES streak.
        if old_state != is_commercial:
            consecutive_yes_count = 0

        print(
            "Commercial state confirmed by extension. "
            f"is_commercial={is_commercial}, "
            f"commercial_state_trigger={commercial_state_trigger}"
        )

    elif message_type == "browser_fullscreen_state_change":
        is_fullscreen = bool(data["isFullscreen"])
        print(f"Fullscreen state changed on browser. is_fullscreen={is_fullscreen}")

        # The extension sends the latest plugin preferences again when entering
        # fullscreen. Apply any changes without requiring the plugin to restart.
        if is_fullscreen and custom_trigger_plugin_preferences:
            changed_keys, screenshot_preferences_changed = apply_plugin_preferences(
                custom_trigger_plugin_preferences,
                initialize=False,
            )

            if changed_keys:
                print("Plugin preferences updated while running:")
                for key in changed_keys:
                    print(f"  - {key}")

                await send_status(
                    "AI commercial detector preferences updated",
                    (
                        "Updated preferences: "
                        + ", ".join(changed_keys)
                        + "\n"
                        + build_current_preferences_debug()
                    ),
                )

            # Frequency, dimensions, and batch size affect screenshot handling.
            # Re-send the request whenever any screenshot preference changes so
            # the browser immediately uses the new capture settings.
            if screenshot_preferences_changed:
                print("Screenshot preferences changed. Requesting screenshots again.")
                await request_screenshots()

            # If reducing the batch size means the existing rolling buffer is now
            # large enough, allow the next eligible analysis to start.
            await maybe_start_analysis()


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


def get_string_preference(preferences, key, default):
    """Read a text preference safely and fall back to its default."""
    value = preferences.get(key, default)

    if value is None:
        return default

    value = str(value).strip()
    return value if value else default


def apply_plugin_preferences(preferences, initialize=False):
    """Apply initial or updated plugin preferences and report what changed."""
    global llm_call_frequency_seconds
    global consecutive_yes_required
    global debug_mode
    global ollama_model
    global commercial_prompt
    global non_commercial_prompt
    global screenshot_batch_size
    global screenshot_frequency_milliseconds
    global screenshot_max_width
    global screenshot_max_height
    global screenshot_buffer
    global consecutive_yes_count
    global last_llm_call_time
    global screenshot_version
    global last_analyzed_screenshot_version
    global gpu_checked
    global preference_version

    if initialize:
        current_llm_frequency = DEFAULT_LLM_CALL_FREQUENCY_SECONDS
        current_yes_required = DEFAULT_CONSECUTIVE_YES_REQUIRED
        current_debug_mode = DEFAULT_DEBUG_MODE
        current_model = DEFAULT_OLLAMA_MODEL
        current_commercial_prompt = DEFAULT_COMMERCIAL_PROMPT
        current_non_commercial_prompt = DEFAULT_NON_COMMERCIAL_PROMPT
        current_batch_size = DEFAULT_SCREENSHOT_BATCH_SIZE
        current_screenshot_frequency = DEFAULT_SCREENSHOT_FREQUENCY_MILLISECONDS
        current_max_width = DEFAULT_SCREENSHOT_MAX_WIDTH
        current_max_height = DEFAULT_SCREENSHOT_MAX_HEIGHT
    else:
        current_llm_frequency = llm_call_frequency_seconds
        current_yes_required = consecutive_yes_required
        current_debug_mode = debug_mode
        current_model = ollama_model
        current_commercial_prompt = commercial_prompt
        current_non_commercial_prompt = non_commercial_prompt
        current_batch_size = screenshot_batch_size
        current_screenshot_frequency = screenshot_frequency_milliseconds
        current_max_width = screenshot_max_width
        current_max_height = screenshot_max_height

    new_values = {
        "llm-call-frequency-seconds": get_float_preference(
            preferences,
            "llm-call-frequency-seconds",
            current_llm_frequency,
            minimum=0,
        ),
        "consecutive-yes-required": get_int_preference(
            preferences,
            "consecutive-yes-required",
            current_yes_required,
            minimum=1,
        ),
        "debug-mode": get_bool_preference(
            preferences,
            "debug-mode",
            current_debug_mode,
        ),
        "ollama-model": get_string_preference(
            preferences,
            "ollama-model",
            current_model,
        ),
        "commercial-prompt": get_string_preference(
            preferences,
            "commercial-prompt",
            current_commercial_prompt,
        ),
        "non-commercial-prompt": get_string_preference(
            preferences,
            "non-commercial-prompt",
            current_non_commercial_prompt,
        ),
        "screenshot-batch-size": get_int_preference(
            preferences,
            "screenshot-batch-size",
            current_batch_size,
            minimum=1,
        ),
        "screenshot-frequency-milliseconds": get_int_preference(
            preferences,
            "screenshot-frequency-milliseconds",
            current_screenshot_frequency,
            minimum=1,
        ),
        "screenshot-max-width": get_int_preference(
            preferences,
            "screenshot-max-width",
            current_max_width,
            minimum=1,
        ),
        "screenshot-max-height": get_int_preference(
            preferences,
            "screenshot-max-height",
            current_max_height,
            minimum=1,
        ),
    }

    old_values = {
        "llm-call-frequency-seconds": current_llm_frequency,
        "consecutive-yes-required": current_yes_required,
        "debug-mode": current_debug_mode,
        "ollama-model": current_model,
        "commercial-prompt": current_commercial_prompt,
        "non-commercial-prompt": current_non_commercial_prompt,
        "screenshot-batch-size": current_batch_size,
        "screenshot-frequency-milliseconds": current_screenshot_frequency,
        "screenshot-max-width": current_max_width,
        "screenshot-max-height": current_max_height,
    }

    changed_keys = [
        key
        for key, new_value in new_values.items()
        if initialize or new_value != old_values[key]
    ]

    if initialize:
        preference_version = 0
    elif changed_keys:
        preference_version += 1

    llm_call_frequency_seconds = new_values["llm-call-frequency-seconds"]
    consecutive_yes_required = new_values["consecutive-yes-required"]
    debug_mode = new_values["debug-mode"]
    ollama_model = new_values["ollama-model"]
    commercial_prompt = new_values["commercial-prompt"]
    non_commercial_prompt = new_values["non-commercial-prompt"]
    screenshot_batch_size = new_values["screenshot-batch-size"]
    screenshot_frequency_milliseconds = new_values[
        "screenshot-frequency-milliseconds"
    ]
    screenshot_max_width = new_values["screenshot-max-width"]
    screenshot_max_height = new_values["screenshot-max-height"]

    old_buffer = screenshot_buffer
    new_batch_size = screenshot_batch_size

    if initialize:
        screenshot_buffer = deque(maxlen=new_batch_size)
        consecutive_yes_count = 0
        last_llm_call_time = 0.0
        screenshot_version = 0
        last_analyzed_screenshot_version = -1
        gpu_checked = False
    elif "screenshot-batch-size" in changed_keys:
        # Preserve as many of the newest screenshots as possible when resizing
        # the rolling batch instead of throwing the whole buffer away.
        screenshot_buffer = deque(
            list(old_buffer)[-new_batch_size:],
            maxlen=new_batch_size,
        )

    decision_preferences = {
        "ollama-model",
        "commercial-prompt",
        "non-commercial-prompt",
        "consecutive-yes-required",
    }
    if not initialize and decision_preferences.intersection(changed_keys):
        # Do not combine a previous YES streak with decisions made using a new
        # model, prompt, or confirmation threshold.
        consecutive_yes_count = 0

    if "ollama-model" in changed_keys:
        # The selected model is supplied on every Ollama chat request, so model
        # changes can take effect while the plugin is running. Re-check its
        # CPU/GPU split after the new model has successfully loaded.
        gpu_checked = False

    screenshot_keys = {
        "screenshot-batch-size",
        "screenshot-frequency-milliseconds",
        "screenshot-max-width",
        "screenshot-max-height",
    }
    screenshot_preferences_changed = bool(
        screenshot_keys.intersection(changed_keys)
    )

    return changed_keys, screenshot_preferences_changed


def print_current_preferences():
    """Print the current plugin settings in a compact form."""
    print(
        f"LLM call frequency: every {llm_call_frequency_seconds:g} "
        "second(s) minimum"
    )
    print(f"Consecutive YES responses required: {consecutive_yes_required}")
    print(f"Debug mode: {debug_mode}")
    print(f"Ollama model: {ollama_model}")
    print(f"Screenshot batch size: {screenshot_batch_size}")
    print(f"Screenshot frequency: {screenshot_frequency_milliseconds} ms")
    print(
        f"Screenshot max dimensions: {screenshot_max_width}x{screenshot_max_height}"
    )


def build_current_preferences_debug():
    """Return the current settings as readable debug text."""
    return (
        f"Model: {ollama_model}\n"
        f"LLM minimum interval: {llm_call_frequency_seconds:g}s\n"
        f"Consecutive YES required: {consecutive_yes_required}\n"
        f"Debug mode: {debug_mode}\n"
        f"Screenshot batch size: {screenshot_batch_size}\n"
        f"Screenshot frequency: {screenshot_frequency_milliseconds}ms\n"
        f"Screenshot max dimensions: {screenshot_max_width}x{screenshot_max_height}"
    )


async def handle_screenshot(screenshot_bytes):
    global screenshot_version

    print(f"Received screenshot as JPEG: {len(screenshot_bytes)} bytes")

    screenshot_buffer.append(screenshot_bytes)
    screenshot_version += 1

    print(f"Screenshot buffer: {len(screenshot_buffer)}/{screenshot_batch_size}")

    # We cannot analyze until the first full rolling batch exists.
    if len(screenshot_buffer) < screenshot_batch_size:
        return

    await maybe_start_analysis()


async def maybe_start_analysis():
    global last_llm_call_time
    global last_analyzed_screenshot_version
    global analysis_task

    if len(screenshot_buffer) < screenshot_batch_size:
        return

    # Never allow more than one Ollama request at a time.
    if analysis_task and not analysis_task.done():
        return

    # Require at least one newly received screenshot since the previous LLM
    # analysis started. This prevents frequency=0 from re-analyzing the exact
    # same batch repeatedly.
    if screenshot_version <= last_analyzed_screenshot_version:
        return

    # Respect the user's configured minimum time between the START of calls.
    now = time.monotonic()
    if now - last_llm_call_time < llm_call_frequency_seconds:
        return

    screenshots = list(screenshot_buffer)
    state_at_start = commercial_state
    preference_version_at_start = preference_version

    last_llm_call_time = now
    last_analyzed_screenshot_version = screenshot_version
    analysis_task = asyncio.create_task(
        analyze_screenshot_batch(
            screenshots,
            state_at_start,
            preference_version_at_start,
        )
    )


async def analyze_screenshot_batch(
    screenshots,
    state_at_start,
    preference_version_at_start,
):
    global analysis_task
    global consecutive_yes_count
    global commercial_state
    global gpu_checked

    try:
        print(
            f"Sending {len(screenshots)} screenshots to Ollama. "
            f"Current commercial state={state_at_start}"
        )

        # Snapshot these values at the start of the request. If preferences are
        # changed while Ollama is working, preference_version will change and the
        # result will be discarded below.
        selected_debug_mode = debug_mode
        selected_model = ollama_model
        selected_commercial_prompt = commercial_prompt
        selected_non_commercial_prompt = non_commercial_prompt

        transition_detected, llm_response, ai_stats = await ask_ollama_about_transition(
            screenshots,
            state_at_start,
            selected_debug_mode,
            selected_model,
            selected_commercial_prompt,
            selected_non_commercial_prompt,
        )

        # Preferences can change while Ollama is analyzing. Ignore a response
        # produced with stale model/prompt/settings and let the next analysis use
        # the newly applied configuration.
        if preference_version != preference_version_at_start:
            print(
                "Ignoring Ollama response because plugin preferences changed "
                "during analysis"
            )
            consecutive_yes_count = 0
            return

        # Put useful performance information at the top of every debug payload.
        ai_debug_header = build_ai_debug_header(ai_stats)

        # Check the Ollama CLI once after the model has successfully loaded.
        # This gives the same CPU/GPU split shown by `ollama ps`.
        if not gpu_checked:
            gpu_checked = await warn_if_not_full_gpu(selected_model)

        print(f"Ollama response: {llm_response!r}")
        print(ai_debug_header)

        # The commercial state may have changed while Ollama was thinking. If
        # so, this answer was produced for an outdated question and is ignored.
        if commercial_state != state_at_start:
            print(
                "Ignoring Ollama response because commercial state changed "
                "during analysis"
            )
            consecutive_yes_count = 0
            return

        if transition_detected:
            consecutive_yes_count += 1
        else:
            # A NO breaks the streak. The requested confirmations must be
            # consecutive YES responses.
            consecutive_yes_count = 0

        yes_count = consecutive_yes_count
        yes_required = consecutive_yes_required

        answer_text = "YES" if transition_detected else "NO"
        print(
            f"Transition answer={answer_text}; "
            f"consecutive YES count={yes_count}/{yes_required}"
        )

        # In debug mode, surface every decision that has not yet triggered a
        # state change. Performance/token information appears first, followed by
        # the complete YES/NO + reason response from Ollama.
        if yes_count < yes_required:
            if selected_debug_mode:
                await send_status(
                    f"AI decision: {answer_text} ({yes_count}/{yes_required} YES)",
                    ai_debug_header + "\n\nAI response:\n" + llm_response,
                )
            return

        # Enough consecutive YES responses were received. A YES means the
        # desired transition depends on our current state:
        #   normal program -> commercial
        #   commercial     -> normal program
        new_commercial_state = not state_at_start

        # Update immediately so another completed analysis cannot send the same
        # change again before the extension echoes the confirmed state back.
        commercial_state = new_commercial_state
        consecutive_yes_count = 0

        if new_commercial_state:
            display = "AI detected commercial break"
        else:
            display = "AI detected return to programming"

        if selected_debug_mode:
            debug = ai_debug_header + "\n\nAI response:\n" + llm_response
        else:
            debug = (
                ai_debug_header
                + "\n\nDecision:\n"
                + f"Ollama returned YES {yes_required} time(s) in a row. "
                + f"New commercial state={new_commercial_state}"
            )

        print(f"Sending commercial state change: {new_commercial_state}")
        await send_commercial_state_change(
            new_commercial_state,
            display,
            debug,
        )

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(f"Ollama analysis failed: {exc}")

        if websocket is not None:
            await send_status(
                "AI commercial detection error",
                f"Ollama analysis failed: {exc}",
            )
    finally:
        # Only clear the task slot if this coroutine is still the registered
        # analysis task.
        current_task = asyncio.current_task()
        if analysis_task is current_task:
            analysis_task = None

        # Important for frequency=0: if at least one screenshot arrived while
        # Ollama was working, immediately check whether another analysis can be
        # started using the newest rolling batch.
        if websocket is not None:
            await maybe_start_analysis()


async def ask_ollama_about_transition(
    screenshots,
    currently_commercial,
    selected_debug_mode,
    model,
    selected_commercial_prompt,
    selected_non_commercial_prompt,
):
    if currently_commercial:
        question = selected_non_commercial_prompt.rstrip() + " "
    else:
        question = selected_commercial_prompt.rstrip() + " "

    if selected_debug_mode:
        question += (
            "Respond with YES or NO on the first line. On the second line, give "
            "one short reason for the decision. Keep the reason concise."
        )
    else:
        question += "Respond with exactly YES or NO and nothing else."

    call_started = time.monotonic()
    response = await ollama_client.chat(
        model=model,
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
    wall_time_seconds = time.monotonic() - call_started

    llm_response = response.message.content.strip()
    transition_detected = parse_yes_no_response(
        llm_response,
        selected_debug_mode,
    )

    prompt_tokens = getattr(response, "prompt_eval_count", None)
    response_tokens = getattr(response, "eval_count", None)
    total_tokens = None
    if prompt_tokens is not None and response_tokens is not None:
        total_tokens = prompt_tokens + response_tokens

    ai_stats = {
        "model": model,
        "screenshots": len(screenshots),
        "wall_time_seconds": wall_time_seconds,
        "total_duration_ns": getattr(response, "total_duration", None),
        "load_duration_ns": getattr(response, "load_duration", None),
        "prompt_eval_duration_ns": getattr(response, "prompt_eval_duration", None),
        "eval_duration_ns": getattr(response, "eval_duration", None),
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "total_tokens": total_tokens,
    }

    return transition_detected, llm_response, ai_stats


def format_nanoseconds_as_seconds(value):
    """Format an Ollama nanosecond duration without failing on missing values."""
    if value is None:
        return "n/a"

    try:
        return f"{float(value) / 1_000_000_000:.3f}s"
    except (TypeError, ValueError):
        return "n/a"


def format_token_count(value):
    """Format a token count returned by Ollama."""
    if value is None:
        return "n/a"

    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def build_ai_debug_header(stats):
    """Build the performance/token section placed at the top of debug output."""
    return (
        "AI call details:\n"
        f"Model: {stats['model']}\n"
        f"Screenshots: {stats['screenshots']}\n"
        f"Wall-clock time: {stats['wall_time_seconds']:.3f}s\n"
        f"Ollama total duration: "
        f"{format_nanoseconds_as_seconds(stats['total_duration_ns'])}\n"
        f"Model load duration: "
        f"{format_nanoseconds_as_seconds(stats['load_duration_ns'])}\n"
        f"Prompt/image evaluation: "
        f"{format_nanoseconds_as_seconds(stats['prompt_eval_duration_ns'])}\n"
        f"Response generation: "
        f"{format_nanoseconds_as_seconds(stats['eval_duration_ns'])}\n"
        f"Prompt tokens: {format_token_count(stats['prompt_tokens'])}\n"
        f"Response tokens: {format_token_count(stats['response_tokens'])}\n"
        f"Total tokens: {format_token_count(stats['total_tokens'])}"
    )


def parse_yes_no_response(response, selected_debug_mode=False):
    """Convert an Ollama response into a strict True/False decision."""
    if selected_debug_mode:
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

    expected = (
        "YES/NO on the first line"
        if selected_debug_mode
        else "only YES or NO"
    )
    raise ValueError(
        f"Expected Ollama to return {expected}, got: {response!r}"
    )


def get_ollama_processor_status():
    """Return the text output from `ollama ps`."""
    try:
        startupinfo = None
        creationflags = 0

        # Avoid flashing a console window on Windows when this script is packaged.
        if hasattr(subprocess, "STARTUPINFO"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        result = subprocess.run(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            check=True,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        return result.stdout.strip()

    except Exception as exc:
        print(f"Could not run ollama ps: {exc}")
        return ""


def get_ollama_model_processor_line(status, model):
    """Find the row for a model in `ollama ps` output."""
    model_lower = model.lower()

    for line in status.splitlines():
        if model_lower in line.lower():
            return line.strip()

    return ""


async def warn_if_not_full_gpu(model):
    """Warn the extension if Ollama reports any CPU offload for the model."""
    status = await asyncio.to_thread(get_ollama_processor_status)

    if not status:
        print("Could not determine Ollama processor status")
        return False

    model_line = get_ollama_model_processor_line(status, model)

    if not model_line:
        print(f"Could not find {model!r} in ollama ps output")
        print(status)
        return False

    print(f"Ollama processor status: {model_line}")

    if "100% GPU" not in model_line.upper():
        await send_status(
            "Warning: Ollama is not fully using the GPU.",
            (
                f"Ollama is using CPU offload for {model}. Performance may be reduced. "
                f"Restarting Ollama may allow the model to load fully into VRAM.\n"
                f"{model_line}"
            ),
        )

    return True


async def send_commercial_state_change(is_commercial, display, debug):
    if websocket is None:
        return

    try:
        await websocket.send(
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
    is_auto_commercial_blocked,
    display,
    debug,
):
    if websocket is None:
        return

    try:
        await websocket.send(
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


async def send_status(display, debug):
    if websocket is None:
        return

    try:
        await websocket.send(
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


async def request_screenshots():
    if websocket is None:
        return

    try:
        await websocket.send(
            json.dumps(
                {
                    "type": "request_screenshots",
                    "timestamp": time.time(),
                    "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
                    "data": {
                        "shouldSendScreenshots": True,
                        "frequencyMilliseconds": screenshot_frequency_milliseconds,
                        "maxDimensionsPixels": {
                            "height": screenshot_max_height,
                            "width": screenshot_max_width,
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


async def get_local_ollama_models():
    """Return the names of models currently installed in the local Ollama library."""
    try:
        response = await ollama_client.list()
        models = []

        for model in response.models:
            model_name = getattr(model, "model", None) or getattr(model, "name", None)
            if model_name:
                models.append(str(model_name))

        return sorted(set(models), key=str.lower)

    except Exception as exc:
        print(f"Could not get local Ollama models: {exc}")
        return []


async def send_manifest():
    if websocket is None:
        return

    local_models = await get_local_ollama_models()
    model_options = [
        {"label": model_name, "value": model_name}
        for model_name in local_models
    ]

    # The manifest schema expects at least one option. If Ollama is unavailable
    # or no models are installed, keep the preferred default visible so the
    # manifest can still render and the user gets a useful model name to install.
    if not model_options:
        model_options = [
            {"label": DEFAULT_OLLAMA_MODEL, "value": DEFAULT_OLLAMA_MODEL}
        ]

    model_default = (
        DEFAULT_OLLAMA_MODEL
        if DEFAULT_OLLAMA_MODEL in local_models
        else model_options[0]["value"]
    )

    try:
        await websocket.send(
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
                                "key": "ollama-model",
                                "label": "Ollama Model",
                                "description": (
                                    "Local Ollama model used for screenshot analysis. "
                                    "Only models currently installed in Ollama are listed."
                                ),
                                "type": "select",
                                "options": model_options,
                                "default": model_default,
                            },
                            {
                                "key": "commercial-prompt",
                                "label": "Commercial Prompt",
                                "description": (
                                    "Prompt used while regular programming is active to "
                                    "decide whether the screenshots indicate a commercial."
                                ),
                                "type": "textarea",
                                "default": DEFAULT_COMMERCIAL_PROMPT,
                            },
                            {
                                "key": "non-commercial-prompt",
                                "label": "Non-Commercial Prompt",
                                "description": (
                                    "Prompt used while a commercial is active to decide "
                                    "whether regular programming has returned."
                                ),
                                "type": "textarea",
                                "default": DEFAULT_NON_COMMERCIAL_PROMPT,
                            },
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
        print(f"Default Ollama model: {DEFAULT_OLLAMA_MODEL}")
        await asyncio.Future()


asyncio.run(main())