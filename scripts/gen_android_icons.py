"""从 Web 端图标生成安卓各密度 mipmap 图标（依赖 Pillow）。"""

import os
import sys

from PIL import Image

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(REPO_ROOT, "frontend", "public", "icons", "icon-512.png")
RES_DIR = os.path.join(REPO_ROOT, "android", "app", "src", "main", "res")

# Android 各密度下 launcher 图标的基准尺寸
DENSITIES = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}


def main() -> int:
    if not os.path.exists(SOURCE):
        print("缺少源图标：%s" % SOURCE, file=sys.stderr)
        return 1

    with Image.open(SOURCE) as base:
        base = base.convert("RGBA")
        for density, size in DENSITIES.items():
            out_dir = os.path.join(RES_DIR, "mipmap-" + density)
            os.makedirs(out_dir, exist_ok=True)
            icon = base.resize((size, size), Image.LANCZOS)
            icon.save(os.path.join(out_dir, "ic_launcher.png"), "PNG")
            print("生成 mipmap-%s/ic_launcher.png (%dx%d)" % (density, size, size))

    return 0


if __name__ == "__main__":
    sys.exit(main())