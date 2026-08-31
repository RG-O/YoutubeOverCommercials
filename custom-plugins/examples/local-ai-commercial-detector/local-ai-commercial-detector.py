import asyncio
import json
import re
import subprocess
import time
from collections import deque

import ollama
import websockets

PLUGIN_PROTOCOL_VERSION = 1  # DO NOT TOUCH

PLUGIN_NAME = "AI Commercial Detector"
PLUGIN_ID = "ai-commercial-detector-ws"  # Must be unique
PLUGIN_VERSION = "1.8.1"

PORT = 64145

# Ollama settings.
# Install the Python package with: pip install ollama
# Make sure the Ollama desktop/service is running.
DEFAULT_OLLAMA_MODEL = "qwen2.5vl:7b"
DEFAULT_OLLAMA_CONTEXT_SIZE = None  # None = let the Ollama runtime decide
OLLAMA_HOST = "http://127.0.0.1:11434"

# Regular-programming and commercial defaults intentionally match. They are
# separate preferences so users can tune the two states independently.
DEFAULT_REGULAR_LLM_CALL_FREQUENCY_SECONDS = 0
DEFAULT_COMMERCIAL_LLM_CALL_FREQUENCY_SECONDS = 0

DEFAULT_REGULAR_CONSECUTIVE_YES_REQUIRED = 1
DEFAULT_COMMERCIAL_CONSECUTIVE_YES_REQUIRED = 1

DEFAULT_REGULAR_SCREENSHOT_BATCH_SIZE = 3
DEFAULT_COMMERCIAL_SCREENSHOT_BATCH_SIZE = 3

DEFAULT_REGULAR_SCREENSHOT_FREQUENCY_MILLISECONDS = 1500
DEFAULT_COMMERCIAL_SCREENSHOT_FREQUENCY_MILLISECONDS = 1500

# Screenshot dimensions are state-specific, while trim settings are shared.
DEFAULT_REGULAR_SCREENSHOT_MAX_WIDTH = 500
DEFAULT_COMMERCIAL_SCREENSHOT_MAX_WIDTH = 500
DEFAULT_REGULAR_SCREENSHOT_MAX_HEIGHT = 300
DEFAULT_COMMERCIAL_SCREENSHOT_MAX_HEIGHT = 300

# Cooldowns begin after a confirmed state change. Ollama still runs during the
# cooldown, but its decisions are ignored for state-change logic.
DEFAULT_INTO_COMMERCIAL_COOLDOWN_SECONDS = 6
DEFAULT_OUT_OF_COMMERCIAL_COOLDOWN_SECONDS = 6

DEFAULT_SCREENSHOT_TRIM_TOP_PERCENT = 0
DEFAULT_SCREENSHOT_TRIM_RIGHT_PERCENT = 0
DEFAULT_SCREENSHOT_TRIM_BOTTOM_PERCENT = 0
DEFAULT_SCREENSHOT_TRIM_LEFT_PERCENT = 0

# These prompts are user-editable. The response-format instruction is included
# directly in each default prompt rather than appended elsewhere in the script.
DEFAULT_COMMERCIAL_PROMPT = (
    "You are examining consecutive screenshots from a TV broadcast. "
    "Determine if all these screenshots are showing advertisements and/or commercials. "
    "Respond on one line. Response with YES or NO followed by a dash and then "
    "one short reason for the decision. Keep the reason concise."
)

#TODO: Add option to grab a few screenshots at the beging and have it summarize what the user is watching so it can check specifically for that
DEFAULT_NON_COMMERCIAL_PROMPT = (
    "You are examining consecutive screenshots from a TV broadcast. "
    "Do all of these screenshots appear to NOT be part of a commercial "
    "and instead seem to be part of regular programming? "
    "Respond on one line. Response with YES or NO followed by a dash and then "
    "one short reason for the decision. Keep the reason concise."
)

# One shared async Ollama client is enough for this plugin.
ollama_client = ollama.AsyncClient(host=OLLAMA_HOST)

# This plugin is intentionally designed for one WebSocket connection at a time.
# handle_client() stores the active connection here so it does not need to be
# passed through every function.
websocket = None

# Current plugin state.
commercial_state = False

regular_llm_call_frequency_seconds = DEFAULT_REGULAR_LLM_CALL_FREQUENCY_SECONDS
commercial_llm_call_frequency_seconds = DEFAULT_COMMERCIAL_LLM_CALL_FREQUENCY_SECONDS

regular_consecutive_yes_required = DEFAULT_REGULAR_CONSECUTIVE_YES_REQUIRED
commercial_consecutive_yes_required = DEFAULT_COMMERCIAL_CONSECUTIVE_YES_REQUIRED

regular_screenshot_batch_size = DEFAULT_REGULAR_SCREENSHOT_BATCH_SIZE
commercial_screenshot_batch_size = DEFAULT_COMMERCIAL_SCREENSHOT_BATCH_SIZE

regular_screenshot_frequency_milliseconds = (
    DEFAULT_REGULAR_SCREENSHOT_FREQUENCY_MILLISECONDS
)
commercial_screenshot_frequency_milliseconds = (
    DEFAULT_COMMERCIAL_SCREENSHOT_FREQUENCY_MILLISECONDS
)

regular_screenshot_max_width = DEFAULT_REGULAR_SCREENSHOT_MAX_WIDTH
commercial_screenshot_max_width = DEFAULT_COMMERCIAL_SCREENSHOT_MAX_WIDTH
regular_screenshot_max_height = DEFAULT_REGULAR_SCREENSHOT_MAX_HEIGHT
commercial_screenshot_max_height = DEFAULT_COMMERCIAL_SCREENSHOT_MAX_HEIGHT

into_commercial_cooldown_seconds = DEFAULT_INTO_COMMERCIAL_COOLDOWN_SECONDS
out_of_commercial_cooldown_seconds = DEFAULT_OUT_OF_COMMERCIAL_COOLDOWN_SECONDS
cooldown_until = 0.0

screenshot_trim_top_percent = DEFAULT_SCREENSHOT_TRIM_TOP_PERCENT
screenshot_trim_right_percent = DEFAULT_SCREENSHOT_TRIM_RIGHT_PERCENT
screenshot_trim_bottom_percent = DEFAULT_SCREENSHOT_TRIM_BOTTOM_PERCENT
screenshot_trim_left_percent = DEFAULT_SCREENSHOT_TRIM_LEFT_PERCENT

