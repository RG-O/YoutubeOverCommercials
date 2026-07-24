
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

is_vlc_http_api_control_mode = True
vlc_http_api_auth = ("", "1234")
my_file_path = "file:///C:/Users/user/Downloads/video.mp4"

#RESUME_FILE = Path("vlc_resume_times.json")
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
        #file_path, #todo: better or worse to open this way?

        # Main UI/interface: no normal VLC window controls
        #"--intf", "dummy",
        "--qt-start-minimized",
        "--qt-minimal-view",

        # Still enable HTTP remote control
        "--extraintf", "http",
        "--http-password", "1234",

        "--qt-continue=2", # 2 will resume last watched location automatically? 1 will prompt?

        # Optional quality-of-life flags
        "--qt-notification=0",   # Never show media change popup
        "--no-video-title-show",
        "--no-qt-privacy-ask",
        "--no-qt-error-dialogs",
        "--no-qt-updates-notif",

        "--no-one-instance", #needed to be able to close later? maybe it doesn't help?
        "--no-one-instance-when-started-from-file", #needed to be able to close later? maybe it doesn't help?

        #"--qt-pause-minimized=1", #pause when minimized. or maybe just "--qt-pause-minimized"
        "--loop", #doing this helps get resume last watched actually work
    ])

    requests.get(
        "http://localhost:8080/requests/status.json",
        params={"command": "in_play", "input": file_path},
        auth=vlc_http_api_auth
    )

def get_vlc_video_dimensions():
    # url = f"http://{vlc_host}:{vlc_port}/requests/status.json"

    # response = requests.get(url, auth=("", vlc_password), timeout=3)
    # response.raise_for_status()

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
        # TODO: move this two its own function and have fancy timeouts and failure states
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


def get_vlc_current_time():
    """
    Returns current playback time in seconds from VLC.
    Returns 0 if anything fails.
    """
    try:
        response = requests.get(
            "http://localhost:8080/requests/status.json",
            auth=vlc_http_api_auth,
            timeout=3
        )

        response.raise_for_status()

        return int(response.json().get("time", 0))

    except Exception:
        return 0


def save_video_resume_time(video_path):
    """
    Saves VLC's current playback position for video_path.
    Safe to call immediately before closing VLC.
    """

    try:
        current_time = get_vlc_current_time()

        try:
            with open(RESUME_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

        data[str(Path(video_path).resolve())] = current_time

        with open(RESUME_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    except Exception:
        pass


def get_saved_resume_time(video_path):
    """
    Returns previously saved resume time.
    Returns 0 if:
      - file doesn't exist
      - entry doesn't exist
      - anything fails
    """

    try:
        with open(RESUME_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return int(
            data.get(
                str(Path(video_path).resolve()),
                0
            )
        )

    except Exception:
        return 0


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
    # win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
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

    #time.sleep(0.05) #TODO: is this necessary?


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
        #win32con.HWND_TOPMOST,  # Always on top #TODO: remove?
        #win32con.HWND_TOP,
        #win32con.HWND_NOTOPMOST, 
        win32con.HWND_BOTTOM,
        x,
        y,
        target_width,
        target_height,
        win32con.SWP_NOACTIVATE, #TODO: bring other one back?
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


def send_ctrl_h(hwnd):
    # Press CTRL down
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_CONTROL, 0)

    # Press H down
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, ord('H'), 0)

    time.sleep(0.05)

    # Release H
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, ord('H'), 0)

    # Release CTRL
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_CONTROL, 0)


