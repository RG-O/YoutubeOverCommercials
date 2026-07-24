
import win32gui
import win32con
import win32api
import pyautogui
import time
import requests
import os
import subprocess
import re
import json

from pathlib import Path
from flask import Flask, request, jsonify

PLUGIN_PROTOCOL_VERSION = 1 # DO NOT TOUCH

PLUGIN_NAME = "VLC Over Commercials"
PLUGIN_ID = "vlc-over-commercials"
PLUGIN_VERSION = "1.0.0"

vlc_http_api_auth = ("", "1234")
my_file_path = "file:///C:/Users/user/Downloads/video.mp4"

SCRIPT_DIR = Path(__file__).resolve().parent
RESUME_FILE = SCRIPT_DIR / "vlc_resume_times.json"

optimized_width_percentage = 90
optimized_height_percentage = 85
has_optimal_demensions_been_captured = False
previous_overlay_video_width_percentage = 0
previous_overlay_video_height_percentage = 0

vlc_process = None
original_forground_window = None
is_original_forground_window_topmost = False
is_setup_complete = False
is_live_video = False
set_volume = 256
set_volume_fallback = 205

def find_window_by_title(partial_title):
    def enum_handler(hwnd, result):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if partial_title in title:
                print(title)
                result.append(hwnd)

    result = []
    win32gui.EnumWindows(enum_handler, result)
    return result[0] if result else None

def find_vlc_exe():
    possible_paths = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    print("Could not find vlc.exe in Program Files or Program Files (x86).")

def open_vlc_with_specific_file(file_path):
    global vlc_http_api_auth
    global vlc_process

    vlc_path = find_vlc_exe()

    vlc_process = subprocess.Popen([
        vlc_path,

        "--qt-start-minimized",
        "--qt-minimal-view",

        "--extraintf", "http",
        "--http-password", "1234",

        "--qt-continue=2", # 2 will resume last watched location automatically

        "--qt-notification=0",   # Never show media change popup
        "--no-video-title-show",
        "--no-qt-privacy-ask",
        "--no-qt-error-dialogs",
        "--no-qt-updates-notif",

        "--no-one-instance", #needed to be able to close later? maybe it doesn't help?
        "--no-one-instance-when-started-from-file", #needed to be able to close later? maybe it doesn't help?

        "--loop", #doing this helps get resume last watched actually work
    ])

    requests.get(
        "http://localhost:8080/requests/status.json",
        params={"command": "in_play", "input": file_path},
        auth=vlc_http_api_auth
    )

def get_vlc_video_dimensions():
    response = requests.get("http://localhost:8080/requests/status.json", auth=vlc_http_api_auth)

    data = response.json()

    print(data)

    categories = data.get("information", {}).get("category", {})

    for stream_name, stream_info in categories.items():
        if not isinstance(stream_info, dict):
            continue

        stream_type = str(stream_info.get("Type", "")).lower()

        if stream_type == "video":
            # VLC often reports this format:
            # "Video_resolution": "1920x1080"
            resolution = (
                stream_info.get("Video_resolution")
                or stream_info.get("Buffer_dimensions")
                or stream_info.get("Resolution")
            )

            if resolution:
                match = re.search(r"(\d+)\s*x\s*(\d+)", str(resolution))
                if match:
                    width = int(match.group(1))
                    height = int(match.group(2))
                    return width, height

            # Fallbacks for other VLC response shapes
            width = stream_info.get("Width") or stream_info.get("width")
            height = stream_info.get("Height") or stream_info.get("height")

            if width and height:
                return int(width), int(height)


def wait_for_vlc_playing(timeout=60):
    start = time.time()

    last_displayed = None

    while time.time() - start < timeout:
        # TODO: move this call to its own function and have fancy timeouts and failure states
        response = requests.get("http://localhost:8080/requests/status.json", auth=vlc_http_api_auth) #TODO: wait/retry if not succesful?
        status = response.json()

        if status["state"] != "playing":
            print("playing false")
            time.sleep(0.2)
            continue

        displayed = status.get("stats", {}).get("displayedpictures", 0)

        if last_displayed is not None and displayed > last_displayed:
            return True

        print("displayed > last_displayed false")
        last_displayed = displayed

        time.sleep(0.2)

    return False