screenshot_buffer = deque(maxlen=DEFAULT_REGULAR_SCREENSHOT_BATCH_SIZE)
consecutive_yes_count = 0
last_llm_call_time = 0.0
analysis_task = None
screenshot_version = 0
last_analyzed_screenshot_version = -1

ollama_model = DEFAULT_OLLAMA_MODEL
ollama_context_size = DEFAULT_OLLAMA_CONTEXT_SIZE
commercial_prompt = DEFAULT_COMMERCIAL_PROMPT
non_commercial_prompt = DEFAULT_NON_COMMERCIAL_PROMPT
gpu_checked = False

# Incremented whenever runtime preferences change. An LLM result created with an
# older preference version is ignored so it cannot affect the new configuration.
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
    global commercial_state
    global regular_llm_call_frequency_seconds
    global commercial_llm_call_frequency_seconds
    global regular_consecutive_yes_required
    global commercial_consecutive_yes_required
    global regular_screenshot_batch_size
    global commercial_screenshot_batch_size
    global regular_screenshot_frequency_milliseconds
    global commercial_screenshot_frequency_milliseconds
    global regular_screenshot_max_width
    global commercial_screenshot_max_width
    global regular_screenshot_max_height
    global commercial_screenshot_max_height
    global into_commercial_cooldown_seconds
    global out_of_commercial_cooldown_seconds
    global cooldown_until
    global screenshot_trim_top_percent
    global screenshot_trim_right_percent
    global screenshot_trim_bottom_percent
    global screenshot_trim_left_percent
    global screenshot_buffer
    global consecutive_yes_count
    global last_llm_call_time
    global analysis_task
    global screenshot_version
    global last_analyzed_screenshot_version
    global ollama_model
    global ollama_context_size
    global commercial_prompt
    global non_commercial_prompt
    global gpu_checked
    global preference_version

    commercial_state = False

    regular_llm_call_frequency_seconds = DEFAULT_REGULAR_LLM_CALL_FREQUENCY_SECONDS
    commercial_llm_call_frequency_seconds = DEFAULT_COMMERCIAL_LLM_CALL_FREQUENCY_SECONDS

    regular_consecutive_yes_required = DEFAULT_REGULAR_CONSECUTIVE_YES_REQUIRED
    commercial_consecutive_yes_required = DEFAULT_COMMERCIAL_CONSECUTIVE_YES_REQUIRED

    regular_screenshot_batch_size = DEFAULT_REGULAR_SCREENSHOT_BATCH_SIZE
    commercial_screenshot_batch_size = DEFAULT_COMMERCIAL_SCREENSHOT_BATCH_SIZE

    regular_screenshot_frequency_milliseconds = (
        DEFAULT_REGULAR_SCREENSHOT_FREQUENCY_MILLISECONDS
    )
    commercial_screenshot_frequency_milliseconds = (
        DEFAULT_COMMERCIAL_SCREENSHOT_FREQUENCY_MILLISECONDS
    )

    regular_screenshot_max_width = DEFAULT_REGULAR_SCREENSHOT_MAX_WIDTH
    commercial_screenshot_max_width = DEFAULT_COMMERCIAL_SCREENSHOT_MAX_WIDTH
    regular_screenshot_max_height = DEFAULT_REGULAR_SCREENSHOT_MAX_HEIGHT
    commercial_screenshot_max_height = DEFAULT_COMMERCIAL_SCREENSHOT_MAX_HEIGHT

    into_commercial_cooldown_seconds = DEFAULT_INTO_COMMERCIAL_COOLDOWN_SECONDS
    out_of_commercial_cooldown_seconds = DEFAULT_OUT_OF_COMMERCIAL_COOLDOWN_SECONDS
    cooldown_until = 0.0

    screenshot_trim_top_percent = DEFAULT_SCREENSHOT_TRIM_TOP_PERCENT
    screenshot_trim_right_percent = DEFAULT_SCREENSHOT_TRIM_RIGHT_PERCENT
    screenshot_trim_bottom_percent = DEFAULT_SCREENSHOT_TRIM_BOTTOM_PERCENT
    screenshot_trim_left_percent = DEFAULT_SCREENSHOT_TRIM_LEFT_PERCENT

    screenshot_buffer = deque(maxlen=DEFAULT_REGULAR_SCREENSHOT_BATCH_SIZE)
    consecutive_yes_count = 0
    last_llm_call_time = 0.0
    analysis_task = None
    screenshot_version = 0
    last_analyzed_screenshot_version = -1

    ollama_model = DEFAULT_OLLAMA_MODEL
    ollama_context_size = DEFAULT_OLLAMA_CONTEXT_SIZE
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

        resize_screenshot_buffer_for_current_state()
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

        old_state = commercial_state
        commercial_state = is_commercial

        # Any confirmed state change starts a fresh YES streak and the cooldown
        # associated with the direction of that state change. This also covers
        # state changes initiated by triggers outside this plugin.
        if old_state != is_commercial:
            consecutive_yes_count = 0
            start_state_change_cooldown(is_commercial)
            resize_screenshot_buffer_for_current_state()
            await request_screenshots()

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

            # Re-send screenshot settings whenever any screenshot-related
            # preference changes, including an inactive state's settings.
            if screenshot_preferences_changed:
                resize_screenshot_buffer_for_current_state()
                print("Screenshot preferences changed. Requesting screenshots again.")
                await request_screenshots()

            # If a new batch size is smaller, the preserved rolling buffer may
            # already be large enough for another analysis.
            await maybe_start_analysis()


def get_float_preference(preferences, key, default, minimum=None, maximum=None):
    """Read a numeric preference safely and fall back to its default."""
    try:
        value = float(preferences.get(key, default))
    except (TypeError, ValueError):
        value = default

    if minimum is not None:
        value = max(minimum, value)

    if maximum is not None:
        value = min(maximum, value)

    return value


def get_int_preference(preferences, key, default, minimum=None, maximum=None):
    """Read an integer preference safely and fall back to its default."""
    try:
        value = int(float(preferences.get(key, default)))
    except (TypeError, ValueError):
        value = default

    if minimum is not None:
        value = max(minimum, value)

    if maximum is not None:
        value = min(maximum, value)

    return value


def get_string_preference(preferences, key, default):
    """Read a text preference safely and fall back to its default."""
    value = preferences.get(key, default)

    if value is None:
        return default

    value = str(value).strip()
    return value if value else default


