import os
import gzip
import shutil

# 目标文件夹目录
TARGET_DIR = "VideoResults"
OLD_DOMAIN = "tutututu.cyou"
NEW_DOMAIN = "cktutu.lifestyle"

def process_m3u8_files():
    if not os.path.exists(TARGET_DIR):
        print(f"[WARN] 目录 '{TARGET_DIR}' 不存在，跳过处理。")
        return

    replaced_count = 0
    compressed_count = 0
    file_count = 0

    # 递归遍历 VideoResults 目录下的所有文件
    for root, _, files in os.walk(TARGET_DIR):
        for file in files:
            if file.endswith('.m3u8'):
                file_path = os.path.join(root, file)
                file_count += 1
                
                try:
                    # 1. 读取并替换 m3u8 内容
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    is_modified = False
                    if OLD_DOMAIN in content:
                        content = content.replace(OLD_DOMAIN, NEW_DOMAIN)
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        replaced_count += 1
                        is_modified = True
                        print(f"[SUCCESS] 替换域名: {file_path}")

                    # 2. 重新生成 .gz 压缩包 (如 filename.m3u8 -> filename.m3u8.gz)
                    # 如果原压缩包是 filename.gz，将下面的 .m3u8.gz 改为 .gz 即可
                    gz_path = f"{file_path}.gz"
                    
                    # 使用 gzip 压缩更新后的内容
                    with open(file_path, 'rb') as f_in:
                        with gzip.open(gz_path, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    
                    compressed_count += 1
                    if is_modified:
                        print(f"[GZ] 已更新压缩包: {gz_path}")

                except Exception as e:
                    print(f"[ERROR] 处理文件失败 {file_path}: {e}")

    print(f"\n==========================================")
    print(f"处理完成！共扫描 {file_count} 个 .m3u8 文件:")
    print(f" - 修改域名文件数: {replaced_count}")
    print(f" - 重新生成 gz 包数: {compressed_count}")
    print(f"==========================================")

if __name__ == "__main__":
    process_m3u8_files()
