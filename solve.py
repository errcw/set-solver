"""Solve a game board."""

import sys

import cv2

import classification
import segmentation


def label(classified):
    count = classified["count"]
    fill = classified["fill"]
    color = classified["color"]
    shape = classified["shape"]
    return f"{count}-{fill}-{color}-{shape}"

def main():
    img = cv2.imread(sys.argv[1])

    for i, card in enumerate(segmentation.detect_cards(img)):
        cv2.imwrite(f"{sys.argv[2]}.rects.{i}.png", card.img_bgr)

        c = classification.classify_card(card.img_bgr)
        print(f"Card {i}: {c}")

        cv2.polylines(img, [card.rect], True, (52, 64, 255), 10)
        cv2.putText(img, f"{label(c)} ({i})", (card.rect[0][0], card.rect[0][1]), cv2.FONT_HERSHEY_PLAIN, 2, (255, 255, 255), 5)

    cv2.imwrite(f"{sys.argv[2]}.png", img)

if __name__ == "__main__":
    main()