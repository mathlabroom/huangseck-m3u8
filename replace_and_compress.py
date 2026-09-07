import os
import re
import gzip
import shutil
import requests

TARGET_DIR = "VideoResults"
ENTRY_URL = "https://hsck.us"  # 中转站入口

# 提取图片 URL 中域名的精准正则（带图片后缀约束）
COVER_URL_PATTERN = r'https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/[^\s"\'<>]+\.(?:jpg|jpeg|png|webp|gif)'

def get_real_cover_domain():
    """解析 hsck.us 的 JS 跳转，请求真实目标网页并提取最新封面域名"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        print(f"[1/3] 正在访问中转站: {ENTRY_URL} ...")
        res_entry = requests.get(ENTRY_URL, headers=headers, timeout=10)
        res_entry.encoding = 'utf-8'
        
        # 1. 用正则匹配出 JS 中的真实跳转地址 strU (如 "https://5858.space:8899/?u=...")
        redirect_match = re.search(r'var\s+strU\s*=\s*["\']([^"\']+)["\']', res_entry.text)
        if not redirect_match:
            print("[ERROR] 未能从中转站源码中解析出跳转 URL (strU)。")
            return None
        
        real_url = redirect_match.group(1)
        # 容错处理：如果 strU 里面拼了 window.location，剔除结尾未定义的 JS 变量拼接
        real_url = real_url.split('?')[0]  # 拿到基础域名/页面地址，如 https://5858.space:8899
        print(f"[2/3] 解析出真实目标地址: {real_url}")

        # 2. 请求真实的网页内容
        res_target = requests.get(real_url, headers=headers, timeout=12)
        res_target.encoding = 'utf-8'
        
        if res_target.status_code == 200:
            # 3. 从真实网页源码中提取最新的封面域名
            cover_match = re.search(COVER_URL_PATTERN, res_target.text, re.IGNORECASE)
            if cover_match:
                latest_domain = cover_match.group(1)
                print(f"[3/3] 成功从真实目标页抓取到最新【封面域名】: {latest_domain}")
                return latest_domain
            else:
                print("[ERROR] 已进入真实网页，但未在源码中匹配到图片域名。")
        else:
            print(f"[ERROR] 请求真实目标页失败，状态码: {res_target.status_code}")

    except Exception as e:
        print(f"[ERROR] 执行跳转抓取过程发生异常: {e}")
        
    return None

def process_m3u8_files():
    # 1. 自动解解析跳转并获取最新封面域名
    new_cover_domain = get_real_cover_domain()
    
    if not new_cover_domain:
        print("[ABORT] 无法获取最新封面域名，任务终止。")
        return

    if not os.path.exists(TARGET_DIR):
        print(f"[WARN] 目录 '{TARGET_DIR}' 不存在，跳过处理。")
        return

    # 2. 搜集 VideoResults 目录下的所有 .m3u8 文件
    all_m3u8_files = []
    for root, _, files in os.walk(TARGET_DIR):
        for file in files:
            if file.endswith('.m3u8'):
                all_m3u8_files.append(os.path.join(root, file))

    if not all_m3u8_files:
        print("[WARN] 未找到任何 .m3u8 文件。")
        return

    replaced_count = 0
    compressed_count = 0
    file_count = len(all_m3u8_files)

    # 3. 遍历本地文件替换域名并重新压包
    for file_path in all_m3u8_files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # 提取文件内的所有图片域名
            cover_domains_in_file = set(re.findall(COVER_URL_PATTERN, content, re.IGNORECASE))
            
            is_modified = False
            for old_dom in cover_domains_in_file:
                if old_dom != new_cover_domain:
                    content = content.replace(old_dom, new_cover_domain)
                    is_modified = True

            if is_modified:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                replaced_count += 1
                print(f"[SUCCESS] 封面域名更新为 -> {new_cover_domain}: {file_path}")

            # 4. 重新打包 .gz 文件
            gz_path = f"{file_path}.gz"
            with open(file_path, 'rb') as f_in:
                with gzip.open(gz_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            compressed_count += 1

        except Exception as e:
            print(f"[ERROR] 处理文件失败 {file_path}: {e}")

    print(f"\n==========================================")
    print(f"自动化处理完成！共扫描 {file_count} 个 .m3u8 文件:")
    print(f" - 实时抓取的最新封面域名: {new_cover_domain}")
    print(f" - 修改文件数: {replaced_count}")
    print(f" - 重新生成 gz 包数: {compressed_count}")
    print(f"==========================================")

if __name__ == "__main__":
    process_m3u8_files()