def wait_for_setup_complete(timeout=30):
    if is_setup_complete:
        return True
        
    start = time.time()

    while time.time() - start < timeout:
        time.sleep(0.5)
        
        if is_setup_complete:
            return True
        
    return False


def calculate_largest_aspect_fit(max_width_percent=90, max_height_percent=75):
    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)

    max_width_px = int(screen_width * (max_width_percent / 100))
    max_height_px = int(screen_height * (max_height_percent / 100))

    video_width, video_height = get_vlc_video_dimensions()

    video_aspect = video_width / video_height
    max_box_aspect = max_width_px / max_height_px

    if video_aspect > max_box_aspect:
        # Width is the limiting factor
        final_width_px = max_width_px
        final_height_px = int(final_width_px / video_aspect)
    else:
        # Height is the limiting factor
        final_height_px = max_height_px
        final_width_px = int(final_height_px * video_aspect)

    final_width_percent = (final_width_px / screen_width) * 100
    final_height_percent = (final_height_px / screen_height) * 100

    return final_width_percent, final_height_percent


def is_live_media(status):
    length = status.get("length", 0)
    print("length:")
    print(length)

    # Most true live streams have no known duration.
    if not length or length <= 0:
        return True

    # If the stream reports a duration, it's probably VOD or a local file.
    return False


def position_and_resize_window(
    hwnd,
    width_percent=90,
    height_percent=75,
    vertical="middle",   # "top", "middle", "bottom"
    horizontal="middle"  # "left", "middle", "right"
):
    print("hwnd = ", hwnd, ", ", "width_percent = ", width_percent, ", ", "height_percent = ", height_percent, ", ", "vertical = ", vertical, ", ", "horizontal = ", horizontal, ", ")
    # Get screen resolution
    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)

    # Calculate target size
    target_width = int(screen_width * (width_percent / 100))
    target_height = int(screen_height * (height_percent / 100))

    print("screen_width = ", screen_width, ", ", "screen_height = ", screen_height, ", ", "target_width = ", target_width, ", ", "target_height = ", target_height)

    # Calculate horizontal position
    if horizontal == "left":
        x = 0
    elif horizontal == "right":
        x = screen_width - target_width
    else:  # "middle"
        x = (screen_width - target_width) // 2

    # Calculate vertical position
    if vertical == "top":
        y = 0
    elif vertical == "bottom":
        y = screen_height - target_height
    else:  # "middle"
        y = (screen_height - target_height) // 2

    print("x = ", x, ", ", "y = ", y)

    # Restore/show window without activating it
    win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)

    # Move and resize window
    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST,  # Keeps window above fullscreen apps
        x,
        y,
        target_width,
        target_height,
        win32con.SWP_NOACTIVATE,
    )


def remove_topmost(hwnd, width_percent=90, height_percent=75):
    # Get screen resolution
    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)

    # Calculate target size
    target_width = int(screen_width * (width_percent / 100))
    target_height = int(screen_height * (height_percent / 100))

    # Calculate centered position
    x = (screen_width - target_width) // 2
    y = (screen_height - target_height) // 2

    # removing TOPMOST status so user can easily minimize it, but keeping it on top of the fullscreen browser
    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_BOTTOM,
        x,
        y,
        target_width,
        target_height,
        win32con.SWP_NOACTIVATE,
    )


def minimize_window(hwnd):
    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)


def make_borderless(hwnd):
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)

    # Remove title bar + borders
    style &= ~(
        win32con.WS_CAPTION |
        win32con.WS_THICKFRAME |
        win32con.WS_MINIMIZE |
        win32con.WS_MAXIMIZE |
        win32con.WS_SYSMENU
    )

    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)

    # Apply changes
    win32gui.SetWindowPos(
        hwnd,
        None,
        0, 0, 0, 0,
        win32con.SWP_NOMOVE |
        win32con.SWP_NOSIZE |
        win32con.SWP_NOZORDER |
        win32con.SWP_FRAMECHANGED
    )


