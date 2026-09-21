# optimize_frames.py
import os
from PIL import Image

FRAMES_DIR = r"I:\XMWJ\PYxm\tongshengxiang\static\frames"

# 目标宽度（手机屏幕 720 足够）
TARGET_WIDTH = 540

# 压缩质量（60-70 是甜点，肉眼看不出差别但体积减半）
QUALITY = 65

def optimize(path):
    img = Image.open(path).convert("RGB")
    w, h = img.size

    # 缩放到目标宽度
    if w > TARGET_WIDTH:
        new_h = int(h * TARGET_WIDTH / w)
        img = img.resize((TARGET_WIDTH, new_h), Image.LANCZOS)

    # 保存为 JPG，质量 65
    img.save(path, "JPEG", quality=QUALITY, optimize=True)

    size_kb = os.path.getsize(path) / 1024
    print(f"{os.path.basename(path):12s} -> {size_kb:.1f} KB")

def main():
    files = sorted([f for f in os.listdir(FRAMES_DIR)
                    if f.lower().endswith(('.jpg', '.jpeg'))])
    if not files:
        print("没找到 JPG 文件")
        return

    print(f"共 {len(files)} 张图，开始压缩...\n")
    total_before = 0
    total_after = 0
    for f in files:
        p = os.path.join(FRAMES_DIR, f)
        total_before += os.path.getsize(p)
        optimize(p)
        total_after += os.path.getsize(p)

    print(f"\n压缩前: {total_before/1024/1024:.1f} MB")
    print(f"压缩后: {total_after/1024/1024:.1f} MB")
    print(f"减少了: {(1 - total_after/total_before)*100:.1f}%")

if __name__ == '__main__':
    main()