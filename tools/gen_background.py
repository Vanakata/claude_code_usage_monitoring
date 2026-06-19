#!/usr/bin/env python
"""Генерира dark hacker-themed background варианти (480x320) за дисплея.

Пуска се ръчно за preview: създава work/bg-previews/bg_*.png.
Държи всичко тъмно, за да не убива четимостта на foreground текста.
"""
import os
import random

from PIL import Image, ImageDraw, ImageFont

random.seed(7)
W, H = 480, 320
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT_PATH = os.path.join(ROOT, "turing-smart-screen-python", "res", "fonts",
                         "roboto-mono", "RobotoMono-Regular.ttf")
OUT = os.path.join(ROOT, "work", "bg-previews")
os.makedirs(OUT, exist_ok=True)

GLYPHS = "01ABCDEF{}[]()<>/\\=+*#$%;:.|01010110"
CODE_LINES = [
    "def main():", "  for i in range(n):", "    if token.valid:",
    "    return self.run()", "class Claude(Agent):", "import sys, os",
    "  x = 0xDEADBEEF", "  while True:", "    yield next(stream)",
    "  except Error as e:", "  await client.send()", "0x1A86  0x5722",
    "git commit -m 'wip'", "  hash = sha256(buf)", "  ptr -> 0x00ff",
]


def matrix() -> Image.Image:
    img = Image.new("RGB", (W, H), (6, 9, 7))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT_PATH, 14)
    step = 15
    for x in range(0, W, step):
        head = random.randint(-H, H)
        length = random.randint(6, 22)
        for k in range(length):
            y = head - k * 16
            if 0 <= y < H:
                # head по-ярко, опашката избледнява (но цялото е тъмно)
                g = max(18, 110 - k * 9)
                d.text((x, y), random.choice(GLYPHS), font=f, fill=(8, g, 30))
    return img


def code() -> Image.Image:
    img = Image.new("RGB", (W, H), (7, 9, 11))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT_PATH, 13)
    y = 6
    while y < H:
        line = random.choice(CODE_LINES)
        d.text((8, y), line, font=f, fill=(34, 58, 48))
        y += 17
    # лек scanline ефект
    for sy in range(0, H, 3):
        d.line([(0, sy), (W, sy)], fill=(0, 0, 0), width=1)
    return img


def circuit() -> Image.Image:
    img = Image.new("RGB", (W, H), (7, 10, 14))
    d = ImageDraw.Draw(img)
    trace = (18, 60, 66)
    node = (30, 95, 100)
    for _ in range(70):
        x = random.randint(0, W); y = random.randint(0, H)
        ln = random.randint(20, 90)
        if random.random() < 0.5:
            d.line([(x, y), (min(W, x + ln), y)], fill=trace, width=1)
            d.line([(x + ln, y), (x + ln, y + random.randint(-40, 40))], fill=trace, width=1)
        else:
            d.line([(x, y), (x, min(H, y + ln))], fill=trace, width=1)
        if random.random() < 0.4:
            d.rectangle([x - 2, y - 2, x + 2, y + 2], fill=node)
    # vignette — потъмняване към краищата
    for i in range(60):
        a = int(60 * (i / 60))
        d.rectangle([i, i, W - i, H - i], outline=(0, 0, 0))
    return img


def main():
    for name, fn in (("matrix", matrix), ("code", code), ("circuit", circuit)):
        p = os.path.join(OUT, f"bg_{name}.png")
        fn().save(p)
        print("wrote", p)


if __name__ == "__main__":
    main()