def restore_borders(hwnd):
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)

    style |= (
        win32con.WS_CAPTION |
        win32con.WS_THICKFRAME |
        win32con.WS_MINIMIZE |
        win32con.WS_MAXIMIZE |
        win32con.WS_SYSMENU
    )

    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)

    win32gui.SetWindowPos(
        hwnd,
        None,
        0, 0, 0, 0,
        win32con.SWP_FRAMECHANGED |
        win32con.SWP_NOMOVE |
        win32con.SWP_NOSIZE |
        win32con.SWP_NOZORDER
    )


def close_window_by_hwnd(hwnd):
    """
    Try to close the real window gracefully.
    If it does not close, kill the process that owns that window.
    """
    if not hwnd or not win32gui.IsWindow(hwnd):
        return

    # Ask the window to close, same as clicking X
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

app = Flask(__name__)


@app.route("/custom-plugin-overlay-api", methods=["POST"])
def custom_plugin_overlay():
    global vlc_http_api_auth
    global my_file_path
    global has_optimal_demensions_been_captured
    global optimized_width_percentage, optimized_height_percentage
    global previous_overlay_video_width_percentage, previous_overlay_video_height_percentage
    global vlc_process
    global is_setup_complete
    global original_forground_window
    global is_original_forground_window_topmost
    global is_live_video
    global set_volume

    data = request.json
    request_type = data["type"]
    print(request_type)
    preferences = data["data"]["preferences"]
    
    overlay_video_width_percentage = float(preferences["videoOverlayWidth"])
    overlay_video_height_percentage = float(preferences["videoOverlayHeight"])
    overlay_video_location_horizontal = preferences["overlayVideoLocationHorizontal"]
    overlay_video_location_vertical = preferences["overlayVideoLocationVertical"]
    
    is_pip_mode = bool(preferences["isPiPMode"])
    pip_height_percentage = float(preferences["pipHeight"])
    pip_width_percentage = float(preferences["pipWidth"])
    pip_location_horizontal = preferences["pipLocationHorizontal"]
    pip_location_vertical = preferences["pipLocationVertical"]

    if request_type == "commercial_state_change":
        is_commercial = data["data"]["isCommercialState"]
        
        wait_for_setup_complete()

        if is_commercial:
            print("START overlay")
            
            #TODO: somehow globally define hwnd
            window_title = "VLC" 
            hwnd = find_window_by_title(window_title)

            have_demensions_changed = (overlay_video_width_percentage != previous_overlay_video_width_percentage or overlay_video_height_percentage != previous_overlay_video_width_percentage) 

            print(have_demensions_changed)

            previous_overlay_video_width_percentage = overlay_video_width_percentage
            previous_overlay_video_height_percentage = overlay_video_height_percentage

            if have_demensions_changed:
                optimized_width_percentage, optimized_height_percentage = calculate_largest_aspect_fit(max_width_percent=overlay_video_width_percentage, max_height_percent=overlay_video_height_percentage)
                
            position_and_resize_window(hwnd, width_percent=optimized_width_percentage, height_percent=optimized_height_percentage, vertical=overlay_video_location_vertical, horizontal=overlay_video_location_horizontal)
            
            time.sleep(0.1)
            requests.get("http://localhost:8080/requests/status.json?command=pl_forceresume", auth=vlc_http_api_auth)
                
            response = requests.get("http://localhost:8080/requests/status.json", auth=vlc_http_api_auth)
            data = response.json()
                
            if is_live_media(data):
                print("is_live_media is True")
                requests.get(
                    "http://localhost:8080/requests/status.json",
                    params={
                        "command": "volume",
                        "val": set_volume,
                    },
                    auth=vlc_http_api_auth,
                    timeout=3,
                )
            else:
                print("is_live_media is False")

            return jsonify({"status": "ok"})
        else:
            #TODO: somehow globally define hwnd
            window_title = "VLC" 
            hwnd = find_window_by_title(window_title)

            response = requests.get("http://localhost:8080/requests/status.json", auth=vlc_http_api_auth)
            data = response.json()
            set_volume = int(data.get("volume", set_volume_fallback))
            if set_volume == 0:
                set_volume = set_volume_fallback
                
            if is_live_media(data) is False:
                print("is_live_media is False")
                requests.get("http://localhost:8080/requests/status.json?command=pl_forcepause", auth=vlc_http_api_auth)
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            else:
                print("is_live_media is True")
                requests.get(
                    "http://localhost:8080/requests/status.json",
                    params={
                        "command": "volume",
                        "val": 0,
                    },
                    auth=vlc_http_api_auth,
                    timeout=3,
                )
                print("is_pip_mode:")
                print(is_pip_mode)
                if is_pip_mode:
                    pip_optimized_width_percentage, pip_optimized_height_percentage = calculate_largest_aspect_fit(max_width_percent=pip_width_percentage, max_height_percent=pip_height_percentage)
                    position_and_resize_window(hwnd, width_percent=pip_optimized_width_percentage, height_percent=pip_optimized_height_percentage, vertical=pip_location_vertical, horizontal=pip_location_horizontal)
                else:
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                    
            print("STOP overlay")

    elif request_type == "browser_fullscreen_state_change":
        is_fullscreen = data["data"]["isFullscreen"] #TODO: set is_fullscreen earlier (maybe have global variable?) and use it for determining whether to do other things

        window_title = "VLC"
        hwnd = find_window_by_title(window_title)

        if is_fullscreen:
            print("User entered fullscreen on browser")
            make_borderless(hwnd)
        else:
            print("User exited fullscreen on browser")
            
            if original_forground_window is not None and is_original_forground_window_topmost:
                win32gui.SetWindowPos(
                    original_forground_window,
                    win32con.HWND_NOTOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE
                    | win32con.SWP_NOSIZE
                    | win32con.SWP_NOACTIVATE
                )
                
                is_original_forground_window_topmost = False
                
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            time.sleep(0.1)
            remove_topmost(hwnd, width_percent=optimized_width_percentage, height_percent=optimized_height_percentage)
            restore_borders(hwnd)

    elif request_type == "init":
        original_forground_window = win32gui.GetForegroundWindow()
        print(win32gui.GetWindowText(original_forground_window))
            
        my_file_path = preferences["pluginOverlayPreferences"]["preferences"]["url"]
        open_vlc_with_specific_file(my_file_path)
        time.sleep(1) #TODO: better way to wait or not have to wait at all?
        print("waiting for playing")
        wait_for_vlc_playing()
        time.sleep(0.5) #TODO: dynamically wait for video demensions
        print("done waiting for playing")
        window_title = "VLC"
        hwnd = find_window_by_title(window_title)
        if hwnd is None:
            return jsonify({"status": "error", "message": "VLC could not be opened."})
        make_borderless(hwnd)

        time.sleep(0.2)

        position_and_resize_window(hwnd, width_percent=10, height_percent=10) # Force to bring forward now to get annoying taskbar showing out of the way early
        time.sleep(0.2)
            
        response = requests.get("http://localhost:8080/requests/status.json", auth=vlc_http_api_auth)
        data = response.json()
        set_volume = int(data.get("volume", set_volume_fallback))
        if set_volume == 0:
            set_volume = set_volume_fallback
                
        if is_live_media(data) is False:
            requests.get("http://localhost:8080/requests/status.json?command=pl_forcepause", auth=vlc_http_api_auth)
            time.sleep(0.2)
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            time.sleep(0.2)
            position_and_resize_window(hwnd, width_percent=10, height_percent=10) # need to bring this back and away a second time to clear out the taskbar for windows 10
            time.sleep(0.2)
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            time.sleep(0.2)
                
            if original_forground_window is not None:
                time.sleep(0.4)

                win32gui.SetWindowPos(
                    original_forground_window,
                    win32con.HWND_TOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE |
                    win32con.SWP_NOSIZE |
                    win32con.SWP_NOOWNERZORDER
                ) # doing this to clear out the taskbar for windows 11
                
                is_original_forground_window_topmost = True
                
        else:
            requests.get(
                "http://localhost:8080/requests/status.json",
                params={
                    "command": "volume",
                    "val": 0,
                },
                auth=vlc_http_api_auth,
                timeout=3,
            )
            print("is_pip_mode:")
            print(is_pip_mode)
            if is_pip_mode:
                pip_optimized_width_percentage, pip_optimized_height_percentage = calculate_largest_aspect_fit(max_width_percent=pip_width_percentage, max_height_percent=pip_height_percentage)
                position_and_resize_window(hwnd, width_percent=pip_optimized_width_percentage, height_percent=pip_optimized_height_percentage, vertical=pip_location_vertical, horizontal=pip_location_horizontal)
            else:
                time.sleep(0.2)
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                time.sleep(0.2)
                position_and_resize_window(hwnd, width_percent=10, height_percent=10) # need to bring this back and away a second time to clear out the taskbar for windows 10
                time.sleep(0.2)
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                time.sleep(0.2)

                if original_forground_window is not None:
                    time.sleep(0.4)

                    win32gui.SetWindowPos(
                        original_forground_window,
                        win32con.HWND_TOPMOST,
                        0, 0, 0, 0,
                        win32con.SWP_NOMOVE |
                        win32con.SWP_NOSIZE |
                        win32con.SWP_NOOWNERZORDER
                    ) # doing this to clear out the taskbar for windows 11
                
                    is_original_forground_window_topmost = True
            
                
        is_setup_complete = True

        return jsonify({"status": "info", "message": "Message from VLC Over Commercials plugin: Success! Click in this window to return focus and you are good to go!"})

    elif request_type == "end":
        if original_forground_window is not None and is_original_forground_window_topmost:
            win32gui.SetWindowPos(
                original_forground_window,
                win32con.HWND_NOTOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE
                | win32con.SWP_NOSIZE
                | win32con.SWP_NOACTIVATE
            )
            
            is_original_forground_window_topmost = False
        
        #TODO: somhow globally define hwnd
        window_title = "VLC" 
        hwnd = find_window_by_title(window_title)

        remove_topmost(hwnd, width_percent=optimized_width_percentage, height_percent=optimized_height_percentage)
        restore_borders(hwnd)

        response = requests.get("http://localhost:8080/requests/status.json", auth=vlc_http_api_auth)
        data = response.json()
                
        if is_live_media(data):
            print("is_live_media is True")
            requests.get(
                "http://localhost:8080/requests/status.json",
                params={
                    "command": "volume",
                    "val": set_volume,
                },
                auth=vlc_http_api_auth,
                timeout=3,
            )
        else:
            print("is_live_media is False")

        requests.get("http://localhost:8080/requests/status.json?command=pl_stop", auth=vlc_http_api_auth) #TODO: should use quit?
        close_window_by_hwnd(hwnd)

        if vlc_process and vlc_process.poll() is None:
            vlc_process.terminate()
            print("vlc_process.terminate()")

        print("Extension Stopped")

    return jsonify({"status": "ok"})

