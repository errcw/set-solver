import copy
import glob
import math
import sys

import cv2
import imagehash
import numpy as np
from shapely.geometry import Polygon
from PIL import Image

clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))

class ReferenceCard:
    @staticmethod
    def from_file(file):
        img = cv2.imread(file)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l_corrected = clahe.apply(l)
        lab_corrected = cv2.merge((l_corrected, a, b))
        img_rgb = cv2.cvtColor(lab_corrected, cv2.COLOR_LAB2RGB)
        pil = Image.fromarray(img_rgb)
        phash = imagehash.phash(pil, hash_size=32)
        return ReferenceCard(file, phash)

    def __init__(self, name, phash):
        self.name = name
        self.phash = phash

class DetectedCard:
    def __init__(self, img_rgb, rect):
        pil = Image.fromarray(img_rgb)
        self.phash = imagehash.phash(pil, hash_size=32)
        self.rect = rect

class RefCardSet:
    @staticmethod
    def from_files(file_glob):
        refs = []
        for f in glob.glob(file_glob):
            img = ReferenceCard.from_file(f)
            refs.append(img)

    def __init__(self, refs):
        self.refs = refs

    def find_best_match(self, detected):
        min_diff = float('inf')
        best = None
        for ref in self.refs:
            diff = detected.phash - ref.phash
            print("%s vs %s: diff %s" % (detected.name, ref.name, diff))
            if diff < min_diff:
                min_diff = diff
                best = ref
        return best

class Line(object):
    def __init__(self, p1, p2):
        vec = p2 - p1
        a = -vec[1]
        b = vec[0]
        c = -(a * p1[0] + b * p1[1])
        self.p1 = p1
        self.p2 = p2
        self.vec = vec
        self.a = a
        self.b = b
        self.c = c

    def intersect(self, o):
        w = self.a * o.b - self.b * o.a
        if w == 0:
            return None
        x = (self.b * o.c - o.b * self.c) / w
        y = (o.a * self.c - self.a * o.c) / w
        return np.array([x, y])
 
    def len(self):
        if not hasattr(self, 'length'):
            self.length = math.hypot(self.vec[0], self.vec[1])
        return self.length

    def relative_angle(self, o):
        dot = sum(self.vec * o.vec) / self.len() / o.len()
        if dot > 1.0:
            dot = 1.0
        if dot < -1.0:
            dot = -1.0
        return math.acos(dot)