def send_spacebar(hwnd):
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, 0x20, 0)  # spacebar down
    time.sleep(0.05)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, 0x20, 0)  # spacebar up

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
    global is_vlc_http_api_control_mode
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
    
    #is_fullscreen = data["data"].get("isFullscreen", False)

    overlay_video_width_percentage = float(preferences["videoOverlayWidth"])
    overlay_video_height_percentage = float(preferences["videoOverlayHeight"])
    overlay_video_location_horizontal = preferences["overlayVideoLocationHorizontal"]
    overlay_video_location_vertical = preferences["overlayVideoLocationVertical"]
    
    is_pip_mode = bool(preferences["overlayVideoLocationVertical"])
    pip_height_percentage = float(preferences["pipHeight"])
    pip_width_percentage = float(preferences["pipWidth"])
    pip_location_horizontal = preferences["pipLocationHorizontal"]
    pip_location_vertical = preferences["pipLocationVertical"]

    if request_type == "commercial_state_change":
        is_commercial = data["data"]["isCommercialState"]
        
        wait_for_setup_complete()

        if is_commercial:
            print("START overlay")
            #TODO: somhow globally define hwnd
            window_title = "VLC"  # Change this to your target window
            hwnd = find_window_by_title(window_title)

            have_demensions_changed = (overlay_video_width_percentage != previous_overlay_video_width_percentage or overlay_video_height_percentage != previous_overlay_video_width_percentage) 

            print(have_demensions_changed)

            previous_overlay_video_width_percentage = overlay_video_width_percentage
            previous_overlay_video_height_percentage = overlay_video_height_percentage

            if have_demensions_changed:
                optimized_width_percentage, optimized_height_percentage = calculate_largest_aspect_fit(max_width_percent=overlay_video_width_percentage, max_height_percent=overlay_video_height_percentage)
                
            position_and_resize_window(hwnd, width_percent=optimized_width_percentage, height_percent=optimized_height_percentage, vertical=overlay_video_location_vertical, horizontal=overlay_video_location_horizontal)
            
            if is_vlc_http_api_control_mode:
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
            else:
                time.sleep(0.5)
                send_spacebar(hwnd)


            return jsonify({"status": "ok"})
        else:
            #TODO: somhow globally define hwnd
            window_title = "VLC"  # Change this to your target window
            hwnd = find_window_by_title(window_title)
            if is_vlc_http_api_control_mode:
                response = requests.get("http://localhost:8080/requests/status.json", auth=vlc_http_api_auth)
                data = response.json()
                set_volume = int(data.get("volume", 80))
                
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
                    if is_pip_mode:
                        pip_optimized_width_percentage, pip_optimized_height_percentage = calculate_largest_aspect_fit(max_width_percent=pip_width_percentage, max_height_percent=pip_height_percentage)
                        position_and_resize_window(hwnd, width_percent=pip_optimized_width_percentage, height_percent=pip_optimized_height_percentage, vertical=pip_location_vertical, horizontal=pip_location_horizontal)
                    
                #time.sleep(0.2)
            else:
                send_spacebar(hwnd)
                time.sleep(1)
            
            print("STOP overlay")

    elif request_type == "browser_fullscreen_state_change":
        is_fullscreen = data["data"]["isFullscreen"]

        window_title = "VLC"  # Change this to your target window
        hwnd = find_window_by_title(window_title)

        if is_fullscreen:
            print("User entered fullscreen on browser")
            make_borderless(hwnd)
        else:
            print("User exited fullscreen on browser")
            
            if original_forground_window is not None and is_original_forground_window_topmost:
                win32gui.SetWindowPos(
                    original_forground_window,
                    #win32con.HWND_TOPMOST,
                    win32con.HWND_NOTOPMOST,
                    #win32con.HWND_TOP,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE |
                    win32con.SWP_NOSIZE #|
                    #win32con.SWP_NOOWNERZORDER
                    | win32con.SWP_NOACTIVATE
                )
                
                is_original_forground_window_topmost = False
                
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            time.sleep(0.1)
            remove_topmost(hwnd, width_percent=optimized_width_percentage, height_percent=optimized_height_percentage)
            restore_borders(hwnd)

    elif request_type == "init":
        print("init")
        if is_vlc_http_api_control_mode:
            original_forground_window = win32gui.GetForegroundWindow()
            print(win32gui.GetWindowText(original_forground_window))
            
            #TODO: Do I keep or remove this? I think I'm leaning towards remove since I do it later for non live and it shows the user what is happening instead of the quick flash of the taskbar which looks glitchy
            # if original_forground_window is not None:
            #     win32gui.SetWindowPos(
            #         original_forground_window,
            #         win32con.HWND_TOPMOST,
            #         #win32con.HWND_NOTOPMOST,
            #         #win32con.HWND_TOP,
            #         0, 0, 0, 0,
            #         win32con.SWP_NOMOVE |
            #         win32con.SWP_NOSIZE #|
            #         #win32con.SWP_NOOWNERZORDER
            #         | win32con.SWP_NOACTIVATE
            #     )
                
            #     is_original_forground_window_topmost = True
                
            #     time.sleep(0.4)
                

                
            my_file_path = preferences["pluginOverlayPreferences"]["preferences"]["url"]
            open_vlc_with_specific_file(my_file_path)
            #requests.get("http://localhost:8080/requests/status.json?command=pl_forcepause", auth=vlc_http_api_auth)
            time.sleep(1) #todo: better way to wait or not have to wait at all?
            print("waiting for playing")
            wait_for_vlc_playing()
            time.sleep(0.5) #TODO: dynamically wait for video demensions
            print("done waiting for playing")
            window_title = "VLC"  # Change this to your target window
            hwnd = find_window_by_title(window_title)
            if hwnd is None:
                return jsonify({"status": "error", "error": "No VLC window found."}) #TODO: update message
            make_borderless(hwnd)
            #print("Extension Initiated. Tip: Click on VLC and hit Ctrl + H to hide VLC UI")

            time.sleep(0.2)

            position_and_resize_window(hwnd, width_percent=10, height_percent=10) # Force to bring forward now to get annoying taskbar showing out of the way early #TODO: figure this out for windows 11
            time.sleep(0.2) #todo: better way to wait or not have to wait at all?
            # resume_seconds = get_saved_resume_time(my_file_path)
            # requests.get(
            #     "http://localhost:8080/requests/status.json",
            #     params={"command": "seek", "val": resume_seconds},
            #     auth=vlc_http_api_auth
            # )
            #time.sleep(2) #todo: better way to wait or not have to wait at all?
            
            response = requests.get("http://localhost:8080/requests/status.json", auth=vlc_http_api_auth)
            data = response.json()
            set_volume = int(data.get("volume", 80))
                
            if is_live_media(data) is False:
                requests.get("http://localhost:8080/requests/status.json?command=pl_forcepause", auth=vlc_http_api_auth)
                time.sleep(0.2)
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE) #TODO: maybe do have everything show at the beginging and do this?
                time.sleep(0.2)
                
                if original_forground_window is not None:
                    time.sleep(0.4)

                    win32gui.SetWindowPos(
                        original_forground_window,
                        win32con.HWND_TOPMOST,
                        #win32con.HWND_NOTOPMOST,
                        #win32con.HWND_TOP,
                        0, 0, 0, 0,
                        win32con.SWP_NOMOVE |
                        win32con.SWP_NOSIZE |
                        win32con.SWP_NOOWNERZORDER
                    )
                
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
                if is_pip_mode:
                    pip_optimized_width_percentage, pip_optimized_height_percentage = calculate_largest_aspect_fit(max_width_percent=pip_width_percentage, max_height_percent=pip_height_percentage)
                    position_and_resize_window(hwnd, width_percent=pip_optimized_width_percentage, height_percent=pip_optimized_height_percentage, vertical=pip_location_vertical, horizontal=pip_location_horizontal)
            
                
            is_setup_complete = True

            return jsonify({"status": "info", "message": "Message from VLC Over Commercials plugin: Success! Click in this window to return focus and you are good to go!"})

        print(data)

    elif request_type == "end":
        #TODO: somhow globally define hwnd
        
        if original_forground_window is not None and is_original_forground_window_topmost:
            win32gui.SetWindowPos(
                original_forground_window,
                #win32con.HWND_TOPMOST,
                win32con.HWND_NOTOPMOST,
                #win32con.HWND_TOP,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE |
                win32con.SWP_NOSIZE #|
                #win32con.SWP_NOOWNERZORDER
                | win32con.SWP_NOACTIVATE
            )
            
            is_original_forground_window_topmost = False
        
        window_title = "VLC"  # Change this to your target window
        hwnd = find_window_by_title(window_title)
        remove_topmost(hwnd, width_percent=optimized_width_percentage, height_percent=optimized_height_percentage)
        restore_borders(hwnd)


        if is_vlc_http_api_control_mode:
            
            if is_vlc_http_api_control_mode:
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
            else:
                time.sleep(0.5)
                send_spacebar(hwnd)
                
            save_video_resume_time(my_file_path)
            requests.get("http://localhost:8080/requests/status.json?command=pl_stop", auth=vlc_http_api_auth) #todo: should use quit?
            close_window_by_hwnd(hwnd)
            #TODO: do I use this instead? or both?
            if vlc_process and vlc_process.poll() is None:
                vlc_process.terminate()
                print("vlc_process.terminate()")
            #TODO: close and capture stop time?

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
                    "description": "This can be a stream URL or a local file URL (E.g. file:///C:/Users/user/Downloads/video.mp4)",
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
