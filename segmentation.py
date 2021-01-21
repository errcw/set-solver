import copy
import math
import sys

import cv2
import numpy as np
from shapely.geometry import Polygon

class Line(object):
    def __init__(self, p1, p2):
        v = p2 - p1
        a = -v[1]
        b = v[0]
        c = -(a * p1[0] + b * p1[1])
        self.p1 = p1
        self.p2 = p2
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
            vec = self.p2 - self.p1
            self.length = math.hypot(vec[0], vec[1])
        return self.length
        
    def relativeAngle(self, o):
        vec1 = self.p2 - self.p1
        vec2 = o.p2 - o.p1
        dot = sum(vec1 * vec2) / self.len() / o.len()
        if dot > 1.0:
            dot = 1.0
        if dot < -1.0:
            dot = -1.0
        return math.acos(dot)


def findRects(lines):
    lines = [Line(line[0][0:2], line[0][2:4]) for line in lines]

    outputLineIndices = set()
    # Create a graph of the edges, connected if they share an endpoint and form a right angle.
    connections = [[] for i in range(len(lines))]

    # Distance between edge endpoints that we still consider connected.
    ENDPOINT_THRESHOLD_PIXELS = 80

    # The shorter dimension must be at least this value
    MIN_WIDTH = 50

    # Allowed delta from 90 degrees between edges.
    # Top-down shots should see very small values here (<5 degrees), perspective ones get much larger
    ANGLE_THRESHOLD_DEGREES = 20

    MIN_ASPECT = 1.3
    MAX_ASPECT = 1.9

    # % difference in dimension sizes allowed between found cards.
    # Most of the difference is from the perspective transform, purely top-down shots allow a much smaller value
    ALLOWED_DIM_DIFF = 0.5

    def formsCorner(A, B):
        # If lines A & B form a valid corner, returns the "cost", otherwise False
        # The cost is distance from the segments to their mutual intersection
        cost = 0
        p = A.intersect(B)
        if p is None:
            return False

        aToP = A.p2 - p 
        distAp = math.hypot(aToP[0], aToP[1])
        bToP = B.p1 - p
        distBp = math.hypot(bToP[0], bToP[1])
        if distAp > ENDPOINT_THRESHOLD_PIXELS and distBp > ENDPOINT_THRESHOLD_PIXELS:
            return False
        cost = distAp + distBp

        theta = A.relativeAngle(B)
        thetaDegrees = theta / math.pi * 180
        deltaFromRightAngle = abs(90 - thetaDegrees)
        if deltaFromRightAngle > ANGLE_THRESHOLD_DEGREES:
            return False

        return cost

    print("Generating connectivity")
    for i in range(len(lines)):
        A = lines[i]
        if A.len() < ENDPOINT_THRESHOLD_PIXELS / 2:
            continue

        for j in range(i + 1, len(lines)):
            B = lines[j]

            if B.len() < ENDPOINT_THRESHOLD_PIXELS / 2:
                continue

            # Edges are directed, so we only allow the end of one to connect to the beginning of the other.
            AB = formsCorner(A, B)
            if AB is not False:
                connections[i].append([j, AB])
            
            BA = formsCorner(B, A)
            if BA is not False:
                connections[j].append([i, BA])



    memo = {}
    # Find any 4-cycles in the graph. 
    def findNCycles(dest, cur, stepsLeft):
        # Can find a cycle from any node in the cycle; mandate we only find it from the smallest index
        if cur < dest:
            return []

        if stepsLeft == 0:
            if cur == dest:
                # Using the first element of the array to pass back the cost...
                return [[0, dest]]
            else:
                return []

        output = []

        key = (dest, cur, stepsLeft)
        if key in memo:
            return copy.deepcopy(memo[key])

        for nextNode in connections[cur]:
            next, nextCost = nextNode
            results = findNCycles(dest, next, stepsLeft - 1)
            for result in results:
                result[0] += nextCost
            output.extend(results)
        
        output = [val + [cur] for val in output if val[0] < MIN_WIDTH * 6] 
        memo[key] = copy.deepcopy(output)
        return output
    

    widths = []
    heights = []
    aspects = []

    outputRects = []

    potentialRects = []

    def goodRect(idxs):
        L = [lines[idx] for idx in idxs[0:4]]

        L = [Line(L[i-1].intersect(L[i]), L[i].intersect(L[(i+1)%4])) for i in range(4)]

        lens = [line.len() for line in L]

        # Check that side lengths are equal'ish
        if abs(lens[0] - lens[2]) > ENDPOINT_THRESHOLD_PIXELS:
            #print "uneven sides"
            return False

        if abs(lens[1] - lens[3]) > ENDPOINT_THRESHOLD_PIXELS:
            #print "uneven sides"
            return False

        width = (lens[0] + lens[2]) / 2
        height = (lens[1] + lens[3]) / 2

        width, height = (min(width, height), max(width, height))

        if cost > (width + height) / 2:
            #print "Bad cost"
            return False
        
        if width < MIN_WIDTH:
            #print "Too small"
            return False

        aspect = height / width
        if aspect < MIN_ASPECT or aspect > MAX_ASPECT:
            return False


        if widths:
            avgWidth = sum(widths) / len(widths)
            avgHeight = sum(heights) / len(heights)
            widthErr = abs(float(width - avgWidth) / avgWidth)
            heightErr = abs(float(height - avgHeight) / avgHeight)
            if heightErr > ALLOWED_DIM_DIFF or widthErr > ALLOWED_DIM_DIFF:
                #print "Too much relative error %s, %s" % (widthErr, heightErr)
                return False
        
        curPoly = Polygon([l.p1 for l in L])
        for rect in outputRects:
            outPoly = Polygon(rect)

            if outPoly.intersection(curPoly).area / outPoly.area > 0:
                #print "Intersects"
                return False
            
        return [width, height]



    print("Finding rectangles")
    for i in range(len(lines)):
        if i in outputLineIndices:
            continue
        memo = {}
        cycles = findNCycles(i, i, 4)
        for cycle in cycles:
            cost = cycle[0]
            cycle = cycle[1:]
            
            potentialRects.append([cost, cycle])


    print("Evaluating %d potential rectangles" % len(potentialRects))
    for potentialRect in sorted(potentialRects):
        cost, cycle = potentialRect
        if widths and cost > sum(widths) / len(widths) * 2:
            break
        unique = True
        for idx in cycle:
            if idx in outputLineIndices:
                unique = False
                break
        if not unique:
            continue


        dims = goodRect(cycle)
        if dims:
            width = min(dims[0], dims[1])
            height = max(dims[0], dims[1])
            widths.append(int(width))
            heights.append(int(height))
            aspects.append(int(height * 100 / width) / 100.0)

            angleSum = 0

            rect = []
            for idx in range(len(cycle) - 1):
                outputLineIndices.add(cycle[idx])

                iA = cycle[idx]
                iB = cycle[(idx + 1) % len(cycle)]
                rect.append(lines[iA].intersect(lines[iB]))
            arr = np.array(rect, np.float32)
            outputRects.append(arr)

    print(widths)
    print(heights)
    print(aspects)
    print("%s - %s" % (min(aspects), max(aspects)))

    return outputRects 


