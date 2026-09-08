import asyncio
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import websockets


PLUGIN_PROTOCOL_VERSION = 1  # DO NOT TOUCH

PLUGIN_NAME = "Commercial Push Notifications"
PLUGIN_ID = "ntfy-commercial-notifications"  # Must be unique
PLUGIN_VERSION = "1.0.0"

PORT = 64146

clients = set()


async def handle_client(websocket):
    print("Client connected")
    clients.add(websocket)

    try:
        async for message in websocket:
            try:
                # Messages from the extension should be JSON.
                msg = json.loads(message)
                await handle_message(websocket, msg)

            except json.JSONDecodeError as error:
                print("Received invalid JSON:", error)

                await send_status(
                    websocket,
                    "Plugin received an invalid message",
                    f"Could not decode the message as JSON: {error}",
                    display_type="error",
                )

            except Exception as error:
                # Catch unexpected message-processing errors so the plugin
                # stays running instead of crashing.
                print("Error while handling message:", error)

                await send_status(
                    websocket,
                    "Plugin message error",
                    f"An unexpected error occurred while handling a message: {error}",
                    display_type="error",
                )

    except websockets.exceptions.ConnectionClosed:
        pass

    except Exception as error:
        print("WebSocket error:", error)

    finally:
        clients.discard(websocket)
        print("Client disconnected")


async def handle_message(ws, msg):
    # Make sure the message contains the fields we expect.
    if not isinstance(msg, dict):
        await send_status(
            ws,
            "Invalid plugin message",
            "The message received from the extension was not a JSON object.",
            display_type="error",
        )
        return

    message_type = msg.get("type")

    if not message_type:
        await send_status(
            ws,
            "Invalid plugin message",
            "The message did not contain a 'type' field.",
            display_type="error",
        )
        return

    data = msg.get("data", {})

    if not isinstance(data, dict):
        data = {}

    preferences = data.get("preferences", {})

    if not isinstance(preferences, dict):
        preferences = {}

    # Plugin settings are keyed by the plugin's own ID so another plugin
    # can never overwrite them.
    custom_overlay_plugin_preferences = (
        preferences
        .get("pluginPreferencesById", {})
        .get(PLUGIN_ID, {})
        .get("preferences", {})
    )

    if not isinstance(custom_overlay_plugin_preferences, dict):
        custom_overlay_plugin_preferences = {}

    if message_type == "plugin_manifest":
        print("Plugin Manifest Requested. Sending Manifest.")
        await send_manifest(ws)
        return

    if message_type == "init":
        print("Extension initiated")
        print("Full message:")
        print(msg)
        print("Full preferences:")
        print(preferences)
        print("Your custom requested plugin preferences:")
        print(custom_overlay_plugin_preferences)

        topic = custom_overlay_plugin_preferences.get("ntfy-topic", "").strip()

        if not topic:
            await send_status(
                ws,
                "ntfy topic is not set",
                "Enter an ntfy topic in the plugin preferences before notifications can be sent.",
                display_type="error",
            )
        else:
            await send_status(
                ws,
                "ntfy notifications ready",
                f"Connected and ready to send notifications to ntfy topic '{topic}'.",
            )

    elif message_type == "commercial_state_change":
        is_commercial = data.get("isCommercialState")

        utilities = data.get("utilities", {})
        if not isinstance(utilities, dict):
            utilities = {}

        commercial_state_trigger = utilities.get(
            "triggerOfLastCommercialStateChange"
        )

        print(
            "Commercial state change. is_commercial =",
            is_commercial,
            ", commercial_state_trigger =",
            commercial_state_trigger,
        )

        if is_commercial is True:
            # Commercials just started.
            should_notify = custom_overlay_plugin_preferences.get(
                "notify-commercial-start",
                True,
            )

            if should_notify:
                title = custom_overlay_plugin_preferences.get(
                    "commercial-start-title",
                    "Commercial Break Started",
                )

                description = custom_overlay_plugin_preferences.get(
                    "commercial-start-description",
                    "A commercial break has started.",
                )

                await send_ntfy_notification(
                    ws,
                    custom_overlay_plugin_preferences,
                    title,
                    description,
                    notification_name="commercial start",
                )

        elif is_commercial is False:
            # Commercials just ended.
            should_notify = custom_overlay_plugin_preferences.get(
                "notify-commercial-end",
                True,
            )

            if should_notify:
                title = custom_overlay_plugin_preferences.get(
                    "commercial-end-title",
                    "Commercial Break Ended",
                )

                description = custom_overlay_plugin_preferences.get(
                    "commercial-end-description",
                    "The commercial break has ended.",
                )

                await send_ntfy_notification(
                    ws,
                    custom_overlay_plugin_preferences,
                    title,
                    description,
                    notification_name="commercial end",
                )

        else:
            # This should normally never happen, but it is safer to handle it.
            await send_status(
                ws,
                "Invalid commercial state received",
                (
                    "The commercial_state_change message did not contain "
                    "a valid True or False isCommercialState value."
                ),
                display_type="error",
            )

    elif message_type == "browser_fullscreen_state_change":
        is_fullscreen = data.get("isFullscreen")

        print(
            "Fullscreen state changed on browser. is_fullscreen =",
            is_fullscreen,
        )


