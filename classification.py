"""Classification of card attributes."""

import glob
import math
import os
import sys

import cv2
import numpy as np


def bicolorize(img_bgr):
    """Convert the card image to use a single color for the shape(s) and white for the card."""
    # NB: These values are pretty sensitive: need to be low to pick up fuzzy stripes, but too
    # low and then the edge of the shape interferes with getting a good contour.
    VALUE_THRESHOLD = 60
    SATURATION_THRESHOLD = 35

    # In HSV, determine shape vs. card.
    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

    # Assume the first and last rows are all card-coloured.
    card_sample = np.vstack((img_hsv[:15, :, :], img_hsv[-15:, :, :])).reshape((-1, 3))
    (card_h, card_s, card_v) = card_sample.mean(axis=0)

    # Build a mask for shape vs. card.
    s = np.abs(img_hsv[:, :, 1] - card_s) >= SATURATION_THRESHOLD
    v = np.abs(img_hsv[:, :, 2] - card_v) >= VALUE_THRESHOLD
    shape_mask = s | v

    # Flatten the shape to a single (average + saturated) colour.
    shape_bgr = img_bgr[shape_mask].reshape((-1, 3)).mean(axis=0)

    # Saturate the shape colour.
    card_bgr = cv2.cvtColor(np.uint8([[[card_h, card_s, card_v]]]), cv2.COLOR_HSV2BGR)
    max_c = card_bgr.max()
    min_c = shape_bgr.min()
    s = shape_bgr.astype(np.float32)
    s = 255 * (s - min_c) / (max_c - min_c)
    s = np.clip(s, 0, 255)
    shape_bgr = s.astype(np.uint8)

    # Apply the mask and palette.
    img_bgr[shape_mask] = shape_bgr
    img_bgr[np.invert(shape_mask)] = (255, 255, 255)

    return img_bgr


def classify_color(bgr):
    """Given a sample BGR-valued pixel, determine its Set color."""
    BGR_COLOR_AVGS = {
        "red": (0, 36, 225),
        "green": (62, 122, 0),
        "purple": (86, 0, 75)
    }

    def color_diff(bgr1, bgr2):
        # From https://www.compuphase.com/cmetric.htm
        (b1, g1, r1) = bgr1
        (b2, g2, r2) = bgr2
        r_mean = (r1 + r2) / 2
        r = r1 - r2
        g = g1 - g2
        b = b1 - b2
        return math.sqrt((int((512+r_mean)*r*r) >> 8) + 4*g*g + (int((767-r_mean)*b*b) >> 8))

    color_diffs = {
        c: color_diff(bgr, avg) for c, avg in BGR_COLOR_AVGS.items()
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


def classify_card(img_bgr):
    """Given a card image, return its Set attributes."""
    MIN_SHAPE_AREA_FRACTION = 0.1

    bicolor = bicolorize(img_bgr.copy())
    cv2.imwrite("/tmp/bicolor.png", bicolor)

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

    return classification


def main():
    def process_card(file):
        c = classify_card(cv2.imread(file))
        print(f"{c}")
        return c

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
