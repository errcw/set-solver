"""Solve a game board."""

import copy
import sys

import cv2

import classification
import segmentation


class Card:
    COUNTS = {
        1: 0,
        2: 1,
        3: 2,
    }
    FILLS = {
        "solid": 0,
        "outline": 1,
        "stripes": 2,
    }
    COLORS = {
        "red": 0,
        "green": 1,
        "purple": 2,
    }
    SHAPES = {
        "diamond": 0,
        "capsule": 1,
        "squiggle": 2,
    }

    def __init__(self, classified, rect):
        count = classified["count"]
        fill = classified["fill"]
        color = classified["color"]
        shape = classified["shape"]
        self.attrs = (Card.COUNTS[count], Card.FILLS[fill], Card.COLORS[color], Card.SHAPES[shape])
        self.label = f"{count}-{fill}-{color}-{shape}"
        self.rect = rect

    @staticmethod
    def find_sets(cards):
        def id(attrs):
            return (attrs[0] << 6) | (attrs[1] << 4) | (attrs[2] << 2) | (attrs[3] << 0)
        seen_by_id = {}

        sets = []
        for i, card_i in enumerate(cards):
            for j, card_j in enumerate(cards[i+1:], i+1):
                third_attrs = [-(a_i + a_j) % 3 for (a_i, a_j) in zip(card_i.attrs, card_j.attrs)]
                card_k = seen_by_id.get(id(third_attrs))
                if card_k:
                    sets.append((card_i, card_j, card_k))
            seen_by_id[id(card_i.attrs)] = card_i
        return sets

SET_COLORS_BGR = [
    [242, 214, 139],
    [167, 242, 139],
    [139, 167, 242],
    [214, 139, 242],
    [139, 219, 242],
    [222, 247, 134],
]

def expand_rect(rect, amount):
    if amount == 0:
        return rect
    ret = copy.deepcopy(rect)
    ret[0][0] -= amount
    ret[0][1] -= amount
    ret[1][0] += amount
    ret[1][1] -= amount
    ret[2][0] += amount
    ret[2][1] += amount
    ret[3][0] -= amount
    ret[3][1] += amount
    return ret

def main():
    debug = "--debug" in sys.argv

    img = cv2.imread(sys.argv[1])

    cards = []
    for i, card_seg in enumerate(segmentation.detect_cards(img)):
        classified = classification.classify_card(card_seg.img_bgr)
        cards.append(Card(classified, card_seg.rect))

        if debug:
            print(f"Card {i}: {classified}")
            cv2.imwrite(f"{sys.argv[2]}.rects.{i}.png", card_seg.img_bgr)


    sets = Card.find_sets(cards)

    OUTLINE_WIDTH = 50
    label_counts = {}
    for i, set_i in enumerate(sets):
        for card in set_i:
            labels = label_counts.get(card.attrs, 0)
            cv2.polylines(img, [expand_rect(card.rect, labels * OUTLINE_WIDTH)], True, SET_COLORS_BGR[i], OUTLINE_WIDTH)
            label_counts[card.attrs] = labels + 1

    if debug:
        for i, card in enumerate(cards):
            cv2.polylines(img, [card.rect], True, (52, 64, 255), 10)
            cv2.putText(img, f"{card.label} ({i})", (card.rect[0][0], card.rect[0][1]), cv2.FONT_HERSHEY_PLAIN, 2, (255, 255, 255), 5)

    cv2.imwrite(f"{sys.argv[2]}.png", img)


if __name__ == "__main__":
    main()