def get_context_size_preference(preferences, key, default):
    """Read the optional Ollama context size preference. None means runtime default."""
    value = preferences.get(key, default)

    if value is None:
        return None

    value = str(value).strip().lower()
    if value in ("", "runtime-default", "default", "none"):
        return None

    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def format_context_size(value):
    """Return a readable context-size label for status/debug output."""
    if value is None:
        return "Runtime Default"
    return f"{value:,} tokens"


def apply_plugin_preferences(preferences, initialize=False):
    """Apply initial or updated plugin preferences and report what changed."""
    global regular_llm_call_frequency_seconds
    global commercial_llm_call_frequency_seconds
    global regular_consecutive_yes_required
    global commercial_consecutive_yes_required
    global regular_screenshot_batch_size
    global commercial_screenshot_batch_size
    global regular_screenshot_frequency_milliseconds
    global commercial_screenshot_frequency_milliseconds
    global regular_screenshot_max_width
    global commercial_screenshot_max_width
    global regular_screenshot_max_height
    global commercial_screenshot_max_height
    global into_commercial_cooldown_seconds
    global out_of_commercial_cooldown_seconds
    global cooldown_until
    global screenshot_trim_top_percent
    global screenshot_trim_right_percent
    global screenshot_trim_bottom_percent
    global screenshot_trim_left_percent
    global consecutive_yes_count
    global last_llm_call_time
    global screenshot_version
    global last_analyzed_screenshot_version
    global ollama_model
    global ollama_context_size
    global commercial_prompt
    global non_commercial_prompt
    global gpu_checked
    global preference_version

    if initialize:
        current_values = {
            "regular-llm-call-frequency-seconds": DEFAULT_REGULAR_LLM_CALL_FREQUENCY_SECONDS,
            "commercial-llm-call-frequency-seconds": DEFAULT_COMMERCIAL_LLM_CALL_FREQUENCY_SECONDS,
            "regular-consecutive-yes-required": DEFAULT_REGULAR_CONSECUTIVE_YES_REQUIRED,
            "commercial-consecutive-yes-required": DEFAULT_COMMERCIAL_CONSECUTIVE_YES_REQUIRED,
            "regular-screenshot-batch-size": DEFAULT_REGULAR_SCREENSHOT_BATCH_SIZE,
            "commercial-screenshot-batch-size": DEFAULT_COMMERCIAL_SCREENSHOT_BATCH_SIZE,
            "regular-screenshot-frequency-milliseconds": DEFAULT_REGULAR_SCREENSHOT_FREQUENCY_MILLISECONDS,
            "commercial-screenshot-frequency-milliseconds": DEFAULT_COMMERCIAL_SCREENSHOT_FREQUENCY_MILLISECONDS,
            "regular-screenshot-max-width": DEFAULT_REGULAR_SCREENSHOT_MAX_WIDTH,
            "commercial-screenshot-max-width": DEFAULT_COMMERCIAL_SCREENSHOT_MAX_WIDTH,
            "regular-screenshot-max-height": DEFAULT_REGULAR_SCREENSHOT_MAX_HEIGHT,
            "commercial-screenshot-max-height": DEFAULT_COMMERCIAL_SCREENSHOT_MAX_HEIGHT,
            "into-commercial-cooldown-seconds": DEFAULT_INTO_COMMERCIAL_COOLDOWN_SECONDS,
            "out-of-commercial-cooldown-seconds": DEFAULT_OUT_OF_COMMERCIAL_COOLDOWN_SECONDS,
            "screenshot-trim-top-percent": DEFAULT_SCREENSHOT_TRIM_TOP_PERCENT,
            "screenshot-trim-right-percent": DEFAULT_SCREENSHOT_TRIM_RIGHT_PERCENT,
            "screenshot-trim-bottom-percent": DEFAULT_SCREENSHOT_TRIM_BOTTOM_PERCENT,
            "screenshot-trim-left-percent": DEFAULT_SCREENSHOT_TRIM_LEFT_PERCENT,
            "ollama-model": DEFAULT_OLLAMA_MODEL,
            "ollama-context-size": DEFAULT_OLLAMA_CONTEXT_SIZE,
            "commercial-prompt": DEFAULT_COMMERCIAL_PROMPT,
            "non-commercial-prompt": DEFAULT_NON_COMMERCIAL_PROMPT,
        }
    else:
        current_values = {
            "regular-llm-call-frequency-seconds": regular_llm_call_frequency_seconds,
            "commercial-llm-call-frequency-seconds": commercial_llm_call_frequency_seconds,
            "regular-consecutive-yes-required": regular_consecutive_yes_required,
            "commercial-consecutive-yes-required": commercial_consecutive_yes_required,
            "regular-screenshot-batch-size": regular_screenshot_batch_size,
            "commercial-screenshot-batch-size": commercial_screenshot_batch_size,
            "regular-screenshot-frequency-milliseconds": regular_screenshot_frequency_milliseconds,
            "commercial-screenshot-frequency-milliseconds": commercial_screenshot_frequency_milliseconds,
            "regular-screenshot-max-width": regular_screenshot_max_width,
            "commercial-screenshot-max-width": commercial_screenshot_max_width,
            "regular-screenshot-max-height": regular_screenshot_max_height,
            "commercial-screenshot-max-height": commercial_screenshot_max_height,
            "into-commercial-cooldown-seconds": into_commercial_cooldown_seconds,
            "out-of-commercial-cooldown-seconds": out_of_commercial_cooldown_seconds,
            "screenshot-trim-top-percent": screenshot_trim_top_percent,
            "screenshot-trim-right-percent": screenshot_trim_right_percent,
            "screenshot-trim-bottom-percent": screenshot_trim_bottom_percent,
            "screenshot-trim-left-percent": screenshot_trim_left_percent,
            "ollama-model": ollama_model,
            "ollama-context-size": ollama_context_size,
            "commercial-prompt": commercial_prompt,
            "non-commercial-prompt": non_commercial_prompt,
        }

    new_values = {
        "regular-llm-call-frequency-seconds": get_float_preference(
            preferences,
            "regular-llm-call-frequency-seconds",
            current_values["regular-llm-call-frequency-seconds"],
            minimum=0,
        ),
        "commercial-llm-call-frequency-seconds": get_float_preference(
            preferences,
            "commercial-llm-call-frequency-seconds",
            current_values["commercial-llm-call-frequency-seconds"],
            minimum=0,
        ),
        "regular-consecutive-yes-required": get_int_preference(
            preferences,
            "regular-consecutive-yes-required",
            current_values["regular-consecutive-yes-required"],
            minimum=1,
        ),
        "commercial-consecutive-yes-required": get_int_preference(
            preferences,
            "commercial-consecutive-yes-required",
            current_values["commercial-consecutive-yes-required"],
            minimum=1,
        ),
        "regular-screenshot-batch-size": get_int_preference(
            preferences,
            "regular-screenshot-batch-size",
            current_values["regular-screenshot-batch-size"],
            minimum=1,
        ),
        "commercial-screenshot-batch-size": get_int_preference(
            preferences,
            "commercial-screenshot-batch-size",
            current_values["commercial-screenshot-batch-size"],
            minimum=1,
        ),
        "regular-screenshot-frequency-milliseconds": get_int_preference(
            preferences,
            "regular-screenshot-frequency-milliseconds",
            current_values["regular-screenshot-frequency-milliseconds"],
            minimum=1,
        ),
        "commercial-screenshot-frequency-milliseconds": get_int_preference(
            preferences,
            "commercial-screenshot-frequency-milliseconds",
            current_values["commercial-screenshot-frequency-milliseconds"],
            minimum=1,
        ),
        "regular-screenshot-max-width": get_int_preference(
            preferences,
            "regular-screenshot-max-width",
            current_values["regular-screenshot-max-width"],
            minimum=1,
        ),
        "commercial-screenshot-max-width": get_int_preference(
            preferences,
            "commercial-screenshot-max-width",
            current_values["commercial-screenshot-max-width"],
            minimum=1,
        ),
        "regular-screenshot-max-height": get_int_preference(
            preferences,
            "regular-screenshot-max-height",
            current_values["regular-screenshot-max-height"],
            minimum=1,
        ),
        "commercial-screenshot-max-height": get_int_preference(
            preferences,
            "commercial-screenshot-max-height",
            current_values["commercial-screenshot-max-height"],
            minimum=1,
        ),
        "into-commercial-cooldown-seconds": get_float_preference(
            preferences,
            "into-commercial-cooldown-seconds",
            current_values["into-commercial-cooldown-seconds"],
            minimum=0,
        ),
        "out-of-commercial-cooldown-seconds": get_float_preference(
            preferences,
            "out-of-commercial-cooldown-seconds",
            current_values["out-of-commercial-cooldown-seconds"],
            minimum=0,
        ),
        "screenshot-trim-top-percent": get_float_preference(
            preferences,
            "screenshot-trim-top-percent",
            current_values["screenshot-trim-top-percent"],
            minimum=0,
            maximum=100,
        ),
        "screenshot-trim-right-percent": get_float_preference(
            preferences,
            "screenshot-trim-right-percent",
            current_values["screenshot-trim-right-percent"],
            minimum=0,
            maximum=100,
        ),
        "screenshot-trim-bottom-percent": get_float_preference(
            preferences,
            "screenshot-trim-bottom-percent",
            current_values["screenshot-trim-bottom-percent"],
            minimum=0,
            maximum=100,
        ),
        "screenshot-trim-left-percent": get_float_preference(
            preferences,
            "screenshot-trim-left-percent",
            current_values["screenshot-trim-left-percent"],
            minimum=0,
            maximum=100,
        ),
        "ollama-model": get_string_preference(
            preferences,
            "ollama-model",
            current_values["ollama-model"],
        ),
        "ollama-context-size": get_context_size_preference(
            preferences,
            "ollama-context-size",
            current_values["ollama-context-size"],
        ),
        "commercial-prompt": get_string_preference(
            preferences,
            "commercial-prompt",
            current_values["commercial-prompt"],
        ),
        "non-commercial-prompt": get_string_preference(
            preferences,
            "non-commercial-prompt",
            current_values["non-commercial-prompt"],
        ),
    }

    changed_keys = [
        key
        for key, new_value in new_values.items()
        if initialize or new_value != current_values[key]
    ]

    if initialize:
        preference_version = 0
    elif changed_keys:
        preference_version += 1

    regular_llm_call_frequency_seconds = new_values[
        "regular-llm-call-frequency-seconds"
    ]
    commercial_llm_call_frequency_seconds = new_values[
        "commercial-llm-call-frequency-seconds"
    ]
    regular_consecutive_yes_required = new_values[
        "regular-consecutive-yes-required"
    ]
    commercial_consecutive_yes_required = new_values[
        "commercial-consecutive-yes-required"
    ]
    regular_screenshot_batch_size = new_values["regular-screenshot-batch-size"]
    commercial_screenshot_batch_size = new_values["commercial-screenshot-batch-size"]
    regular_screenshot_frequency_milliseconds = new_values[
        "regular-screenshot-frequency-milliseconds"
    ]
    commercial_screenshot_frequency_milliseconds = new_values[
        "commercial-screenshot-frequency-milliseconds"
    ]
    regular_screenshot_max_width = new_values["regular-screenshot-max-width"]
    commercial_screenshot_max_width = new_values["commercial-screenshot-max-width"]
    regular_screenshot_max_height = new_values["regular-screenshot-max-height"]
    commercial_screenshot_max_height = new_values["commercial-screenshot-max-height"]
    into_commercial_cooldown_seconds = new_values["into-commercial-cooldown-seconds"]
    out_of_commercial_cooldown_seconds = new_values["out-of-commercial-cooldown-seconds"]
    screenshot_trim_top_percent = new_values["screenshot-trim-top-percent"]
    screenshot_trim_right_percent = new_values["screenshot-trim-right-percent"]
    screenshot_trim_bottom_percent = new_values["screenshot-trim-bottom-percent"]
    screenshot_trim_left_percent = new_values["screenshot-trim-left-percent"]
    ollama_model = new_values["ollama-model"]
    ollama_context_size = new_values["ollama-context-size"]
    commercial_prompt = new_values["commercial-prompt"]
    non_commercial_prompt = new_values["non-commercial-prompt"]

    if initialize:
        consecutive_yes_count = 0
        last_llm_call_time = 0.0
        screenshot_version = 0
        last_analyzed_screenshot_version = -1
        gpu_checked = False

    # Do not carry a YES streak across a model, prompt, confirmation threshold,
    # or batch-size change because the decisions are no longer directly
    # comparable.
    decision_keys = {
        "ollama-model",
        "ollama-context-size",
        "commercial-prompt",
        "non-commercial-prompt",
        "regular-consecutive-yes-required",
        "commercial-consecutive-yes-required",
        "regular-screenshot-batch-size",
        "commercial-screenshot-batch-size",
    }
    if not initialize and decision_keys.intersection(changed_keys):
        consecutive_yes_count = 0

    if "ollama-model" in changed_keys:
        # The next Ollama request can use the newly selected model immediately.
        # Re-check the new model's processor split after it loads.
        gpu_checked = False

    screenshot_keys = {
        "regular-screenshot-batch-size",
        "commercial-screenshot-batch-size",
        "regular-screenshot-frequency-milliseconds",
        "commercial-screenshot-frequency-milliseconds",
        "regular-screenshot-max-width",
        "commercial-screenshot-max-width",
        "regular-screenshot-max-height",
        "commercial-screenshot-max-height",
        "screenshot-trim-top-percent",
        "screenshot-trim-right-percent",
        "screenshot-trim-bottom-percent",
        "screenshot-trim-left-percent",
    }
    screenshot_preferences_changed = bool(screenshot_keys.intersection(changed_keys))

    return changed_keys, screenshot_preferences_changed