async def send_ntfy_notification(
    ws,
    plugin_preferences,
    title,
    description,
    notification_name,
):
    """
    Validate the ntfy settings and send a notification.

    The actual HTTP request is run in another thread using asyncio.to_thread().
    This prevents a slow ntfy server from blocking the plugin's WebSocket.
    """

    topic = str(
        plugin_preferences.get("ntfy-topic", "")
    ).strip()

    server = str(
        plugin_preferences.get("ntfy-server", "https://ntfy.sh")
    ).strip()

    title = str(title or "")
    description = str(description or "")

    # Make sure a topic was entered.
    if not topic:
        await send_status(
            ws,
            "Could not send ntfy notification",
            (
                f"The {notification_name} notification was not sent because "
                "the ntfy topic is empty. Enter a topic in the plugin preferences."
            ),
            display_type="error",
        )
        return

    # Make sure a server was entered.
    if not server:
        await send_status(
            ws,
            "Could not send ntfy notification",
            (
                f"The {notification_name} notification was not sent because "
                "the ntfy server is empty."
            ),
            display_type="error",
        )
        return

    # Add https:// if somebody enters something like "ntfy.sh".
    if not server.startswith(("http://", "https://")):
        server = "https://" + server

    # Remove a trailing slash so we don't create a URL containing "//".
    server = server.rstrip("/")

    # URL-encode the topic in case it contains characters that need escaping.
    encoded_topic = urllib.parse.quote(topic, safe="")

    notification_url = f"{server}/{encoded_topic}"

    print(f"Sending {notification_name} ntfy notification")
    print("Server:", server)
    print("Topic:", topic)
    print("Title:", title)
    print("Description:", description)

    try:
        # urllib is a blocking library, so run it in another thread.
        response_code = await asyncio.to_thread(
            send_ntfy_http_request,
            notification_url,
            title,
            description,
        )

        print(
            f"ntfy {notification_name} notification sent. "
            f"HTTP status: {response_code}"
        )

        await send_status(
            ws,
            f"ntfy notification sent: {title}",
            (
                f"Successfully sent the {notification_name} notification "
                f"to topic '{topic}'. HTTP status: {response_code}"
            ),
        )

    except urllib.error.HTTPError as error:
        # ntfy responded, but with an HTTP error such as 400, 401, 403, etc.
        error_body = ""

        try:
            error_body = error.read().decode("utf-8", errors="replace")
        except Exception:
            pass

        debug_message = (
            f"ntfy returned HTTP {error.code} {error.reason} while sending "
            f"the {notification_name} notification."
        )

        if error_body:
            debug_message += f" Response: {error_body}"

        print(debug_message)

        await send_status(
            ws,
            f"ntfy error: HTTP {error.code}",
            debug_message,
            display_type="error",
        )

    except urllib.error.URLError as error:
        # Usually DNS problems, server unavailable, refused connection, etc.
        debug_message = (
            f"Could not connect to the ntfy server '{server}' while sending "
            f"the {notification_name} notification. Error: {error.reason}"
        )

        print(debug_message)

        await send_status(
            ws,
            "Could not connect to ntfy",
            debug_message,
            display_type="error",
        )

    except TimeoutError:
        debug_message = (
            f"The ntfy server '{server}' took too long to respond while "
            f"sending the {notification_name} notification."
        )

        print(debug_message)

        await send_status(
            ws,
            "ntfy request timed out",
            debug_message,
            display_type="error",
        )

    except Exception as error:
        # Catch anything unexpected so a notification problem cannot crash
        # the whole plugin.
        debug_message = (
            f"An unexpected error occurred while sending the "
            f"{notification_name} ntfy notification: {error}"
        )

        print(debug_message)

        await send_status(
            ws,
            "Could not send ntfy notification",
            debug_message,
            display_type="error",
        )


