import os

root = "content"
old_str = "Fantasy Factory"
new_str = "FantasyFactory"

cnt = 0
for dirpath, _, files in os.walk(root):
    for fn in files:
        if not fn.endswith(".md"):
            continue
        fpath = os.path.join(dirpath, fn)
        with open(fpath, "r", encoding="utf-8") as f:
            text = f.read()
        if old_str in text:
            text = text.replace(old_str, new_str)
            with open(fpath, "w", encoding="utf-8") as fw:
                fw.write(text)
            print(f"修改 {fpath}")
            cnt += 1
print(f"\n总共修改md数量：{cnt}")
