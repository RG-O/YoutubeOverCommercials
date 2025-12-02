
"""
Advanced Logo Analyzer - Flask service

This module exposes two endpoints used by the consuming app:
 - POST /advanced-logo-analysis
 - GET  /ping-advanced-logo-analysis
"""


import base64
import os
import sys
import threading
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from flask import Flask, jsonify, request
from PIL import Image
import pystray
from pystray import Menu as menu, MenuItem as item

__version__ = "1.0"
PORT = 64143

app = Flask(__name__)

# -----------------------------------------------------------------------------
# Global state
# -----------------------------------------------------------------------------
logo_edges: List[np.ndarray] = []
avg_edge_mask: Optional[np.ndarray] = None

logo_edges_from_eroded: List[np.ndarray] = []
avg_edge_mask_from_eroded: Optional[np.ndarray] = None

color_imgs: List[np.ndarray] = []
avg_color_img: Optional[np.ndarray] = None

contours: List[np.ndarray] = []

# Defensive defaults so later comparisons won't raise NameError if mask hasn't
# been built yet. The consuming app should call "build-mask-first" or equivalent
# before relying on detection, but we avoid crashes.
avg_edge_mask_boolean_mask: np.ndarray = np.zeros((1, 1), dtype=bool)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def image_to_base64(img_np: np.ndarray) -> str:
    """Encode a numpy image (H x W x C) or (H x W) to a PNG data URL."""
    img_pil = Image.fromarray(img_np)
    buf = BytesIO()
    img_pil.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def decode_request_image(data_url: str) -> Tuple[np.ndarray, np.ndarray]:
    """
    Decode an incoming 'data:image/...;base64,...' string into two representations:
      - gray_np: single-channel uint8 grayscale (used for edge detection)
      - color_bgr: 3-channel BGR uint8 (OpenCV native ordering)
    """
    b64 = data_url.split(",", 1)[1]
    img_bytes = base64.b64decode(b64)

    # PIL grayscale (preserve aspect and single channel)
    pil_gray = Image.open(BytesIO(img_bytes)).convert("L")
    gray_np = np.array(pil_gray)

    # cv2 decode to get BGR image (preserves colors)
    buf = np.frombuffer(img_bytes, dtype=np.uint8)
    color_bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if color_bgr is None:
        # Fallback: convert PIL RGB to BGR if decoding failed
        pil_rgb = Image.open(BytesIO(img_bytes)).convert("RGB")
        color_rgb = np.array(pil_rgb)
        color_bgr = cv2.cvtColor(color_rgb, cv2.COLOR_RGB2BGR)

    return gray_np, color_bgr


def build_styled_mask_preview(edge_mask: np.ndarray) -> np.ndarray:
    """
    Convert a single-channel edge mask into a 3-channel stylized preview where
    edge pixels are colored with a specified 'edge' color and background is
    a light styled background. Returns an uint8 BGR image.
    """
    styled_background_color = (236, 238, 240)  # BGR
    styled_edge_color = (18, 56, 77)  # BGR

    h, w = edge_mask.shape
    background = np.full((h, w, 3), styled_background_color, dtype=np.uint8)

    # normalize mask to [0,1] for blending (float operations for smoothness)
    mask_norm = (edge_mask / 255.0)[:, :, None]
    blended = (background.astype(np.float32) * (1 - mask_norm)) + (
        np.array(styled_edge_color, dtype=np.float32) * mask_norm
    )
    return blended.astype(np.uint8)