@app.route("/plugin-manifest", methods=["GET"])
def plugin_manifest():
    return jsonify({
        "type": "plugin_manifest",
        "timestamp": time.time(),
        "pluginProtocolVersion": PLUGIN_PROTOCOL_VERSION,
        "data": {
            "name": PLUGIN_NAME,
            "id": PLUGIN_ID,
            "version": PLUGIN_VERSION,
            "description": "This plugin will automatically play VLC(TM) over commercials. Have latest version of VLC installed and closed before initiating. VLC is a trademark of the VideoLAN organization. This plugin is not affiliated with VLC or VideoLAN.", #TODO: Update this.
            "primaryColor": "#E85E00",
            "secondaryColor": "#f2c7aa",
            "capabilities": ["overlay"],
            "preferences": [
                {
                    "key": "url",
                    "label": "Video URL",
                    "description": "This can be a show/movie stream URL, live stream URL, or a local file URL (E.g. file:///C:/Users/user/Downloads/video.mp4)",
                    "type": "text",
                    "default": "https://upload.wikimedia.org/wikipedia/commons/8/88/Big_Buck_Bunny_alt.webm",
                }
            ]
        }
        
    })

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "alive"})

if __name__ == "__main__":
    print("API running on http://localhost:64144")
    app.run(port=64144)
