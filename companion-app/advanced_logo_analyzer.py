
# import io
# import base64
# import numpy as np
# import cv2
# from PIL import Image
# from io import BytesIO

# def preprocess_edge(image_np):
#     return cv2.Canny(image_np, 50, 150)

# def image_to_base64(img_np):
#     # Convert grayscale numpy image to PNG base64
#     img_pil = Image.fromarray(img_np)
#     buf = BytesIO()
#     img_pil.save(buf, format="PNG")
#     return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

# img_sample = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAApgAAAKYB3X3/OAAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAANCSURBVEiJtZZPbBtFFMZ/M7ubXdtdb1xSFyeilBapySVU8h8OoFaooFSqiihIVIpQBKci6KEg9Q6H9kovIHoCIVQJJCKE1ENFjnAgcaSGC6rEnxBwA04Tx43t2FnvDAfjkNibxgHxnWb2e/u992bee7tCa00YFsffekFY+nUzFtjW0LrvjRXrCDIAaPLlW0nHL0SsZtVoaF98mLrx3pdhOqLtYPHChahZcYYO7KvPFxvRl5XPp1sN3adWiD1ZAqD6XYK1b/dvE5IWryTt2udLFedwc1+9kLp+vbbpoDh+6TklxBeAi9TL0taeWpdmZzQDry0AcO+jQ12RyohqqoYoo8RDwJrU+qXkjWtfi8Xxt58BdQuwQs9qC/afLwCw8tnQbqYAPsgxE1S6F3EAIXux2oQFKm0ihMsOF71dHYx+f3NND68ghCu1YIoePPQN1pGRABkJ6Bus96CutRZMydTl+TvuiRW1m3n0eDl0vRPcEysqdXn+jsQPsrHMquGeXEaY4Yk4wxWcY5V/9scqOMOVUFthatyTy8QyqwZ+kDURKoMWxNKr2EeqVKcTNOajqKoBgOE28U4tdQl5p5bwCw7BWquaZSzAPlwjlithJtp3pTImSqQRrb2Z8PHGigD4RZuNX6JYj6wj7O4TFLbCO/Mn/m8R+h6rYSUb3ekokRY6f/YukArN979jcW+V/S8g0eT/N3VN3kTqWbQ428m9/8k0P/1aIhF36PccEl6EhOcAUCrXKZXXWS3XKd2vc/TRBG9O5ELC17MmWubD2nKhUKZa26Ba2+D3P+4/MNCFwg59oWVeYhkzgN/JDR8deKBoD7Y+ljEjGZ0sosXVTvbc6RHirr2reNy1OXd6pJsQ+gqjk8VWFYmHrwBzW/n+uMPFiRwHB2I7ih8ciHFxIkd/3Omk5tCDV1t+2nNu5sxxpDFNx+huNhVT3/zMDz8usXC3ddaHBj1GHj/As08fwTS7Kt1HBTmyN29vdwAw+/wbwLVOJ3uAD1wi/dUH7Qei66PfyuRj4Ik9is+hglfbkbfR3cnZm7chlUWLdwmprtCohX4HUtlOcQjLYCu+fzGJH2QRKvP3UNz8bWk1qMxjGTOMThZ3kvgLI5AzFfo379UAAAAASUVORK5CYII="

# img_data = img_sample.split(',')[1]
# img_bytes = base64.b64decode(img_data)
# img_pil = Image.open(BytesIO(img_bytes)).convert("L")
# img_np = np.array(img_pil)

# current_edge = preprocess_edge(img_np)

# print(image_to_base64(current_edge.astype(np.uint8)))


import io
import base64
from flask import Flask, request, jsonify
import numpy as np
import cv2
from PIL import Image
from io import BytesIO
import threading
import webbrowser
import pystray
from pystray import MenuItem as item
import sys
import os

version = "1.0"

app = Flask(__name__)
PORT = 64143

logo_edges = []
avg_edge_mask = None

logo_edges_from_eroded = []
avg_edge_mask_from_eroded = None

color_imgs = []
avg_color_img = None

contours = []

