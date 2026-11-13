"""Generate PWA icons: white star on warm orange rounded square (星灿)."""
import math
import os

from PIL import Image, ImageDraw


def star_points(cx, cy, r_outer, r_inner, n=5, rot=-math.pi / 2):
    pts = []
    for i in range(n * 2):
        r = r_outer if i % 2 == 0 else r_inner
        a = rot + i * math.pi / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def make_icon(size, path):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    top, bottom = (255, 176, 58), (255, 122, 60)
    bg = Image.new("RGBA", (size, size))
    bd = ImageDraw.Draw(bg)
    for y in range(size):
        t = y / max(size - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
        bd.line([(0, y), (size, y)], fill=color)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255)
    img.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.polygon(star_points(size / 2, size * 0.52, size * 0.36, size * 0.15), fill=(255, 255, 255, 255))
    img.save(path)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "public", "icons")
    os.makedirs(out, exist_ok=True)
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        make_icon(size, os.path.join(out, name))
    print("icons generated:", out)