def get_active_llm_call_frequency():
    if commercial_state:
        return commercial_llm_call_frequency_seconds
    return regular_llm_call_frequency_seconds


def get_active_consecutive_yes_required():
    if commercial_state:
        return commercial_consecutive_yes_required
    return regular_consecutive_yes_required


def get_active_screenshot_batch_size():
    if commercial_state:
        return commercial_screenshot_batch_size
    return regular_screenshot_batch_size


def get_active_screenshot_frequency_milliseconds():
    if commercial_state:
        return commercial_screenshot_frequency_milliseconds
    return regular_screenshot_frequency_milliseconds


def get_active_screenshot_max_width():
    if commercial_state:
        return commercial_screenshot_max_width
    return regular_screenshot_max_width


def get_active_screenshot_max_height():
    if commercial_state:
        return commercial_screenshot_max_height
    return regular_screenshot_max_height


def start_state_change_cooldown(new_commercial_state):
    """Start the cooldown for the direction of a confirmed state change."""
    global cooldown_until

    if new_commercial_state:
        cooldown_seconds = into_commercial_cooldown_seconds
        direction = "into commercial"
    else:
        cooldown_seconds = out_of_commercial_cooldown_seconds
        direction = "out of commercial"

    cooldown_until = time.monotonic() + cooldown_seconds
    print(f"Starting {direction} cooldown for {cooldown_seconds:g} second(s)")


