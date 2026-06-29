# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_font(size: int) -> ImageFont.ImageFont:
    for candidate in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/arial.ttf"):
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                pass
    return ImageFont.load_default()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    bg = "#111827"
    panel = "#F8FAFC"
    muted = "#D9DEE8"
    line = "#2F3A4A"
    block = "#111827"

    draw.rounded_rectangle([28, 34, 228, 178], radius=22, fill=bg)
    draw.rounded_rectangle([43, 49, 213, 163], radius=12, fill=panel)

    for x in (86, 128, 170):
        draw.line([x, 62, x, 150], fill=muted, width=4)
    for y in (86, 124):
        draw.line([58, y, 198, y], fill=muted, width=4)

    blocks = [
        [63, 68, 96, 98],
        [116, 65, 149, 96],
        [163, 91, 196, 122],
        [83, 120, 116, 150],
        [134, 118, 167, 149],
    ]
    for box in blocks:
        draw.rounded_rectangle(box, radius=7, fill=block)

    draw.line([96, 83, 116, 80], fill=line, width=6)
    draw.line([149, 80, 163, 106], fill=line, width=6)
    draw.line([116, 135, 134, 133], fill=line, width=6)

    draw.rounded_rectangle([108, 178, 148, 198], radius=7, fill=bg)
    draw.rounded_rectangle([75, 198, 181, 215], radius=8, fill=bg)

    image.save(assets / "app.png")
    image.save(assets / "app.ico", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])


if __name__ == "__main__":
    main()
