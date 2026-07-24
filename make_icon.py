"""生成 ZDQuote macOS 应用图标（.icns）。

做法：用 Pillow 渲染一张 1024x1024 蓝底圆角「ZD」图标，
再用系统 sips 缩放出各尺寸 .iconset，最后 iconutil 转 .icns。
"""
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

BASE = 1024
OUT_ICNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ZDQuote.icns")

# 清爽蓝主色 + 浅蓝
BLUE = (46, 90, 172)        # #2E5AAC
BLUE_LT = (90, 140, 220)


def _load_font(size: int):
    """优先用系统无衬线粗体，失败回退 PIL 默认字体。"""
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_base() -> str:
    """渲染 1024x1024 圆角蓝底 + ZD 文字，返回临时 PNG 路径。"""
    img = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 圆角矩形背景（径向感：外深内浅渐变用两层叠加近似）
    radius = int(BASE * 0.22)
    d.rounded_rectangle([0, 0, BASE - 1, BASE - 1], radius=radius,
                        fill=BLUE)
    # 内层浅蓝高光，营造立体
    inset = int(BASE * 0.06)
    d.rounded_rectangle([inset, inset, BASE - 1 - inset, BASE - 1 - inset],
                        radius=int(radius * 0.8), fill=BLUE_LT)
    d.rounded_rectangle([inset, inset, BASE - 1 - inset, BASE - 1 - inset],
                        radius=int(radius * 0.8), outline=BLUE, width=6)

    # ZD 文字（白色）
    font = _load_font(int(BASE * 0.42))
    text = "ZD"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (BASE - tw) / 2 - bbox[0]
    y = (BASE - th) / 2 - bbox[1]
    d.text((x, y), text, font=font, fill=(255, 255, 255, 255))

    fd, png = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(png, "PNG")
    return png


def build_iconset(base_png: str) -> str:
    """按 macOS .iconset 规范生成各尺寸 PNG（尺寸→文件名，避免重复/自复制）。"""
    iconset = tempfile.mkdtemp(suffix=".iconset")
    # (源像素, 输出文件名)；同一文件名只生成一次
    plan = [
        (16,   "icon_16x16.png"),
        (32,   "icon_16x16@2x.png"),
        (32,   "icon_32x32.png"),
        (64,   "icon_32x32@2x.png"),
        (128,  "icon_128x128.png"),
        (128,  "icon_128x128@2x.png"),
        (256,  "icon_256x256.png"),
        (256,  "icon_256x256@2x.png"),
        (512,  "icon_512x512.png"),
        (512,  "icon_512x512@2x.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    seen = set()
    for px, nm in plan:
        if nm in seen:
            continue
        seen.add(nm)
        out = os.path.join(iconset, nm)
        subprocess.run(
            ["sips", "-z", str(px), str(px), base_png, "--out", out],
            check=True, capture_output=True,
        )
    return iconset


def main():
    base = render_base()
    iconset = build_iconset(base)
    subprocess.run(["iconutil", "--convert", "icns", iconset, "-o", OUT_ICNS],
                    check=True)
    print("生成图标:", OUT_ICNS)
    try:
        os.remove(base)
    except Exception:
        pass
    import shutil
    shutil.rmtree(iconset, ignore_errors=True)


if __name__ == "__main__":
    main()