def order_points(pts):
	# initialzie a list of coordinates that will be ordered
	# such that the first entry in the list is the top-left,
	# the second entry is the top-right, the third is the
	# bottom-right, and the fourth is the bottom-left
	rect = np.zeros((4, 2), np.float32)
	# the top-left point will have the smallest sum, whereas
	# the bottom-right point will have the largest sum
	s = pts.sum(axis = 1)
	rect[0] = pts[np.argmin(s)]
	rect[2] = pts[np.argmax(s)]
	# now, compute the difference between the points, the
	# top-right point will have the smallest difference,
	# whereas the bottom-left will have the largest difference
	diff = np.diff(pts, axis = 1)
	rect[1] = pts[np.argmin(diff)]
	rect[3] = pts[np.argmax(diff)]
	# return the ordered coordinates
	return rect


def get_rects(gray, light):
    fld = cv2.ximgproc.createFastLineDetector()
    lines = []
    for img in [gray, light]:
        img = cv2.medianBlur(img, 9)
        cur = fld.detect(img)
        for line in cur:
            lines.append(np.array(line))
    return findRects(lines)


def segment_to_rects(img):
    w, h = (img.shape[0], img.shape[1])
    scale = 1024.0 / min(w, h)
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    rects = get_rects(gray, s)

    comp_w = 450
    comp_h = 750
    dst = np.array([
		[0, 0],
		[comp_w, 0],
		[comp_w, comp_h],
		[0, comp_h]], np.float32)

    rect_imgs = []
    for rect in rects:
        xform = cv2.getPerspectiveTransform(order_points(rect), dst)
        rect_img = cv2.warpPerspective(img, xform, (comp_w, comp_h))
        rect_imgs.append(rect_img)
    return rect_imgs


if __name__ == "__main__":
    img = cv2.imread(sys.argv[1])
    for i, r in enumerate(segment_to_rects(img)):
        cv2.imwrite("%s.rect.%d.png" % (sys.argv[2], i), r)