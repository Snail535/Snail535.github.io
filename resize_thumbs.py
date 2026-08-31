from PIL import Image
import os

# ========== 配置区，按需修改 ==========
SOURCE_FOLDER = "static/images"    # 原图文件夹
TARGET_FOLDER = "static/thumbs"   # 缩略图输出文件夹
MAX_LONG_SIDE = 600                # 缩略图长边最大像素
QUALITY = 85                       # jpg/webp画质 0‑100
# 支持的图片后缀
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
# ====================================


def make_thumbnail(src_path: str, dst_path: str):
    # 创建输出文件夹
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    # 如果缩略图已经存在，跳过，不重复生成
    if os.path.exists(dst_path):
        print(f"跳过已存在: {dst_path}")
        return

    try:
        with Image.open(src_path) as img:
            width, height = img.size

            # 关键修复：P调色板模式转RGB，否则无法保存JPG
            if img.mode == "P":
                img = img.convert("RGB")
            # 带透明通道RGBA转RGB（jpg不支持透明）
            if img.mode == "RGBA":
                img = img.convert("RGB")

            # 计算缩放比例，长边等于MAX_LONG_SIDE
            if width >= height:
                new_w = MAX_LONG_SIDE
                new_h = int(height * (MAX_LONG_SIDE / width))
            else:
                new_h = MAX_LONG_SIDE
                new_w = int(width * (MAX_LONG_SIDE / height))

            # LANCZOS高质量缩放
            img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # 保存图片
            if dst_path.lower().endswith(".png"):
                img_resized.save(dst_path, "PNG")
            else:
                img_resized.save(dst_path, quality=QUALITY, optimize=True)

            print(f"生成缩略图: {src_path} -> {dst_path}")
    except Exception as e:
        print(f"❌处理失败 {src_path} ,错误信息: {str(e)}")


def scan_folder():
    for root, _, files in os.walk(SOURCE_FOLDER):
        for filename in files:
            if filename.lower().endswith(IMG_EXT):
                src_file = os.path.join(root, filename)
                # 替换路径 images → thumbs
                rel_path = os.path.relpath(src_file, SOURCE_FOLDER)
                dst_file = os.path.join(TARGET_FOLDER, rel_path)
                make_thumbnail(src_file, dst_file)


if __name__ == "__main__":
    scan_folder()
    print("\n✅ 缩略图扫描处理完成！")