def get_cooldown_remaining_seconds():
    """Return the remaining state-change cooldown, or zero when it has expired."""
    return max(0.0, cooldown_until - time.monotonic())


def resize_screenshot_buffer_for_current_state():
    """Resize the rolling buffer while preserving the newest screenshots."""
    global screenshot_buffer

    new_batch_size = get_active_screenshot_batch_size()

    if screenshot_buffer.maxlen == new_batch_size:
        return

    screenshot_buffer = deque(
        list(screenshot_buffer)[-new_batch_size:],
        maxlen=new_batch_size,
    )


def print_current_preferences():
    """Print the current plugin settings in a compact form."""
    print(f"Ollama model: {ollama_model}")
    print(f"Ollama context size: {format_context_size(ollama_context_size)}")
    print(
        "Regular programming: "
        f"LLM frequency={regular_llm_call_frequency_seconds:g}s, "
        f"YES required={regular_consecutive_yes_required}, "
        f"batch size={regular_screenshot_batch_size}, "
        f"screenshot frequency={regular_screenshot_frequency_milliseconds}ms, "
        f"max dimensions={regular_screenshot_max_width}x{regular_screenshot_max_height}"
    )
    print(
        "Commercial: "
        f"LLM frequency={commercial_llm_call_frequency_seconds:g}s, "
        f"YES required={commercial_consecutive_yes_required}, "
        f"batch size={commercial_screenshot_batch_size}, "
        f"screenshot frequency={commercial_screenshot_frequency_milliseconds}ms, "
        f"max dimensions={commercial_screenshot_max_width}x{commercial_screenshot_max_height}"
    )
    print(
        f"Cooldowns: into commercial={into_commercial_cooldown_seconds:g}s, "
        f"out of commercial={out_of_commercial_cooldown_seconds:g}s"
    )
    print(
        "Screenshot trim percentages: "
        f"top={screenshot_trim_top_percent:g}, "
        f"right={screenshot_trim_right_percent:g}, "
        f"bottom={screenshot_trim_bottom_percent:g}, "
        f"left={screenshot_trim_left_percent:g}"
    )


def build_current_preferences_debug():
    """Return the current settings as readable debug text."""
    return (
        f"Model: {ollama_model}\n"
        f"Ollama context size: {format_context_size(ollama_context_size)}\n"
        f"Current state: {'commercial' if commercial_state else 'regular programming'}\n"
        f"Regular LLM minimum interval: {regular_llm_call_frequency_seconds:g}s\n"
        f"Commercial LLM minimum interval: {commercial_llm_call_frequency_seconds:g}s\n"
        f"Regular consecutive YES required: {regular_consecutive_yes_required}\n"
        f"Commercial consecutive YES required: {commercial_consecutive_yes_required}\n"
        f"Regular screenshot batch size: {regular_screenshot_batch_size}\n"
        f"Commercial screenshot batch size: {commercial_screenshot_batch_size}\n"
        f"Regular screenshot frequency: {regular_screenshot_frequency_milliseconds}ms\n"
        f"Commercial screenshot frequency: {commercial_screenshot_frequency_milliseconds}ms\n"
        f"Regular screenshot max dimensions: {regular_screenshot_max_width}x{regular_screenshot_max_height}\n"
        f"Commercial screenshot max dimensions: {commercial_screenshot_max_width}x{commercial_screenshot_max_height}\n"
        f"Going into commercial cooldown: {into_commercial_cooldown_seconds:g}s\n"
        f"Going out of commercial cooldown: {out_of_commercial_cooldown_seconds:g}s\n"
        "Screenshot trim percentages: "
        f"top={screenshot_trim_top_percent:g}, "
        f"right={screenshot_trim_right_percent:g}, "
        f"bottom={screenshot_trim_bottom_percent:g}, "
        f"left={screenshot_trim_left_percent:g}"
    )


async def handle_screenshot(screenshot_bytes):
    global screenshot_version

    print(f"Received screenshot as JPEG: {len(screenshot_bytes)} bytes")

    screenshot_buffer.append(screenshot_bytes)
    screenshot_version += 1

    batch_size = get_active_screenshot_batch_size()
    print(f"Screenshot buffer: {len(screenshot_buffer)}/{batch_size}")

    # We cannot analyze until the first full rolling batch exists.
    if len(screenshot_buffer) < batch_size:
        return

    await maybe_start_analysis()


