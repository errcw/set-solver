"""Lambda function to process/solve a game image."""

import json
import base64

import cv2
import numpy as np

import segmentation
import classification
import solve

def lambda_handler(event, context):
    img_data = base64.b64decode(event["body"])
    img = cv2.imdecode(np.fromstring(img_data, np.uint8), cv2.IMREAD_COLOR)

    cards = []
    for i, card_seg in enumerate(segmentation.detect_cards(img)):
        classified = classification.classify_card(card_seg.img_bgr)
        cards.append(solve.Card(classified, card_seg.rect))
    sets = solve.Card.find_sets(cards)

    card_rects = {
        c.label: [[int(x), int(y)] for [x, y] in c.rect] for c in cards
    }
    sets = [
        (c0.label, c1.label, c2.label) for (c0, c1, c2) in sets
    ]
    return_body = {
        "cards": card_rects,
        "sets": sets,
    }

    return {
        "statusCode": 200,
        "body": json.dumps(return_body)
    }
