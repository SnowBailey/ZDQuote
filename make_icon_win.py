"""生成 ZDQuote Windows 图标 ZDQuote.ico（多尺寸，含透明）。

蓝底圆角 + 白色 "ZD"，与 macOS 版视觉一致。
用法：python make_icon_win.py  ->  产出 ZDQuote.ico
"""
import os
from PIL import Image, ImageDraw, ImageFont

S = 512
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ZDQuote.ico")
BLUE = (31, 111, 235, 255)


def _load_font(size):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def render() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=BLUE)

    font = _load_font(int(S * 0.42))
    text = "ZD"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(
        ((S - tw) / 2 - bbox[0], (S - th) / 2 - bbox[1]),
        text, fill=(255, 255, 255, 255), font=font,
    )
    return img


def main():
    img = render()
    # 先放大到 2x 再缩回做轻微抗锯齿，然后保存多尺寸 .ico
    big = img.resize((S * 2, S * 2), Image.LANCZOS)
    smooth = big.resize((S, S), Image.LANCZOS)
    smooth.save(
        OUT,
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
               (128, 128), (256, 256)],
    )
    print("生成图标:", OUT)


if __name__ == "__main__":
    main()