def find_rects_from_lines(lines):
    lines = [Line(line[0][0:2], line[0][2:4]) for line in lines]

    out_line_indices = set()
    # Create a graph of the edges, connected if they share an endpoint and form a right angle.
    connections = [[] for i in range(len(lines))]

    # Distance between edge endpoints that we still consider connected.
    ENDPOINT_THRESHOLD_PIXELS = 80

    # Allowed delta from 90 degrees between edges.
    # Top-down shots should see very small values here (<5 degrees), perspective ones get much larger
    ANGLE_THRESHOLD_RADIANS = 0.35

    # The shorter dimension must be at least this value
    MIN_WIDTH = 50

    MIN_ASPECT = 1.3
    MAX_ASPECT = 1.9

    # % difference in dimension sizes allowed between found cards.
    # Most of the difference is from the perspective transform, purely top-down shots allow a much smaller value
    ALLOWED_DIM_DIFF = 0.5

    def is_corner(a, b):
        # If lines a & b form a valid corner, returns the "cost", otherwise False.
        # The cost is distance from the segments to their mutual intersection.
        cost = 0
        intersection = a.intersect(b)
        if intersection is None:
            return False

        a_to_int = a.p2 - intersection
        dist_a_to_int = math.hypot(a_to_int[0], a_to_int[1])
        b_to_int = b.p1 - intersection
        dist_b_to_int = math.hypot(b_to_int[0], b_to_int[1])
        if dist_a_to_int > ENDPOINT_THRESHOLD_PIXELS and dist_b_to_int > ENDPOINT_THRESHOLD_PIXELS:
            return False
        cost = dist_a_to_int + dist_b_to_int

        angle = a.relative_angle(b)
        delta_from_right_angle = abs(math.pi / 2 - angle)
        if delta_from_right_angle > ANGLE_THRESHOLD_RADIANS:
            return False

        return cost

    for i in range(len(lines)):
        a = lines[i]
        if a.len() < ENDPOINT_THRESHOLD_PIXELS / 2:
            continue

        for j in range(i + 1, len(lines)):
            b = lines[j]
            if b.len() < ENDPOINT_THRESHOLD_PIXELS / 2:
                continue

            # Edges are directed, so we only allow the end of one to connect to the beginning of the other.
            ab = is_corner(a, b)
            if ab is not False:
                connections[i].append([j, ab])

            ba = is_corner(b, a)
            if ba is not False:
                connections[j].append([i, ba])

    memo = {}
    def find_n_cycles(dest, cur, steps_left):
        # Can find a cycle from any node in the cycle; mandate we only find it from the smallest index
        if cur < dest:
            return []

        if steps_left == 0:
            if cur == dest:
                # Using the first element of the array to pass back the cost...
                return [[0, dest]]
            else:
                return []

        output = []

        key = (dest, cur, steps_left)
        if key in memo:
            return copy.deepcopy(memo[key])

        for next_node in connections[cur]:
            next_idx, next_cost = next_node
            results = find_n_cycles(dest, next_idx, steps_left - 1)
            for result in results:
                result[0] += next_cost
            output.extend(results)

        output = [val + [cur] for val in output if val[0] < MIN_WIDTH * 6] 
        memo[key] = copy.deepcopy(output)
        return output

    # Find any 4-cycles in the line graph. 
    potential_rects = []
    for i in range(len(lines)):
        cycles = find_n_cycles(i, i, 4)
        for cycle in cycles:
            cost = cycle[0]
            cycle = cycle[1:]
            potential_rects.append([cost, cycle])


    def good_rect(indices):
        L = [lines[idx] for idx in indices[0:4]]
        L = [Line(L[i-1].intersect(L[i]), L[i].intersect(L[(i+1)%4])) for i in range(4)]
        lens = [line.len() for line in L]

        # Check that side lengths are equal'ish
        if abs(lens[0] - lens[2]) > ENDPOINT_THRESHOLD_PIXELS:
            return False
        if abs(lens[1] - lens[3]) > ENDPOINT_THRESHOLD_PIXELS:
            return False

        width = (lens[0] + lens[2]) / 2
        height = (lens[1] + lens[3]) / 2

        width, height = (min(width, height), max(width, height))

        if cost > (width + height) / 2:
            return False

        if width < MIN_WIDTH:
            return False

        aspect = height / width
        if aspect < MIN_ASPECT or aspect > MAX_ASPECT:
            return False

        if widths:
            avg_width = sum(widths) / len(widths)
            avg_height = sum(heights) / len(heights)
            width_err = abs(float(width - avg_width) / avg_width)
            height_err = abs(float(height - avg_height) / avg_height)
            if height_err > ALLOWED_DIM_DIFF or width_err > ALLOWED_DIM_DIFF:
                return False

        cur_poly = Polygon([l.p1 for l in L])
        for rect in output_rects:
            out_poly = Polygon(rect)
            if out_poly.intersection(cur_poly).area / out_poly.area > 0:
                return False

        return [width, height]

    print("Evaluating %d potential rectangles" % len(potential_rects))

    widths = []
    heights = []
    aspects = []

    output_rects = []

    for potential_rect in sorted(potential_rects):
        cost, cycle = potential_rect
        if widths and cost > sum(widths) / len(widths) * 2:
            break
        unique = True
        for idx in cycle:
            if idx in out_line_indices:
                unique = False
                break
        if not unique:
            continue

        dims = good_rect(cycle)
        if dims:
            width = min(dims[0], dims[1])
            height = max(dims[0], dims[1])
            widths.append(int(width))
            heights.append(int(height))
            aspects.append(int(height * 100 / width) / 100.0)

            rect = []
            for idx in range(len(cycle) - 1):
                out_line_indices.add(cycle[idx])

                i_a = cycle[idx]
                i_b = cycle[(idx + 1) % len(cycle)]
                rect.append(lines[i_a].intersect(lines[i_b]))

            output_rects.append(np.array(rect, np.float32))

    return output_rects 


def order_points(pts):
    rect = np.zeros((4, 2), np.float32)
    # top left: smallest sum
    # bottom right: largest sum
    add = pts.sum(axis=1)
    rect[0] = pts[np.argmin(add)]
    rect[2] = pts[np.argmax(add)]
    # top right: smallest difference
    # bottom right: largest difference
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def find_rects(gray, light):
    fld = cv2.ximgproc.createFastLineDetector()
    all_lines = []
    for img in [gray, light]:
        img = cv2.medianBlur(img, 9)
        lines = fld.detect(img)
        for line in lines:
            all_lines.append(np.array(line))
    return find_rects_from_lines(all_lines)


def detect_cards(img):
    scale = 1024.0 / min(img.shape[0], img.shape[1])
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l_corrected = clahe.apply(l)

    rgb_corrected = cv2.cvtColor(cv2.merge((l_corrected, a, b)), cv2.COLOR_LAB2RGB)

    rects = find_rects(gray, l_corrected)

    comp_w = 450
    comp_h = 750
    dst = np.array([
		[0, 0],
		[comp_w, 0],
		[comp_w, comp_h],
		[0, comp_h]], np.float32)

    cards = []
    for rect in rects:
        xform = cv2.getPerspectiveTransform(order_points(rect), dst)
        rect_img = cv2.warpPerspective(rgb_corrected, xform, (comp_w, comp_h))

        rect_orig = (rect * 1/scale).astype(np.int32)
        cards.append(DetectedCard(rect_img, rect_orig))
    return cards


def main():
    img = cv2.imread(sys.argv[1])
    for i, card in enumerate(detect_cards(img)):
        print(f"Detected card {i} at {card.rect}")
        cv2.polylines(img, [card.rect], True, (52, 64, 255), 10)
    cv2.imwrite(f"{sys.argv[2]}.png", img)

if __name__ == "__main__":
    main()