# def preprocess_edge(img_blur):
#     #blurred = cv2.GaussianBlur(image_np, (5, 5), 0)
#     #return cv2.Canny(blurred, 50, 150)
#     #return cv2.Canny(img_blur, 10, 80)
#     #return cv2.Canny(img_blur, 30, 70)
#     #TODO: set different levels for mask creation, during commercial, and out of commercial
#     return cv2.Canny(img_blur, 20, 50)

def image_to_base64(img_np):
    # Convert grayscale numpy image to PNG base64
    img_pil = Image.fromarray(img_np)
    buf = BytesIO()
    img_pil.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def get_logo_bounding_box(edge_mask):
    contours, _ = cv2.findContours(edge_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    return cv2.boundingRect(largest)  # (x, y, w, h)

def overlay_logo_box(original_bgr, edge_mask):
    overlay = original_bgr.copy()
    box = get_logo_bounding_box(edge_mask)
    if box:
        x, y, w, h = box
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 255, 0), 2)
    return overlay



#TODO: can I have this all just be hsv from the start?
# previously titled is_average_color_white_or_transparent
def bgr_to_hsv(bgr):
    """
    Classifies a single average BGR color as white/transparent or colored.
    
    Args:
        avg_bgr (tuple): (B, G, R) values, typically float or int.
        
    Returns:
        str: "white_or_transparent" or "colored"
    """
    # Convert to uint8 and reshape for cv2.cvtColor
    color_bgr_uint8 = np.uint8([[list(bgr)]])  # shape (1, 1, 3)

    # Convert to HSV
    hsv = cv2.cvtColor(color_bgr_uint8, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[0][0]

    # print("s:", s)
    # print("v:", v)

    # # Decision logic
    # #if s < 30 and v > 200:
    # #if s < 70 and v > 140:
    # if s < 70 and v > 100:
    #     return "white_or_transparent"
    # else:
    #     return "colored"
    #     #TODO: move decision over to extension

    #return {"h": h, "s": s, "v": v} #not json serializable
    return (h, s, v)




def average_hsv_outside_contours(image_bgr, contours):
    """
    Calculate the average HSV color values outside the given contours.
    
    Args:
        image_bgr (np.ndarray): Original image in BGR format.
        contours (list): List of contours from cv2.findContours.
        
    Returns:
        tuple: (avg_hue, avg_saturation, avg_value)
    """
    # Step 1: Create mask that includes only contour regions
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    mask = np.zeros_like(gray)
    cv2.drawContours(mask, contours, -1, 255, thickness=cv2.FILLED)

    # Step 2: Invert mask to get OUTSIDE of contours
    outside_mask = cv2.bitwise_not(mask)

    # Step 3: Convert image to HSV
    hsv_image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv_image)

    # Step 4: Mask out values outside the contours
    h_out = h[outside_mask == 255]
    s_out = s[outside_mask == 255]
    v_out = v[outside_mask == 255]

    if len(h_out) == 0:
        return None  # No area outside contours

    # Step 5: Compute and return averages
    avg_h = float(np.mean(h_out))
    avg_s = float(np.mean(s_out))
    avg_v = float(np.mean(v_out))

    return (avg_h, avg_s, avg_v)






def average_hsv_and_rgb_outside_contours(image_bgr, contours):
    """
    Calculate average HSV and RGB values for areas outside given contours.
    
    Args:
        image_bgr (np.ndarray): Original BGR image.
        contours (list): List of contours from cv2.findContours.
        
    Returns:
        dict: {
            'avg_hsv': (H, S, V),
            'avg_rgb': (R, G, B)
        }
    """
    # Create mask for inside the contours
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    mask = np.zeros_like(gray)
    cv2.drawContours(mask, contours, -1, 255, thickness=cv2.FILLED)

    # Invert the mask to get outside of contours
    outside_mask = cv2.bitwise_not(mask)

    # HSV processing
    hsv_image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv_image)

    h_out = h[outside_mask == 255]
    s_out = s[outside_mask == 255]
    v_out = v[outside_mask == 255]

    # RGB processing
    rgb_image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    r, g, b = cv2.split(rgb_image)

    r_out = r[outside_mask == 255]
    g_out = g[outside_mask == 255]
    b_out = b[outside_mask == 255]

    # Handle empty region case
    if len(h_out) == 0 or len(r_out) == 0:
        return {
            'avg_hsv': None,
            'avg_rgb': None
        }

    # Compute averages
    avg_hsv = (
        float(np.mean(h_out)),
        float(np.mean(s_out)),
        float(np.mean(v_out))
    )

    avg_rgb = (
        float(np.mean(r_out)),
        float(np.mean(g_out)),
        float(np.mean(b_out))
    )

    return {
        'avg_hsv': avg_hsv,
        'avg_rgb': avg_rgb
    }






