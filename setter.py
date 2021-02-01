"""Classification of card attributes."""

import glob
import os
import sys

import cv2
import numpy as np

def bicolorize(img_bgr):
    """Convert the card image to use a single color for the shape(s) and white for the card."""
    VALUE_THRESHOLD = 60
    SATURATION_THRESHOLD = 50

    # In HSV, determine shape vs. background.
    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

    # Assume the first 10 rows are all card coloured.
    (_, card_s, card_v) = img_hsv[:10,:,:].reshape((-1, 3)).mean(axis=0)

    s = np.abs(img_hsv[:,:,1] - card_s) >= SATURATION_THRESHOLD
    v = np.abs(img_hsv[:,:,2] - card_v) >= VALUE_THRESHOLD
    shape_mask = s | v

    # Normalize the shape to a single colour (and card to white).
    shape_rgb = img_bgr[shape_mask].reshape((-1, 3)).mean(axis=0)
    img_bgr[shape_mask] = shape_rgb
    img_bgr[np.invert(shape_mask)] = (255, 255, 255)

    return img_bgr


def classify_color(bgr):
    """Given a sample BGR-valued pixel, determine its Set color."""
    BGR_COLOR_AVGS = {"red": (0, 34, 226), "green": (64, 123, 0), "purple": (89, 0, 76)}

    color_diffs = {
        c: sum(abs(avg - bgr)) for c, avg in BGR_COLOR_AVGS.items()
    }
    color = min(color_diffs, key=color_diffs.get)
    return color


def classify_fill_color(shape_img):
    """Given a bicolor image of a shape, determine its color and fill pattern."""
    SOLID_FILL_THRESHOLD = 0.7
    LINE_COUNT_THRESHOLD = 5

    # Sample a row half way down the image.
    sample_row = int(shape_img.shape[0] / 2)

    fill_count = 0
    line_count = 0
    color = None
    was_shape_pixel = False
    for pixel in shape_img[sample_row]:
        is_shape_pixel = sum(pixel) < 255 * 3
        if is_shape_pixel:
            fill_count += 1
            if not color:
                color = classify_color(pixel)
            if not was_shape_pixel:
                line_count += 1
        was_shape_pixel = is_shape_pixel

    fill_ratio = fill_count / float(shape_img.shape[1])

    fill = None
    if fill_ratio > SOLID_FILL_THRESHOLD:
        fill = "solid"
    else:
        # Distinguish between outline and line
        if line_count > LINE_COUNT_THRESHOLD:
            fill = "stripes"
        else:
            fill = "outline"

    return (fill, color)

def classify_shape(shape_contour):
    """Given the contour of a shape, determine its Set shape."""
    perim = cv2.arcLength(shape_contour, closed=True)
    approx = cv2.approxPolyDP(shape_contour, 0.01 * perim, closed=True)
    if len(approx) < 6:
        return "diamond"
    else:
        if cv2.isContourConvex(approx):
            return "capsule"
        else:
            return "squiggle"


MIN_SHAPE_AREA_FRACTION = 0.1


def classify_card(img_bgr):
    """Given a card image, return its Set attributes."""
    bicolor = bicolorize(img_bgr)

    gray = cv2.cvtColor(bicolor, cv2.COLOR_BGR2GRAY)
    # Invert, otherwise RETR_EXTERNAL makes the whole card the largest contour
    gray = cv2.bitwise_not(gray)

    contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    classification = {"count": 0}
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if (w * h) / (img_bgr.shape[0] * img_bgr.shape[1]) < MIN_SHAPE_AREA_FRACTION:
            continue
        classification["count"] += 1
        if not "fill" in classification:
            (fill, color) = classify_fill_color(bicolor[y:y+h, x:x+w])
            classification["fill"] = fill
            classification["color"] = color
        if not "shape" in classification:
            classification["shape"] = classify_shape(c)

    print(f"Card: {classification}")
    return classification


def main():
    def process_card(file):
        return classify_card(cv2.imread(file))
    if len(sys.argv) > 1:
        for f in sys.argv[1:]:
            process_card(f)
    else:
        counts = {
            1: "single",
            2: "double",
            3: "triple",
        }
        for f in glob.glob("./img/ref/*.jpg"):
            c = process_card(f)
            n = os.path.basename(f).split("-")
            if n[0] != c["color"]:
                print(f"Mismatched color in {f}")
            if n[1] != counts[c["count"]]:
                print(f"Mismatched count in {f}")
            if n[2] != c["fill"]:
                print(f"Mismatched fill in {f}")
            if os.path.splitext(n[3])[0] != c["shape"]:
                print(f"Mismatched shape in {f}: {n[3]} vs {c['shape']}")


if __name__ == "__main__":
    main()