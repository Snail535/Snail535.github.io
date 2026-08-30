import os

def replace_hash_in_dir(root_dir):
    # topdown=False：从最深的子文件夹开始往上改，避免路径错乱
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
        for name in dirnames:
            if '#' in name:
                old_path = os.path.join(dirpath, name)
                new_name = name.replace("#", "_")
                new_path = os.path.join(dirpath, new_name)
                os.rename(old_path, new_path)
                print(f"【已重命名】\n旧：{old_path}\n新：{new_path}\n")

if __name__ == "__main__":
    target = r"static/thumbs/portraits/ 日本工作室 / Escape/"
    print(f"开始扫描目录：{target}")
    replace_hash_in_dir(target)
    print("全部处理完成！")
