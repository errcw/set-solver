"""Detection!"""

import glob

import cv2
import imagehash
from PIL import Image

class CardImage:
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))

    @staticmethod
    def FromFile(file):
        img = cv2.imread(file)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l_corrected = CardImage.clahe.apply(l)
        lab_corrected = cv2.merge((l_corrected, a, b))
        img_rgb = cv2.cvtColor(lab_corrected, cv2.COLOR_LAB2RGB)
        pil = Image.fromarray(img_rgb)
        phash = imagehash.phash(pil, hash_size=32)
        return CardImage(file, phash)

    def __init__(self, name, phash):
        self.name = name
        self.phash = phash

def main():
    refs = []
    for f in glob.glob("./img-ref/*.png"):
        img = CardImage.FromFile(f)
        print("%s: %s" % (img.name, img.phash))
        refs.append(img)

    for f in glob.glob("./img-test/*.png"):
        test = CardImage.FromFile(f)

        min_diff = float('inf')
        best = None
        for ref in refs:
            diff = test.phash - ref.phash
            print("%s vs %s: diff %s" % (test.name, ref.name, diff))
            if diff < min_diff:
                min_diff = diff
                best = ref
        print("Best for %s is %s" % (test.name, best.name))

if __name__ == "__main__":
    main()