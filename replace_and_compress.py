import os
import re
import gzip
import shutil

TARGET_DIR = "VideoResults"

# 专门用于识别封面图片的正则，通过图片后缀锁定域名
COVER_URL_PATTERN = r'https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/[^\s"\'<>]+\.(?:jpg|jpeg|png|webp|gif)'

def extract_latest_cover_domain(file_path):
    """从指定的 m3u8 文件中，通过图片后缀提取最新的【封面域名】"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            match = re.search(COVER_URL_PATTERN, content, re.IGNORECASE)
            if match:
                return match.group(1)  # 返回第 1 个捕获组，即域名部分
    except Exception as e:
        print(f"[ERROR] 读取文件提取封面域名失败 {file_path}: {e}")
    return None

def process_m3u8_files():
    if not os.path.exists(TARGET_DIR):
        print(f"[WARN] 目录 '{TARGET_DIR}' 不存在，跳过处理。")
        return

    # 1. 搜集所有 .m3u8 文件
    all_m3u8_files = []
    for root, _, files in os.walk(TARGET_DIR):
        for file in files:
            if file.endswith('.m3u8'):
                all_m3u8_files.append(os.path.join(root, file))

    if not all_m3u8_files:
        print("[WARN] 未找到任何 .m3u8 文件。")
        return

    # 2. 找到最新修改（最新爬取/更新）的文件，精确定位最新的【封面有效域名】
    all_m3u8_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    latest_file = all_m3u8_files[0]
    new_cover_domain = extract_latest_cover_domain(latest_file)

    if not new_cover_domain:
        print(f"[ERROR] 无法从最新文件 ({latest_file}) 中自动识别封面域名，停止处理。")
        return

    print(f"[INFO] 识别到的最新有效【封面域名】为: {new_cover_domain}")

    replaced_count = 0
    compressed_count = 0
    file_count = len(all_m3u8_files)

    # 3. 遍历所有文件，只替换封面对应的旧域名
    for file_path in all_m3u8_files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # 提取文件中所有图片链接里的域名
            cover_domains_in_file = set(re.findall(COVER_URL_PATTERN, content, re.IGNORECASE))
            
            is_modified = False
            for old_dom in cover_domains_in_file:
                # 仅当旧图片域名与最新图片域名不同时才替换，不影响视频切片域名
                if old_dom != new_cover_domain:
                    content = content.replace(old_dom, new_cover_domain)
                    is_modified = True

            # 如果内容被修改，写入文件
            if is_modified:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                replaced_count += 1
                print(f"[SUCCESS] 封面域名同步为 -> {new_cover_domain}: {file_path}")

            # 4. 重新生成 .gz 压缩包
            gz_path = f"{file_path}.gz"
            with open(file_path, 'rb') as f_in:
                with gzip.open(gz_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            compressed_count += 1

        except Exception as e:
            print(f"[ERROR] 处理文件失败 {file_path}: {e}")

    print(f"\n==========================================")
    print(f"处理完成！共扫描 {file_count} 个 .m3u8 文件:")
    print(f" - 统一封面域名: {new_cover_domain}")
    print(f" - 修改封面域名文件数: {replaced_count}")
    print(f" - 重新生成 gz 包数: {compressed_count}")
    print(f"==========================================")

if __name__ == "__main__":
    process_m3u8_files()
