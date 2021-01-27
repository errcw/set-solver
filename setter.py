"""Detection!"""

import glob
import os
import sys

import cv2
import imagehash
from PIL import Image
import numpy as np

import noteshrink

class CardImage:
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))

    @staticmethod
    def FromFile(file):
        img = cv2.imread(file)
        img_rgb = noteshrink_card_from_im(img, file)

        pil = Image.fromarray(img_rgb)
        phash = imagehash.phash(pil, hash_size=24)
        whash = imagehash.whash(pil, hash_size=32)

        # TODO
        whash = imagehash.phash(pil, hash_size=16)
        return CardImage(file, phash, whash)

    def __init__(self, name, phash, dhash):
        self.name = name
        self.phash = phash
        self.dhash = dhash

    def diff(self, other):
        return self.dhash - other.dhash
        #pdiff = self.phash - other.phash
        #ddiff = self.dhash - other.dhash
        #return math.hypot(pdiff, ddiff)


def noteshrink_card_from_im(card_im):
    tmp_file = "/tmp/to-noteshrink.tmp.png"
    cv2.imwrite(tmp_file, card_im)
    noteshrunk_file = noteshrink_card_from_file(tmp_file)
    noteshrunk_im = cv2.imread(noteshrunk_file)
    noteshrunk_im = cv2.cvtColor(noteshrunk_im, cv2.COLOR_BGR2RGB)
    return noteshrunk_im

def noteshrink_card_from_file(card_filename):
    img, dpi = noteshrink.load(card_filename)
    options = noteshrink.get_argument_parser(
        # hack to give a required argument from outside sys.argv
        filenames=[card_filename]
    ).parse_args()
    options.num_colors = 2
    options.white_bg = True
    options.quiet = True

    output_filename = "/tmp/did-noteshrink.tmp.png"

    samples = noteshrink.sample_pixels(img, options)
    palette = noteshrink.get_palette(samples, options)

    labels = noteshrink.apply_palette(img, palette, options)

    noteshrink.save(output_filename, labels, palette, dpi, options)
    return output_filename


def classify_color(rgb):
    """Given a sample RGB-valued pixel, determine its Set color."""
    rgb_color_avgs = {"red": (226, 34, 0), "green": (0, 123, 64), "purple": (76, 0, 89)}
    color_diffs = {
        c: sum(abs(rgb_color_avgs[c] - rgb)) for c in rgb_color_avgs
    }
    color = min(color_diffs, key=color_diffs.get)
    return color

def has_color(pixel):
    return sum(pixel) < 255 * 3

def classify_fill_color(shape_img):
    #cv2.imwrite("/tmp/shape.png", shape_img)
    sample_row = int(shape_img.shape[0] / 2)

    fill_count = 0
    line_count = 0
    color = None
    for i, pixel in enumerate(shape_img[sample_row][1:]):
        if has_color(pixel):
            fill_count += 1
            if not color:
                color = classify_color(pixel)
            if not has_color(shape_img[sample_row][i-1]):
                line_count += 1

    fill_ratio = fill_count / float(shape_img.shape[1])
    #fills[cur_fill].append(fill_ratio)
    #print(f"Fraction of nonwhite is {fill_ratio}")

    fill = None
    if fill_ratio > 0.5:
        fill = "solid"
    else:
        # Distinguish between outline and line
        if line_count > 5:
            fill = "stripes"
        else:
            fill = "outline"

    return (fill, color)

def classify_shape(shape_contour):
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

fills = {
    "outline": [],
    "stripes": [],
    "solid": [],
}
counts = {
    1: "single",
    2: "double",
    3: "triple",
}
cur_fill = None
cur_file = None

def classify_card(img):
    bicolor = noteshrink_card_from_im(img)

    gray = cv2.cvtColor(bicolor, cv2.COLOR_RGB2GRAY)
    # Invert, otherwise RETR_EXTERNAL makes the whole card the largest contour
    gray = cv2.bitwise_not(gray)

    contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    classification = {"count": 0}
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w * h / img.shape[0] * img.shape[1] < MIN_SHAPE_AREA_FRACTION:
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


def process_card(file):
    # global cur_fill, cur_file
    # cur_fill = os.path.basename(file).split("-")[2]
    # cur_file = file
    return classify_card(cv2.imread(file))

def main2():
    #for f in glob.glob("./img/ref/*.jpg"):
    #    c = process_card(f)
    #    n = os.path.basename(f).split("-")
    #    if n[0] != c["color"]:
    #        print(f"Mismatched color in {f}")
    #    if n[1] != counts[c["count"]]:
    #        print(f"Mismatched count in {f}")
    #    if n[2] != c["fill"]:
    #        print(f"Mismatched fill in {f}")
    #    if os.path.splitext(n[3])[0] != c["shape"]:
    #        print(f"Mismatched shape in {f}: {n[3]} vs {c['shape']}")

    #for f, c in fills.items():
    #    print(f"mean {f} = {np.mean(c)}")
    #    print(f"median {f} = {np.median(c)}")
    #    print(f"std {f} = {np.std(c)}")
    #    print(f"max {f} = {np.max(c)}")
    #    print(f"min {f} = {np.min(c)}")

    process_card(sys.argv[1])

def main():
    refs = []
    for f in glob.glob("./img/ref/*.jpg"):
        img = CardImage.FromFile(f)
        refs.append(img)

    test = CardImage.FromFile(sys.argv[1])

    min_diff = float('inf')
    best = None
    for ref in refs:
        #diff = test.phash - ref.phash
        diff = test.diff(ref)
        print(f"{test.name} vs {ref.name}: diff={diff}")
        if diff < min_diff:
            min_diff = diff
            best = ref
    print(f"Best for {test.name} is {best.name} (diff={min_diff})")

if __name__ == "__main__":
    main2()