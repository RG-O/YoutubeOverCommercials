
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

app = Flask(__name__)

logo_edges = []
avg_edge_mask = None

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




@app.route("/advanced-logo-analysis", methods=["POST"])
def advanced_logo_analysis():
    global logo_edges, avg_edge_mask

    data = request.json
    img_data = data['image'].split(',')[1]
    img_bytes = base64.b64decode(img_data)
    img_pil = Image.open(BytesIO(img_bytes)).convert("L")
    img_np = np.array(img_pil)

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

        return jsonify({
            "status": data['request'],
            "frames_collected": len(logo_edges),
            "current_edge_preview": image_to_base64(current_edge),
            "img_np": image_to_base64(img_np),
            "img_blur": image_to_base64(img_blur),
            "mask_preview": image_to_base64(avg_edge_mask)
        })

    if data['request'] == "build-mask":
        img_blur = cv2.GaussianBlur(img_np, (5, 5), 0)
        #medium edge threshold for mask building
        current_edge = cv2.Canny(img_blur, 30, 70)
        logo_edges.append(current_edge)
        avg_edge_mask = np.mean(logo_edges, axis=0).astype(np.uint8)

        return jsonify({
            "status": data['request'],
            "frames_collected": len(logo_edges),
            "current_edge_preview": image_to_base64(current_edge),
            "mask_preview": image_to_base64(avg_edge_mask),
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

        return jsonify({
            "status": data['request'],
            "frames_collected": len(logo_edges),
            "current_edge_preview": image_to_base64(current_edge),
            "mask_preview": image_to_base64(avg_edge_mask),
            "img_np": image_to_base64(img_np),
            "img_blur": image_to_base64(img_blur),
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




    avg_edge_mask_boolean_mask = avg_edge_mask > 180  # Ground truth
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

    #TODO: display this for debug people
    # Create an RGB image
    visual = np.zeros((edge1.shape[0], edge1.shape[1], 3), dtype=np.uint8)

    # RED = edge1 only
    visual[edge1 & ~edge2] = [255, 0, 0]

    # BLUE = edge2 only
    visual[~edge1 & edge2] = [0, 0, 255]

    # GREEN = match (edge1 and edge2)
    visual[edge1 & edge2] = [0, 255, 0]

    # precision = true_positive / ground_truth_total
    # return precision * 100


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
        #"diff_preview": image_to_base64(diff_region.astype(np.uint8)),
        "diff_preview": image_to_base64(visual.astype(np.uint8)),
        #"img_np": image_to_base64(img_np),
        #"img_blur": image_to_base64(img_blur),
    })

if __name__ == "__main__":
    app.run(port=64143)