def get_logo_bounding_box(edge_mask: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """Return (x, y, w, h) of largest contour bounding box or None when none found."""
    cnts, _ = cv2.findContours(edge_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    largest = max(cnts, key=cv2.contourArea)
    return cv2.boundingRect(largest)


def bgr_to_hsv_tuple(bgr: Tuple[float, float, float]) -> Tuple[int, int, int]:
    """
    Convert a single BGR tuple (B, G, R) into HSV (H, S, V).
    Helpful for reporting average colors.
    """
    color_uint8 = np.uint8([[list(map(int, bgr))]])  # shape (1,1,3)
    hsv = cv2.cvtColor(color_uint8, cv2.COLOR_BGR2HSV)[0][0]
    return int(hsv[0]), int(hsv[1]), int(hsv[2])


def average_hsv_and_rgb_outside_contours(image_bgr: np.ndarray, contours_list: List[np.ndarray]) -> Dict[str, Optional[Tuple[float, float, float]]]:
    """
    Compute average HSV and RGB of the region outside the provided contours.
    Returns dict {'avg_hsv': (H,S,V) | None, 'avg_rgb': (R,G,B) | None}
    """
    if image_bgr is None or image_bgr.size == 0:
        return {"avg_hsv": None, "avg_rgb": None}

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    mask = np.zeros_like(gray)
    if contours_list:
        cv2.drawContours(mask, contours_list, -1, 255, thickness=cv2.FILLED)

    outside_mask = cv2.bitwise_not(mask)

    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    h_out = h[outside_mask == 255]
    s_out = s[outside_mask == 255]
    v_out = v[outside_mask == 255]

    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    r, g, b = cv2.split(rgb)
    r_out = r[outside_mask == 255]
    g_out = g[outside_mask == 255]
    b_out = b[outside_mask == 255]

    if h_out.size == 0 or r_out.size == 0:
        return {"hsv": None, "rgb": None}

    avg_hsv = (float(h_out.mean()), float(s_out.mean()), float(v_out.mean()))
    avg_rgb = (float(r_out.mean()), float(g_out.mean()), float(b_out.mean()))

    return {"hsv": avg_hsv, "rgb": avg_rgb}


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/advanced-logo-analysis", methods=["POST"])
def advanced_logo_analysis():
    """
    Main endpoint that accepts a JSON payload:
      {
        "image": "data:image/png;base64,...",
        "request": "<action>",
        "commercial": <bool>
      }

    Supported 'request' values:
      - "build-mask-first": initialize masks and previews
      - "build-mask": add a frame to the average mask
      - "build-mask-last": finalize mask and compute averages / contours
      - any other value: perform detection/compare using previously-built mask
    """
    global logo_edges, avg_edge_mask
    global logo_edges_from_eroded, avg_edge_mask_from_eroded
    global color_imgs, avg_color_img
    global contours, avg_edge_mask_boolean_mask
    global ground_truth_total

    data = request.json
    img_field = data.get("image")
    if not img_field:
        return jsonify({"error": "missing image"}), 400

    gray_np, color_bgr = decode_request_image(img_field)
    # small morphological kernel used for erosion (shrinks shapes slightly)
    kernel = np.ones((5, 5), np.uint8)
    img_eroded = cv2.erode(gray_np, kernel)

    req = data.get("request", "")
    commercial_flag = bool(data.get("commercial", False))

    # -------------------------
    # Mask building entrypoints
    # -------------------------
    if req == "build-mask-first":
        # Start fresh with initial statistics
        img_blur = cv2.GaussianBlur(gray_np, (5, 5), 0)
        current_edge = cv2.Canny(img_blur, 20, 50)

        logo_edges = [current_edge]
        avg_edge_mask = np.mean(logo_edges, axis=0).astype(np.uint8)

        img_blur_eroded = cv2.GaussianBlur(img_eroded, (5, 5), 0)
        current_edge_from_eroded = cv2.Canny(img_blur_eroded, 20, 50)
        logo_edges_from_eroded = [current_edge_from_eroded]
        avg_edge_mask_from_eroded = np.mean(logo_edges_from_eroded, axis=0).astype(np.uint8)

        color_imgs = [color_bgr]
        avg_color_img = np.mean(color_imgs, axis=0).astype(np.uint8)

        contours = []

        styled_preview = build_styled_mask_preview(avg_edge_mask)

        return jsonify(
            {
                "request": req,
                "version": __version__,
                "maskBuildPreviewImage": image_to_base64(styled_preview),
            }
        )

    if req == "build-mask":
        # Add a frame to the running average used as the mask
        img_blur = cv2.GaussianBlur(gray_np, (5, 5), 0)
        current_edge = cv2.Canny(img_blur, 30, 70)

        logo_edges.append(current_edge)
        avg_edge_mask = np.mean(logo_edges, axis=0).astype(np.uint8)

        img_blur_eroded = cv2.GaussianBlur(img_eroded, (5, 5), 0)
        current_edge_from_eroded = cv2.Canny(img_blur_eroded, 30, 70)
        logo_edges_from_eroded.append(current_edge_from_eroded)
        avg_edge_mask_from_eroded = np.mean(logo_edges_from_eroded, axis=0).astype(np.uint8)

        color_imgs.append(color_bgr)
        avg_color_img = np.mean(color_imgs, axis=0).astype(np.uint8)

        styled_preview = build_styled_mask_preview(avg_edge_mask)

        return jsonify(
            {
                "request": req,
                "maskBuildPreviewImage": image_to_base64(styled_preview),
            }
        )

    if req == "build-mask-last":
        # Finalize mask and compute contour-based statistics
        img_blur = cv2.GaussianBlur(gray_np, (5, 5), 0)
        current_edge = cv2.Canny(img_blur, 20, 50)

        logo_edges.append(current_edge)
        avg_edge_mask = np.mean(logo_edges, axis=0).astype(np.uint8)

        img_blur_eroded = cv2.GaussianBlur(img_eroded, (5, 5), 0)
        current_edge_from_eroded = cv2.Canny(img_blur_eroded, 20, 50)
        logo_edges_from_eroded.append(current_edge_from_eroded)
        avg_edge_mask_from_eroded = np.mean(logo_edges_from_eroded, axis=0).astype(np.uint8)

        color_imgs.append(color_bgr)
        avg_color_img = np.mean(color_imgs, axis=0).astype(np.uint8)

        avg_edge_mask_boolean_mask_from_eroded = avg_edge_mask_from_eroded > 180
        contours, _ = cv2.findContours(
            (avg_edge_mask_boolean_mask_from_eroded.astype(np.uint8)), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Average color of the eroded-edge mask region (B,G,R)
        masked_pixels = avg_color_img[avg_edge_mask_boolean_mask_from_eroded]
        if masked_pixels.size > 0:
            eroded_edges_avg_bgr = tuple(float(x) for x in masked_pixels.mean(axis=0))
            eroded_edges_avg_hsv = tuple(float(x) for x in bgr_to_hsv_tuple(eroded_edges_avg_bgr))
        else:
            eroded_edges_avg_bgr = (255.0, 255.0, 255.0) # White
            eroded_edges_avg_hsv = (0.0, 0.0, 255.0) # White

        # Visual overlay: color red the location of pixels used to get average logo color
        overlay_img = avg_color_img.copy()
        red_overlay = np.zeros_like(overlay_img)
        red_overlay[:, :, 2] = 255
        mask_3ch = np.stack([avg_edge_mask_boolean_mask_from_eroded] * 3, axis=-1)
        overlay_img = np.where(mask_3ch, cv2.addWeighted(overlay_img, 0.5, red_overlay, 0.5, 0), overlay_img)
        overlay_img_rgb = cv2.cvtColor(overlay_img, cv2.COLOR_BGR2RGB)

        # Create preview
        styled_preview = build_styled_mask_preview(avg_edge_mask)

        # Outer color for white background behind white or transparent logo protection
        outer_hsv_and_rgb = average_hsv_and_rgb_outside_contours(avg_color_img, contours)

        # Ground truth mask for comparisons
        avg_edge_mask_boolean_mask = avg_edge_mask > 180
        ground_truth_total = avg_edge_mask_boolean_mask.sum()

        # Return error if no logo is detected
        if ground_truth_total < 1:
            return jsonify({"error": "no logo detected"}), 400

        return jsonify(
            {
                "request": req,
                "edgeSum": float(ground_truth_total),
                "maskBuildPreviewImage": image_to_base64(styled_preview),
                "finalMaskImage": image_to_base64((avg_edge_mask_boolean_mask.astype(np.uint8)) * 255),
                "averageColorInsideLogoHSV": eroded_edges_avg_hsv,
                "averageColorInsideLogoBGR": eroded_edges_avg_bgr,
                "averageColorInsideLogoCaptureRegionImage": image_to_base64(overlay_img_rgb),
                "averageColorOutsideLogo": outer_hsv_and_rgb,
            }
        )

    # -------------------------
    # Detection / compare path
    # -------------------------
    # If caller flags 'commercial', we adjust edge thresholds to be less/ more sensitive
    if commercial_flag:
        img_blur = cv2.GaussianBlur(gray_np, (5, 5), 0)
        current_edge = cv2.Canny(img_blur, 40, 100)
    else:
        # more sensitive detection on non-commercial content
        current_edge = cv2.Canny(gray_np, 8, 12)

    current_edge_boolean_mask = current_edge > 20

    # True positives where both mask and current edge indicate an edge
    true_positive = np.logical_and(avg_edge_mask_boolean_mask, current_edge_boolean_mask).sum()
    precision = float(true_positive / ground_truth_total) if ground_truth_total != 0 else 0.0

    # Visual diff: color-code pixels for inspection
    edge1 = avg_edge_mask_boolean_mask.astype(bool)
    edge2 = current_edge_boolean_mask.astype(bool)
    styled_background_color = (236, 238, 240)
    visual = np.full((*avg_edge_mask.shape, 3), styled_background_color, dtype=np.uint8)

    visual[edge1 & ~edge2] = [158, 52, 46]   # RED = edge in avg mask only
    visual[~edge1 & edge2] = [94, 136, 158]  # BLUE = edge in current only
    visual[edge1 & edge2] = [56, 122, 76]    # GREEN = both

    outer_hsv_and_rgb = average_hsv_and_rgb_outside_contours(color_bgr, contours)

    return jsonify(
        {
            "request": req,
            "edgeMatchConfidence": precision,
            "edgeMatchVisualImage": image_to_base64(visual.astype(np.uint8)),
            "averageColorOutsideLogo": outer_hsv_and_rgb,
        }
    )


@app.route("/ping-advanced-logo-analysis", methods=["GET"])
def ping():
    """Simple healthcheck used by the tray and other tools."""
    return jsonify({"ok": True, "version": __version__})


# -----------------------------------------------------------------------------
# Tray helpers
# -----------------------------------------------------------------------------
def run_server() -> None:
    """Run the Flask server in the background thread."""
    app.run(port=PORT)


def on_restart(icon, item) -> None:
    """Restart the Python process."""
    icon.stop()
    os.execl(sys.executable, sys.executable, *sys.argv)


def on_exit(icon, item) -> None:
    """Stop tray icon and forcibly exit the process."""
    icon.stop()
    os._exit(0)


def start_tray() -> None:
    """Create system tray icon with Restart and Exit options."""
    #image = Image.open("icon.png")
    base_path = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_path, "icon.png")
    image = Image.open(icon_path)
    tray_menu = menu(item("Exit", on_exit))
    icon = pystray.Icon("Live Commercial Blocker - Advanced Logo Analyzer", image, "Live Commercial Blocker - Advanced Logo Analyzer", tray_menu)
    icon.run()


# -----------------------------------------------------------------------------
# CLI entrypoint
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    start_tray()


# for exe creation:
# py -m PyInstaller --noconsole --icon=icon.ico advanced_logo_analyzer.py
# and then copy/paste icon.png into generated _internal folder
# lastly, compile into setup exe with Inno