@app.route("/advanced-logo-analysis", methods=["POST"])
def advanced_logo_analysis():
    global logo_edges, avg_edge_mask
    global logo_edges_from_eroded, avg_edge_mask_from_eroded
    global color_imgs, avg_color_img
    global contours
    global avg_edge_mask_boolean_mask

    data = request.json
    img_data = data['image'].split(',')[1]
    img_bytes = base64.b64decode(img_data)
    img_pil = Image.open(BytesIO(img_bytes)).convert("L")

    img_pil_color = Image.open(BytesIO(img_bytes)).convert("RGB")
    img_np_color = np.array(img_pil_color)
    img_color = cv2.cvtColor(img_np_color, cv2.COLOR_RGB2BGR)

    np_arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img_color_two = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    #img_color_three = cv2.cvtColor(img_color_two, cv2.COLOR_BGR2RGB)
    #sounds like I may want to keep the image in BGR since everything seems to be BGR2___ later on
    img_color_three = img_color_two

    img_np = np.array(img_pil)


    # Create kernel for morphological ops
    #kernel = np.ones((2, 2), np.uint8)
    #kernel = np.ones((3, 3), np.uint8)
    kernel = np.ones((5, 5), np.uint8)

    # Step 1: Shrink contour region for cleaner inside
    img_eroded = cv2.erode(img_np, kernel)

    

    #img_blur = cv2.GaussianBlur(img_np, (5, 5), 0)
    #img_blur = cv2.GaussianBlur(img_np, (9, 9), 0)

    #current_edge = preprocess_edge(img_blur)

    if data['request'] == "build-mask-first":
        img_blur = cv2.GaussianBlur(img_np, (5, 5), 0)
        current_edge = cv2.Canny(img_blur, 20, 50)
        #clear on first mask build
        logo_edges = []
        logo_edges.append(current_edge)
        avg_edge_mask = np.mean(logo_edges, axis=0).astype(np.uint8)

        img_blur_from_eroded = cv2.GaussianBlur(img_eroded, (5, 5), 0)
        current_edge_from_eroded = cv2.Canny(img_blur_from_eroded, 20, 50)
        logo_edges_from_eroded = []
        logo_edges_from_eroded.append(current_edge_from_eroded)
        avg_edge_mask_from_eroded = np.mean(logo_edges_from_eroded, axis=0).astype(np.uint8)

        color_imgs = []
        color_imgs.append(img_color_three)
        avg_color_img = np.mean(color_imgs, axis=0).astype(np.uint8)

        contours = []

        ############## Converting to color: ######################

        # step 1 done above
        # Step 2: Define colors (BGR format since OpenCV uses BGR)
        styled_background_color = (236, 238, 240)   # RGB(240,238,236) to BGR(236,238,240)
        styled_edge_color = (18, 56, 77)            # #12384d to BGR(18,56,77)

        # Step 3: Create a 3-channel color image for the background
        styled_color_img = np.full((*avg_edge_mask.shape, 3), styled_background_color, dtype=np.uint8)

        # Step 4: Normalize the mask to [0,1] range for blending
        styled_mask_norm = (avg_edge_mask / 255.0)[:, :, None]

        # Step 5: Blend edge color where edges are white
        styled_color_img = styled_color_img * (1 - styled_mask_norm) + np.array(styled_edge_color, dtype=np.uint8) * styled_mask_norm
        styled_color_img = styled_color_img.astype(np.uint8)

        ##########################################################

        return jsonify({
            "status": data['request'],
            "version": version,
            "frames_collected": len(logo_edges),
            "current_edge_preview": image_to_base64(current_edge),
            "img_np": image_to_base64(img_np),
            "img_blur": image_to_base64(img_blur),
            #"mask_preview": image_to_base64(avg_edge_mask)
            "mask_preview": image_to_base64(styled_color_img),
        })

    if data['request'] == "build-mask":
        img_blur = cv2.GaussianBlur(img_np, (5, 5), 0)
        #medium edge threshold for mask building
        current_edge = cv2.Canny(img_blur, 30, 70)
        logo_edges.append(current_edge)
        avg_edge_mask = np.mean(logo_edges, axis=0).astype(np.uint8)

        img_blur_from_eroded = cv2.GaussianBlur(img_eroded, (5, 5), 0)
        current_edge_from_eroded = cv2.Canny(img_blur_from_eroded, 30, 70)
        logo_edges_from_eroded.append(current_edge_from_eroded)
        avg_edge_mask_from_eroded = np.mean(logo_edges_from_eroded, axis=0).astype(np.uint8)

        color_imgs.append(img_color_three)
        avg_color_img = np.mean(color_imgs, axis=0).astype(np.uint8)

        ############## Converting to color: ######################

        # step 1 done above
        # Step 2: Define colors (BGR format since OpenCV uses BGR)
        styled_background_color = (236, 238, 240)   # RGB(240,238,236) to BGR(236,238,240)
        styled_edge_color = (18, 56, 77)            # #12384d to BGR(18,56,77)

        # Step 3: Create a 3-channel color image for the background
        styled_color_img = np.full((*avg_edge_mask.shape, 3), styled_background_color, dtype=np.uint8)

        # Step 4: Normalize the mask to [0,1] range for blending
        styled_mask_norm = (avg_edge_mask / 255.0)[:, :, None]

        # Step 5: Blend edge color where edges are white
        styled_color_img = styled_color_img * (1 - styled_mask_norm) + np.array(styled_edge_color, dtype=np.uint8) * styled_mask_norm
        styled_color_img = styled_color_img.astype(np.uint8)

        ##########################################################

        return jsonify({
            "status": data['request'],
            "frames_collected": len(logo_edges),
            "current_edge_preview": image_to_base64(current_edge),
            #"mask_preview": image_to_base64(avg_edge_mask),
            "mask_preview": image_to_base64(styled_color_img),
            "img_np": image_to_base64(img_np),
            "img_blur": image_to_base64(img_blur),
        })

    if data['request'] == "build-mask-last":
        img_blur = cv2.GaussianBlur(img_np, (5, 5), 0)
        #TODO: compare this to previous to detect if logo went away - display as red error on logobox?
        current_edge = cv2.Canny(img_blur, 20, 50)
        logo_edges.append(current_edge)
        ##TODO: display this one as final mask built (even though it isn't the one actually used)
        avg_edge_mask = np.mean(logo_edges, axis=0).astype(np.uint8)
        ##avg_edge = avg_edge_mask.astype(np.float32)

        # edge_density = np.count_nonzero(avg_edge_mask) / avg_edge_mask.size

        # # If no edges present, this frame isn't usable
        # if edge_density < 0.01:
        #     return jsonify({
        #         "status": "low-edge",
        #         "message": "Not enough visual data in current frame.",
        #         "edge_density": edge_density,
        #         "confidence": 0.0,
        #         "logo": False
        #     })

        img_blur_from_eroded = cv2.GaussianBlur(img_eroded, (5, 5), 0)
        current_edge_from_eroded = cv2.Canny(img_blur_from_eroded, 20, 50)
        logo_edges_from_eroded.append(current_edge_from_eroded)
        avg_edge_mask_from_eroded = np.mean(logo_edges_from_eroded, axis=0).astype(np.uint8)

        color_imgs.append(img_color_three)
        avg_color_img = np.mean(color_imgs, axis=0).astype(np.uint8)

        avg_edge_mask_boolean_mask_from_eroded = avg_edge_mask_from_eroded > 180

        #contours, _ = cv2.findContours(avg_edge_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        #contours, _ = cv2.findContours(avg_edge_mask_boolean_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours, _ = cv2.findContours(avg_edge_mask_boolean_mask_from_eroded.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    

        # attempt at average color of eroded edges ##############

        # Get only the pixels where the mask is True
        masked_pixels = avg_color_img[avg_edge_mask_boolean_mask_from_eroded]

        # Compute the average color (B, G, R)
        #eroded_edges_average_color_bgr = masked_pixels.mean(axis=0)
        if masked_pixels.size > 0:
            eroded_edges_average_color_bgr = masked_pixels.mean(axis=0)
            eroded_edges_average_color_hsv = bgr_to_hsv(eroded_edges_average_color_bgr)
            eroded_edges_average_color_hsv = tuple(float(c) for c in eroded_edges_average_color_hsv) #todo: have this in bgr_to_hsv function?
            eroded_edges_average_color_bgr = tuple(float(c) for c in eroded_edges_average_color_bgr) #todo: some way to not have to do this?
        else:
            eroded_edges_average_color_bgr = np.array([0, 0, 0])
            eroded_edges_average_color_hsv = np.array([0, 0, 0])

        print("eroded edges average color (B, G, R):", eroded_edges_average_color_bgr)
        print("eroded edges average color (H, S, V):", eroded_edges_average_color_hsv)

        # Make a copy of the color image to overlay on
        overlay_img = avg_color_img.copy()

        # Create a red overlay (or any color you like)
        red_overlay = np.zeros_like(overlay_img)
        red_overlay[:, :, 2] = 255  # full red

        # Make a version of the mask with 3 channels
        mask_3ch = np.stack([avg_edge_mask_boolean_mask_from_eroded]*3, axis=-1)

        # Blend the red overlay wherever mask is True
        overlay_img = np.where(mask_3ch, cv2.addWeighted(overlay_img, 0.5, red_overlay, 0.5, 0), overlay_img) #todo: rename
        overlay_img_rgb = cv2.cvtColor(overlay_img, cv2.COLOR_BGR2RGB) #todo: rename
        #print(image_to_base64(overlay_img_rgb))
        ###########


        # for cnt in contours:
        #     mask = np.zeros_like(avg_edge_mask)
        #     cv2.drawContours(mask, [cnt], -1, 255, thickness=cv2.FILLED)
        #     average_color_inside = cv2.mean(img_color_two, mask=mask[:])
        #     print("Average inside color:", average_color_inside)


        #contour_vis = img_color_three.copy()
        contour_vis = avg_color_img.copy()

        individual_avg_colors = []

        for cnt in contours:
            # Create a mask for the current contour
            #mask = np.zeros_like(avg_edge_mask)
            mask = np.zeros_like(avg_edge_mask_from_eroded)
            cv2.drawContours(mask, [cnt], -1, 255, thickness=cv2.FILLED)

            # Compute the mean color within the masked region
            # color = cv2.mean(img_color_three, mask=mask)[:3]  # (B, G, R)
            color = cv2.mean(avg_color_img, mask=mask)[:3]  # (B, G, R)

            #print(color)

            individual_avg_colors.append(color)

            # Draw the contour on the visualization image
            cv2.drawContours(contour_vis, [cnt], -1, (0, 255, 0), thickness=1)


        #print(individual_avg_colors)

        # Compute overall average color from individual contour colors
        if individual_avg_colors:
            overall_avg_color = tuple(np.mean(individual_avg_colors, axis=0))
        else:
            overall_avg_color = (0, 0, 0)

        print(overall_avg_color)

        overall_avg_color = tuple(float(c) for c in overall_avg_color)

        print(overall_avg_color)

        #print("Average color:", overall_avg_color)

        #TODO: I don't believe I have to use this function if I just keep the average color image in HSV the whole time
        logo_mask_avg_hsv = bgr_to_hsv(overall_avg_color)

        logo_mask_avg_hsv = tuple(float(c) for c in logo_mask_avg_hsv)

        avg_logo_outer_hsv_and_rgb = average_hsv_and_rgb_outside_contours(avg_color_img, contours)

        print(logo_mask_avg_hsv)

        ############## Converting to color: ######################

        # step 1 done above
        # Step 2: Define colors (BGR format since OpenCV uses BGR)
        styled_background_color = (236, 238, 240)   # RGB(240,238,236) to BGR(236,238,240)
        styled_edge_color = (18, 56, 77)            # #12384d to BGR(18,56,77)

        # Step 3: Create a 3-channel color image for the background
        styled_color_img = np.full((*avg_edge_mask.shape, 3), styled_background_color, dtype=np.uint8)

        # Step 4: Normalize the mask to [0,1] range for blending
        styled_mask_norm = (avg_edge_mask / 255.0)[:, :, None]

        # Step 5: Blend edge color where edges are white
        styled_color_img = styled_color_img * (1 - styled_mask_norm) + np.array(styled_edge_color, dtype=np.uint8) * styled_mask_norm
        styled_color_img = styled_color_img.astype(np.uint8)

        ##########################################################

        avg_edge_mask_boolean_mask = avg_edge_mask > 180  # Ground truth

        #TODO: add various checks throughout this app because if not edges are detected, it will break plenty of things
        #TODO: can I also add try brakets like in javascript?
        return jsonify({
            "status": data['request'],
            "frames_collected": len(logo_edges),
            "current_edge_preview": image_to_base64(current_edge),
            #"mask_preview": image_to_base64(avg_edge_mask),
            "mask_preview": image_to_base64(styled_color_img),
            "final_mask_preview": image_to_base64((avg_edge_mask_boolean_mask.astype(np.uint8)) * 255),
            #"img_np": image_to_base64(img_np),
            #"img_blur": image_to_base64(img_blur),
            #"logo_mask_avg_hsv": logo_mask_avg_hsv,
            "logo_mask_avg_hsv": eroded_edges_average_color_hsv, #todo: rename?
            #"avg_logo_color": overall_avg_color,
            "avg_logo_color": eroded_edges_average_color_bgr,
            #"contour_vis": image_to_base64(contour_vis),
            "contour_vis": image_to_base64(overlay_img_rgb),
            "avg_logo_outer_hsv_and_rgb": avg_logo_outer_hsv_and_rgb,
        })

    # avg_edge = avg_edge_mask.astype(np.float32)
    # diff = cv2.absdiff(current_edge.astype(np.float32), avg_edge)
    # similarity = 1.0 - (np.mean(diff) / 255.0)
    # match = similarity > 0.8

    # if data['request'] == "compare-to-mask":
    #     return jsonify({
    #         "status": data['request'],
    #         "logo": bool(match),
    #         "confidence": float(similarity),
    #         "current_edge_preview": image_to_base64(current_edge.astype(np.uint8)),
    #         "mask_preview": image_to_base64(avg_edge_mask),
    #         "diff_preview": image_to_base64(diff.astype(np.uint8))
    #     })


    # if current state is commercial set lower edge threashold
    if data['commercial']:
        img_blur = cv2.GaussianBlur(img_np, (5, 5), 0)
        current_edge = cv2.Canny(img_blur, 40, 100)
    else:
        #less blur
        #img_blur = cv2.GaussianBlur(img_np, (3, 3), 0)
        # if current state is not commercial set lower edge threashold as to potentially pick up the logo displaying over whitish background
        #current_edge = cv2.Canny(img_blur, 20, 30)
        #current_edge = cv2.Canny(img_blur, 10, 20)
        current_edge = cv2.Canny(img_np, 8, 12)



    # # --- Masked region-based comparison ---
    # expected_edge_mask = avg_edge_mask > 20  # Only compare where we expect edges
    #diff_region = cv2.absdiff(current_edge.astype(np.float32), avg_edge_mask.astype(np.float32))
    # #TODO: figure out what this means
    # diff_values = diff_region[expected_edge_mask]

    # # If we have nothing to compare, we can't compute similarity
    # if diff_values.size == 0:
    #     similarity = 0.0
    # else:
    #     similarity = 1.0 - (np.mean(diff_values) / 255.0)

    # match = similarity > 0.7





    #similarity_score, _ = ssim(avg_edge_mask, current_edge, full=True)




    #avg_edge_mask_boolean_mask = avg_edge_mask > 180  # Ground truth
    current_edge_boolean_mask = current_edge > 20  # Noisy comparison

    


    # # Dilate the edges in image2 to tolerate small misalignments
    # kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    # current_edge_boolean_mask_dilated = cv2.dilate(current_edge_boolean_mask.astype(np.uint8), kernel, iterations=1) > 0




    true_positive = np.logical_and(avg_edge_mask_boolean_mask, current_edge_boolean_mask).sum()
    #true_positive = np.logical_and(avg_edge_mask_boolean_mask, current_edge_boolean_mask_dilated).sum()
    ground_truth_total = avg_edge_mask_boolean_mask.sum()

    if ground_truth_total == 0:
        precision = 0
    else: 
        precision = true_positive / ground_truth_total


    edge1 = avg_edge_mask_boolean_mask.astype(bool)
    edge2 = current_edge_boolean_mask.astype(bool)

    # img_np_gray = np.array(img_pil)
    # img_np_gray_blur = cv2.GaussianBlur(img_np_gray, (9, 9), 0)  # adjust (9,9) as desired

    # # Convert blurred grayscale to 3-channel RGB (so we can colorize edges)
    # visual = cv2.cvtColor(img_np_gray_blur, cv2.COLOR_GRAY2BGR)

    styled_background_color = (236, 238, 240)   # RGB(240,238,236) to BGR(236,238,240)

    visual = np.full((*avg_edge_mask.shape, 3), styled_background_color, dtype=np.uint8)

    #TODO: display this for debug people
    # Create an RGB image
    #visual = np.zeros((edge1.shape[0], edge1.shape[1], 3), dtype=np.uint8)
    #visual = img_np_color.copy()
    #visual = img_np.copy()

    # RED = edge1 only
    visual[edge1 & ~edge2] = [158, 52, 46]

    # BLUE = edge2 only
    visual[~edge1 & edge2] = [94, 136, 158]

    # GREEN = match (edge1 and edge2)
    visual[edge1 & edge2] = [56, 122, 76]

    # precision = true_positive / ground_truth_total
    # return precision * 100



    just_logo = overlay_logo_box(img_color, avg_edge_mask)


    



    #outer_hsv = average_hsv_outside_contours(img_color_three, contours)
    outer_hsv_and_rgb = average_hsv_and_rgb_outside_contours(img_color_three, contours)



    # --- Return result with visual previews ---
    return jsonify({
        "status": data['request'],
        #"logo": bool(match),
        "confidence": float(precision),
        #"current_edge_preview": image_to_base64(current_edge.astype(np.uint8)),
        "current_edge_preview": image_to_base64((current_edge_boolean_mask.astype(np.uint8)) * 255),
        #"current_edge_preview": image_to_base64((current_edge_boolean_mask_dilated.astype(np.uint8)) * 255),
        #"mask_preview": image_to_base64(avg_edge_mask),
        "mask_preview": image_to_base64((avg_edge_mask_boolean_mask.astype(np.uint8)) * 255),
        #"img_blur": image_to_base64((avg_edge_mask_boolean_mask_from_eroded.astype(np.uint8)) * 255),
        #"diff_preview": image_to_base64(diff_region.astype(np.uint8)),
        "diff_preview": image_to_base64(visual.astype(np.uint8)),
        #"img_np": image_to_base64(img_np),
        #"img_blur": image_to_base64(img_blur),
        #"img_np": image_to_base64(just_logo),
        #"img_np": image_to_base64(contour_vis),
        #"img_np": image_to_base64(avg_color_img),
        #"avg_logo_color": overall_avg_color,
        #"white_or_colored": white_or_colored,
        #"outer_hsv": outer_hsv,
        "outer_hsv_and_rgb": outer_hsv_and_rgb,
    })


@app.route("/ping-advanced-logo-analysis", methods=["GET"])
def ping():
    return jsonify({
        "ok": True,
        "version": version,
    })

def run_server():
    #app.run(host="127.0.0.1", port=PORT)
    app.run(port=64143)

# def on_open():
#     webbrowser.open(f"http://localhost:{PORT}/ping")

def on_restart(icon, item):
    os.execl(sys.executable, sys.executable, *sys.argv)

def on_exit(icon, item):
    icon.stop()
    os._exit(0)

def start_tray():
    image = Image.new("RGB", (64, 64), color=(0, 128, 255))
    # menu = (item("Open Ping", on_open), item("Restart", on_restart), item("Exit", on_exit))
    menu = (item("Restart", on_restart), item("Exit", on_exit))
    icon = pystray.Icon("TV Logo Detector", image, "TV Logo Detector", menu)
    icon.run()

if __name__ == "__main__":
    #app.run(port=64143)
    threading.Thread(target=run_server, daemon=True).start()
    start_tray()