def send_ntfy_http_request(notification_url, title, description):
    """
    Send the actual HTTP POST request to ntfy.

    This is a normal synchronous function because it is called with
    asyncio.to_thread() above.
    """

    # ntfy uses the request body as the notification message.
    body = description.encode("utf-8")

    headers = {
        "Title": title,
        "Content-Type": "text/plain; charset=utf-8",
        "User-Agent": f"{PLUGIN_ID}/{PLUGIN_VERSION}",
    }

    request = urllib.request.Request(
        notification_url,
        data=body,
        headers=headers,
        method="POST",
    )

    # The timeout prevents a bad/unavailable server from hanging forever.
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status


async def send_status(
    ws,
    display,
    debug,
    display_type="info",
    display_time=7000,
):
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
                        "displayType": display_type,
                        # Time until the message disappears.
                        "displayTime": display_time,
                        "debug": debug,
                    },
                }
            )
        )

    except websockets.exceptions.ConnectionClosed:
        print("send_status send stopped: client disconnected")

    except Exception as error:
        # There is nowhere else to report this error if send_status itself
        # fails, so just print it instead of crashing the plugin.
        print("Could not send plugin status:", error)


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
                            "Sends ntfy notifications when commercial breaks "
                            "start and end. Download the ntfy app on your phone "
                            "and subscribe to your topic."
                        ),
                        "primaryColor": "#317f6f",
                        "secondaryColor": "#ffffff",
                        "capabilities": ["overlay"],
                        "preferences": [
                            {
                                "key": "ntfy-topic",
                                "label": "ntfy Topic",
                                "description": "Must be unique! Try to not match anybody else's in the world.",
                                "tooltip": (
                                    "The ntfy topic that should receive the "
                                    "commercial notifications."
                                ),
                                "type": "text",
                                "default": "",
                            },
                            {
                                "key": "ntfy-server",
                                "label": "ntfy Server",
                                "tooltip": (
                                    "The ntfy server to send notifications to. "
                                    "Leave this at the default when using the "
                                    "public ntfy service."
                                ),
                                "type": "text",
                                "default": "https://ntfy.sh",
                            },
                            {
                                "key": "notify-commercial-start",
                                "label": "Notify When Commercials Start",
                                "tooltip": (
                                    "Send an ntfy notification when a commercial "
                                    "break begins."
                                ),
                                "type": "checkbox",
                                "default": True,
                            },
                            {
                                "key": "commercial-start-title",
                                "label": "Commercial Start Notification Title",
                                "tooltip": (
                                    "The title used for the notification when "
                                    "commercials begin."
                                ),
                                "type": "text",
                                "default": "Commercial Break Started",
                            },
                            {
                                "key": "commercial-start-description",
                                "label": "Commercial Start Notification Description",
                                "tooltip": (
                                    "The message shown in the notification when "
                                    "commercials begin."
                                ),
                                "type": "textarea",
                                "default": "A commercial break has started.",
                            },
                            {
                                "key": "notify-commercial-end",
                                "label": "Notify When Commercials End",
                                "tooltip": (
                                    "Send an ntfy notification when a commercial "
                                    "break ends."
                                ),
                                "type": "checkbox",
                                "default": True,
                            },
                            {
                                "key": "commercial-end-title",
                                "label": "Commercial End Notification Title",
                                "tooltip": (
                                    "The title used for the notification when "
                                    "commercials end."
                                ),
                                "type": "text",
                                "default": "Commercial Break Ended",
                            },
                            {
                                "key": "commercial-end-description",
                                "label": "Commercial End Notification Description",
                                "tooltip": (
                                    "The message shown in the notification when "
                                    "commercials end."
                                ),
                                "type": "textarea",
                                "default": "The commercial break has ended.",
                            },
                        ],
                    },
                    "meta": {
                        "display": "Sending Manifest",
                        "debug": "Sending ntfy Commercial Notifications manifest",
                    },
                }
            )
        )

    except websockets.exceptions.ConnectionClosed:
        print("send_manifest stopped: client disconnected")

    except Exception as error:
        print("Could not send plugin manifest:", error)


async def main():
    try:
        async with websockets.serve(handle_client, "localhost", PORT):
            print(f"{PLUGIN_NAME} v{PLUGIN_VERSION}")
            print(f"Server running on ws://localhost:{PORT}")
            print("Press Ctrl+C to stop.")
            await asyncio.Future()

    except OSError as error:
        # A common example is that another program is already using PORT.
        print()
        print("Could not start the WebSocket server.")
        print(f"Error: {error}")
        print()
        print(
            f"Make sure another program is not already using port {PORT}."
        )

    except Exception as error:
        print()
        print("The plugin could not start.")
        print(f"Error: {error}")


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print()
        print("Plugin stopped.")