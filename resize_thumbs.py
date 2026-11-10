from PIL import Image
import os

# 配置
SRC_DIR = r"static/images"
DST_DIR = r"static/thumbs"
MAX_WIDTH = 800
MAX_HEIGHT = 1000
QUALITY = 85


def make_thumb(src_path, dst_path):
    try:
        with Image.open(src_path) as im:
            # 处理png透明、palette模式，转RGB输出jpg
            if im.mode in ("P", "RGBA"):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
                im = bg

            im.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            im.save(dst_path, "JPEG", quality=QUALITY, optimize=True)
            print(f"OK: {src_path} -> {dst_path}")
    except Exception as e:
        print(f"ERR {src_path}: {e}")


def walk_gen():
    for root, _, files in os.walk(SRC_DIR):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                continue
            full_src = os.path.join(root, name)
            rel = os.path.relpath(full_src, SRC_DIR)
            # 输出统一改成jpg后缀
            rel_noext = os.path.splitext(rel)[0]
            full_dst = os.path.join(DST_DIR, rel_noext + ".jpg")
            make_thumb(full_src, full_dst)


if __name__ == "__main__":
    walk_gen()