async def maybe_start_analysis():
    global last_llm_call_time
    global last_analyzed_screenshot_version
    global analysis_task

    batch_size = get_active_screenshot_batch_size()
    if len(screenshot_buffer) < batch_size:
        return

    # Never allow more than one Ollama request at a time.
    if analysis_task and not analysis_task.done():
        return

    # Require at least one newly received screenshot since the previous LLM
    # analysis started. This prevents frequency=0 from re-analyzing the exact
    # same batch repeatedly.
    if screenshot_version <= last_analyzed_screenshot_version:
        return

    # Respect the active state's configured minimum time between call starts.
    now = time.monotonic()
    call_frequency = get_active_llm_call_frequency()

    if now - last_llm_call_time < call_frequency:
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

        # Snapshot values used by this request. If preferences change while the
        # request is running, the result is reported but ignored for state logic.
        selected_model = ollama_model
        selected_context_size = ollama_context_size
        selected_commercial_prompt = commercial_prompt
        selected_non_commercial_prompt = non_commercial_prompt

        decision, llm_response, ai_stats = await ask_ollama_about_transition(
            screenshots,
            state_at_start,
            selected_model,
            selected_context_size,
            selected_commercial_prompt,
            selected_non_commercial_prompt,
        )

        ai_debug_header = build_ai_debug_header(ai_stats)
        full_debug = ai_debug_header + "\n\nAI response:\n" + llm_response

        # Check the Ollama CLI once after the selected model has successfully
        # loaded. This gives the same CPU/GPU split shown by `ollama ps`.
        if not gpu_checked:
            gpu_checked = await warn_if_not_full_gpu(selected_model)

        print(f"Ollama response: {llm_response!r}")
        print(ai_debug_header)

        # A response generated using old preferences is useful for debugging but
        # must not affect the current commercial state or YES streak.
        if preference_version != preference_version_at_start:
            print(
                "Ignoring Ollama response because plugin preferences changed "
                "during analysis"
            )
            await send_status(
                "AI decision ignored because preferences changed",
                full_debug,
            )
            consecutive_yes_count = 0
            return

        # The commercial state may have changed while Ollama was thinking. If
        # so, this answer was produced for the opposite question and is ignored.
        if commercial_state != state_at_start:
            print(
                "Ignoring Ollama response because commercial state changed "
                "during analysis"
            )
            await send_status(
                "AI decision ignored because commercial state changed",
                full_debug,
            )
            consecutive_yes_count = 0
            return

        # Ollama continues running during cooldowns, but every decision is
        # deliberately ignored so it cannot increment/reset the YES streak or
        # trigger another state change too soon.
        cooldown_remaining = get_cooldown_remaining_seconds()
        if cooldown_remaining > 0:
            print(
                f"Ignoring AI decision during state-change cooldown "
                f"({cooldown_remaining:.2f}s remaining)"
            )
            cooldown_display = (
                f"AI decision ignored during cooldown ({cooldown_remaining:.1f}s remaining): "
                f"{decision}"
            )
            if decision == "YES":
                cooldown_display += f" - {llm_response}"

            await send_status(
                cooldown_display,
                full_debug,
            )
            return

        yes_required = get_active_consecutive_yes_required()

        if decision == "YES":
            consecutive_yes_count += 1
        elif decision == "NO":
            # A NO breaks the streak.
            consecutive_yes_count = 0
        else:
            # UNKNOWN neither counts toward nor resets the current YES streak.
            pass

        yes_count = consecutive_yes_count

        print(
            f"Transition answer={decision}; "
            f"consecutive YES count={yes_count}/{yes_required}"
        )
        
        display_question = "is this not commercial" if commercial_state else "is this a commercial"

        # Always send the result of every completed analysis. If the answer is
        # YES, append the entire LLM response to the end of the display.
        status_display = f"AI, {display_question}? AI: {decision} ({yes_count}/{yes_required} YES)"
        if decision == "YES":
            status_display += f" - {llm_response}"

        await send_status(
            status_display,
            full_debug,
        )

        if decision != "YES" or yes_count < yes_required:
            return

        # Enough consecutive YES responses were received. A YES means the
        # desired transition depends on our current state:
        #   regular program -> commercial
        #   commercial      -> regular program
        new_commercial_state = not state_at_start

        # Update immediately so another analysis cannot send the same change
        # again before the extension echoes the confirmed state back.
        commercial_state = new_commercial_state
        consecutive_yes_count = 0
        start_state_change_cooldown(new_commercial_state)

        # The active screenshot batch/frequency/dimensions can change with commercial state.
        resize_screenshot_buffer_for_current_state()

        if new_commercial_state:
            display = "AI detected commercial break"
        else:
            display = "AI detected return to programming"

        # This state change was caused by a YES, so include the complete response
        # at the end of the display as well.
        display += f" - {llm_response}"

        print(f"Sending commercial state change: {new_commercial_state}")
        await send_commercial_state_change(
            new_commercial_state,
            display,
            full_debug,
        )

        # Immediately tell the browser to use the screenshot frequency and
        # dimensions for the newly active state. Shared trim values are included too.
        await request_screenshots()

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(f"Ollama analysis failed: {exc}")

        if websocket is not None:
            context_error = get_context_size_error_details(exc)

            if context_error is not None:
                required_tokens, available_tokens = context_error
                required_text = (
                    f"{required_tokens:,}" if required_tokens is not None else "unknown"
                )
                available_text = (
                    f"{available_tokens:,}" if available_tokens is not None else "unknown"
                )

                await send_status(
                    (
                        "AI request is too large for Ollama's context window. "
                        "Increase the Ollama Context Size preference or reduce the "
                        "screenshot batch size/resolution."
                    ),
                    (
                        "Ollama context-size error\n"
                        f"Request tokens: {required_text}\n"
                        f"Available context: {available_text}\n"
                        f"Configured preference: {format_context_size(ollama_context_size)}\n\n"
                        "If Ollama Context Size is set to Runtime Default, try 8,192 "
                        "or a larger value supported by your model/hardware. You can "
                        "also reduce Screenshot Batch Size or screenshot dimensions.\n\n"
                        f"Original Ollama error: {exc}"
                    ),
                )
            else:
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
    model,
    context_size,
    selected_commercial_prompt,
    selected_non_commercial_prompt,
):
    if currently_commercial:
        question = selected_non_commercial_prompt.strip()
    else:
        question = selected_commercial_prompt.strip()

    options = {
        "temperature": 0,
    }

    # When Runtime Default is selected, do not send num_ctx at all and let
    # Ollama choose its normal runtime context.
    if context_size is not None:
        options["num_ctx"] = context_size

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
        options=options,
    )
    wall_time_seconds = time.monotonic() - call_started

    llm_response = response.message.content.strip()
    decision = parse_yes_no_response(llm_response)

    prompt_tokens = getattr(response, "prompt_eval_count", None)
    response_tokens = getattr(response, "eval_count", None)
    total_tokens = None
    if prompt_tokens is not None and response_tokens is not None:
        total_tokens = prompt_tokens + response_tokens

    ai_stats = {
        "model": model,
        "context_size": context_size,
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

    return decision, llm_response, ai_stats


def parse_yes_no_response(response):
    """Return YES, NO, or UNKNOWN based on the first value in the response."""
    stripped = response.strip()

    if not stripped:
        return "UNKNOWN"

    # Reasons are expected on the same line, e.g.:
    #   YES The screenshots are clearly advertisements.
    # Only the first word/value controls the decision.
    first_value = stripped.split(maxsplit=1)[0]
    cleaned = first_value.upper().strip(" .,!?:;\"'`\n\r\t")

    if cleaned == "YES":
        return "YES"

    if cleaned == "NO":
        return "NO"

    # Anything else is deliberately allowed and treated as UNKNOWN. UNKNOWN
    # neither increments nor resets the consecutive-YES counter.
    return "UNKNOWN"


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
        f"Requested context: {format_context_size(stats['context_size'])}\n"
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


def get_context_size_error_details(exc):
    """Return (required_tokens, available_tokens) for Ollama context overflow errors."""
    error_text = str(exc)
    error_text_lower = error_text.lower()

    if (
        "exceed_context_size_error" not in error_text_lower
        and "exceeds the available context size" not in error_text_lower
    ):
        return None

    required_match = re.search(r'"n_prompt_tokens"\s*:\s*(\d+)', error_text)
    context_match = re.search(r'"n_ctx"\s*:\s*(\d+)', error_text)

    # Fall back to the human-readable message if the JSON fields are unavailable.
    if required_match is None:
        required_match = re.search(r"request \((\d+) tokens\)", error_text, re.IGNORECASE)

    if context_match is None:
        context_match = re.search(
            r"available context size \((\d+) tokens\)",
            error_text,
            re.IGNORECASE,
        )

    required_tokens = int(required_match.group(1)) if required_match else None
    available_tokens = int(context_match.group(1)) if context_match else None

    return required_tokens, available_tokens


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
                        "frequencyMilliseconds": (
                            get_active_screenshot_frequency_milliseconds()
                        ),
                        "maxDimensionsPixels": {
                            "height": get_active_screenshot_max_height(),
                            "width": get_active_screenshot_max_width(),
                        },
                        "trimOptionsPercentages": {
                            "top": screenshot_trim_top_percent,
                            "right": screenshot_trim_right_percent,
                            "bottom": screenshot_trim_bottom_percent,
                            "left": screenshot_trim_left_percent,
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
                        "primaryColor": "#000000",
                        "secondaryColor": "#FFFFFF",
                        "capabilities": [
                            "trigger",
                            "screenshots",
                        ],
                        "preferences": [
                            {
                                "key": "ollama-model",
                                "label": "Ollama Model",
                                "tooltip": (
                                    "Local Ollama model used for screenshot analysis. "
                                    "Only models currently installed in Ollama are listed."
                                ),
                                "type": "select",
                                "options": model_options,
                                "default": model_default,
                            },
                            {
                                "key": "ollama-context-size",
                                "label": "Ollama Context Size",
                                "description": (
                                    "Maximum context window requested from Ollama. Runtime "
                                    "Default does not send num_ctx and lets Ollama decide. "
                                    "Larger values can use more memory."
                                ),
                                "type": "select",
                                "options": [
                                    {"label": "Runtime Default", "value": "runtime-default"},
                                    {"label": "4,096 tokens", "value": "4096"},
                                    {"label": "5K tokens", "value": "5000"},
                                    {"label": "6K tokens", "value": "6000"},
                                    {"label": "7K tokens", "value": "7000"},
                                    {"label": "8,192 tokens", "value": "8192"},
                                    {"label": "12K tokens", "value": "12000"},
                                    {"label": "16,384 tokens", "value": "16384"},
                                    {"label": "32,768 tokens", "value": "32768"},
                                    {"label": "65,536 tokens", "value": "65536"},
                                ],
                                "default": "runtime-default",
                            },
                            {
                                "key": "commercial-prompt",
                                "label": "Commercial Prompt",
                                "tooltip": (
                                    "Prompt used while regular programming is active to "
                                    "decide whether the screenshots indicate a commercial. "
                                    "Try to have answer start with YES or NO."
                                ),
                                "type": "textarea",
                                "default": DEFAULT_COMMERCIAL_PROMPT,
                            },
                            {
                                "key": "non-commercial-prompt",
                                "label": "Non-Commercial Prompt",
                                "tooltip": (
                                    "Prompt used while a commercial is active to decide "
                                    "whether regular programming has returned. "
                                    "Try to have answer start with YES or NO."
                                ),
                                "type": "textarea",
                                "default": DEFAULT_NON_COMMERCIAL_PROMPT,
                            },
                            {
                                "key": "regular-llm-call-frequency-seconds",
                                "label": "Regular Programming LLM Call Frequency (Seconds)",
                                "tooltip": (
                                    "Minimum seconds between Ollama call starts while "
                                    "regular programming is active. Set to 0 to run again "
                                    "as soon as the prior call finishes and fresh screenshots exist."
                                ),
                                "type": "number",
                                "default": DEFAULT_REGULAR_LLM_CALL_FREQUENCY_SECONDS,
                                "min": 0,
                            },
                            {
                                "key": "commercial-llm-call-frequency-seconds",
                                "label": "Commercial LLM Call Frequency (Seconds)",
                                "tooltip": (
                                    "Minimum seconds between Ollama call starts while a "
                                    "commercial is active. Set to 0 to run again as soon as "
                                    "the prior call finishes and fresh screenshots exist."
                                ),
                                "type": "number",
                                "default": DEFAULT_COMMERCIAL_LLM_CALL_FREQUENCY_SECONDS,
                                "min": 0,
                            },
                            {
                                "key": "regular-consecutive-yes-required",
                                "label": "Regular Programming Consecutive YES Responses Required",
                                "tooltip": (
                                    "YES responses required in a row before entering a "
                                    "commercial. NO resets the count; UNKNOWN leaves it unchanged."
                                ),
                                "type": "number",
                                "default": DEFAULT_REGULAR_CONSECUTIVE_YES_REQUIRED,
                                "min": 1,
                            },
                            {
                                "key": "commercial-consecutive-yes-required",
                                "label": "Commercial Consecutive YES Responses Required",
                                "tooltip": (
                                    "YES responses required in a row before returning to "
                                    "regular programming. NO resets the count; UNKNOWN leaves it unchanged."
                                ),
                                "type": "number",
                                "default": DEFAULT_COMMERCIAL_CONSECUTIVE_YES_REQUIRED,
                                "min": 1,
                            },
                            {
                                "key": "regular-screenshot-batch-size",
                                "label": "Regular Programming Screenshot Batch Size",
                                "tooltip": (
                                    "Number of rolling screenshots sent to Ollama while "
                                    "regular programming is active."
                                ),
                                "type": "number",
                                "default": DEFAULT_REGULAR_SCREENSHOT_BATCH_SIZE,
                                "min": 1,
                            },
                            {
                                "key": "commercial-screenshot-batch-size",
                                "label": "Commercial Screenshot Batch Size",
                                "tooltip": (
                                    "Number of rolling screenshots sent to Ollama while a "
                                    "commercial is active."
                                ),
                                "type": "number",
                                "default": DEFAULT_COMMERCIAL_SCREENSHOT_BATCH_SIZE,
                                "min": 1,
                            },
                            {
                                "key": "regular-screenshot-frequency-milliseconds",
                                "label": "Regular Programming Screenshot Frequency (Milliseconds)",
                                "tooltip": (
                                    "How frequently the browser captures screenshots while "
                                    "regular programming is active."
                                ),
                                "type": "number",
                                "default": DEFAULT_REGULAR_SCREENSHOT_FREQUENCY_MILLISECONDS,
                                "min": 1,
                            },
                            {
                                "key": "commercial-screenshot-frequency-milliseconds",
                                "label": "Commercial Screenshot Frequency (Milliseconds)",
                                "tooltip": (
                                    "How frequently the browser captures screenshots while "
                                    "a commercial is active."
                                ),
                                "type": "number",
                                "default": DEFAULT_COMMERCIAL_SCREENSHOT_FREQUENCY_MILLISECONDS,
                                "min": 1,
                            },
                            {
                                "key": "regular-screenshot-max-width",
                                "label": "Regular Programming Screenshot Max Width (Pixels)",
                                "tooltip": (
                                    "Maximum screenshot width while regular programming is active. "
                                    "The extension should preserve the screenshot aspect ratio."
                                ),
                                "type": "number",
                                "default": DEFAULT_REGULAR_SCREENSHOT_MAX_WIDTH,
                                "min": 1,
                            },
                            {
                                "key": "regular-screenshot-max-height",
                                "label": "Regular Programming Screenshot Max Height (Pixels)",
                                "tooltip": (
                                    "Maximum screenshot height while regular programming is active. "
                                    "The extension should preserve the screenshot aspect ratio."
                                ),
                                "type": "number",
                                "default": DEFAULT_REGULAR_SCREENSHOT_MAX_HEIGHT,
                                "min": 1,
                            },
                            {
                                "key": "commercial-screenshot-max-width",
                                "label": "Commercial Screenshot Max Width (Pixels)",
                                "tooltip": (
                                    "Maximum screenshot width while a commercial is active. The "
                                    "extension should preserve the screenshot aspect ratio."
                                ),
                                "type": "number",
                                "default": DEFAULT_COMMERCIAL_SCREENSHOT_MAX_WIDTH,
                                "min": 1,
                            },
                            {
                                "key": "commercial-screenshot-max-height",
                                "label": "Commercial Screenshot Max Height (Pixels)",
                                "tooltip": (
                                    "Maximum screenshot height while a commercial is active. The "
                                    "extension should preserve the screenshot aspect ratio."
                                ),
                                "type": "number",
                                "default": DEFAULT_COMMERCIAL_SCREENSHOT_MAX_HEIGHT,
                                "min": 1,
                            },
                            {
                                "key": "into-commercial-cooldown-seconds",
                                "label": "Going Into Commercial Cooldown (Seconds)",
                                "tooltip": (
                                    "After entering a commercial, AI analysis continues but its "
                                    "decisions are ignored for this many seconds."
                                ),
                                "type": "number",
                                "default": DEFAULT_INTO_COMMERCIAL_COOLDOWN_SECONDS,
                                "min": 0,
                            },
                            {
                                "key": "out-of-commercial-cooldown-seconds",
                                "label": "Going Out of Commercial Cooldown (Seconds)",
                                "tooltip": (
                                    "After returning to regular programming, AI analysis continues "
                                    "but its decisions are ignored for this many seconds."
                                ),
                                "type": "number",
                                "default": DEFAULT_OUT_OF_COMMERCIAL_COOLDOWN_SECONDS,
                                "min": 0,
                            },
                            {
                                "key": "screenshot-trim-top-percent",
                                "label": "Screenshot Trim Top (%)",
                                "tooltip": "Percentage to trim from the top of each screenshot.",
                                "type": "number",
                                "default": DEFAULT_SCREENSHOT_TRIM_TOP_PERCENT,
                                "min": 0,
                                "max": 100,
                            },
                            {
                                "key": "screenshot-trim-right-percent",
                                "label": "Screenshot Trim Right (%)",
                                "tooltip": "Percentage to trim from the right of each screenshot.",
                                "type": "number",
                                "default": DEFAULT_SCREENSHOT_TRIM_RIGHT_PERCENT,
                                "min": 0,
                                "max": 100,
                            },
                            {
                                "key": "screenshot-trim-bottom-percent",
                                "label": "Screenshot Trim Bottom (%)",
                                "tooltip": "Percentage to trim from the bottom of each screenshot.",
                                "type": "number",
                                "default": DEFAULT_SCREENSHOT_TRIM_BOTTOM_PERCENT,
                                "min": 0,
                                "max": 100,
                            },
                            {
                                "key": "screenshot-trim-left-percent",
                                "label": "Screenshot Trim Left (%)",
                                "tooltip": "Percentage to trim from the left of each screenshot.",
                                "type": "number",
                                "default": DEFAULT_SCREENSHOT_TRIM_LEFT_PERCENT,
                                "min": 0,
                                "max": 100,
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
        print("Default Ollama context size: Runtime Default")
        await asyncio.Future()


asyncio.run(main())
