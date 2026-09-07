import os
import re
import gzip
import shutil
import urllib3
import requests
from collections import Counter
from bs4 import BeautifulSoup

# 禁用 requests 在 verify=False 时弹出的 InsecureRequestWarning 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TARGET_DIR = "VideoResults"
# 精准匹配带图片后缀的完整 URL 正则
COVER_URL_PATTERN = r'https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/[^\s"\'<>]+\.(?:jpg|jpeg|png|webp|gif)'

def get_valid_base_url():
    """智能探路者：直接从发布页追踪获取最新真实主站域名"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    anchor_host = "http://hsck.us" 
    
    print("⚠️ 启动智能追踪器，直接从发布页搜寻最新入口...")
    try:
        print(f"📡 正在请求永久发布页: {anchor_host}")
        req_res = requests.get(anchor_host, headers=headers, timeout=10, verify=False)
        html = req_res.text
        soup = BeautifulSoup(html, "lxml" if "lxml" in html else "html.parser")

        # 1. 尝试匹配动态跳转接口
        if "strU=" in html and soup.find(id="hao123"):
            match = re.search(r'strU="(https?://[a-zA-Z0-9:/.]+\?u=?)"', html)
            if match:
                redirect_url = f"{match.group(1)}{anchor_host}/&p=/"
                print(f"🔗 捕获到动态跳转接口: {redirect_url}，正在追踪最终归宿...")
                track_res = requests.head(redirect_url, headers=headers, timeout=8, verify=False, allow_redirects=False)
                location = track_res.headers.get("Location")
                if location:
                    loc_match = re.match(r"(https?://[a-zA-Z0-9][-a-zA-Z0-9]{0,62}(\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+)", location)
                    if loc_match:
                        discovered_url = loc_match.group(1)
                        print(f"🚀 [追踪成功] 通过重定向接口捕获到最新官网: {discovered_url}")
                        return discovered_url

        # 2. 如果发布页自身就已经展示了官网内容
        if len(html) > 20000 and soup.find(class_="stui-warp-content"):
            print(f"🚀 [寻路成功] 发布页本身已展现官网特征，直接采用: {anchor_host}")
            return anchor_host
    except Exception as tracker_err:
        print(f"❌ 智能寻路系统发生故障: {tracker_err}")

    print("⚠️ 寻路系统未能探明新域名，后备退回发布页根域名。")
    return anchor_host

def fetch_latest_cover_domain(base_url):
    """访问真实官网，抓取所有图片域名，并通过【出现频率最高】原则筛选真正的主图床"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        print(f"🔍 正在请求真实官网 {base_url} 统计图片域名频次...")
        res = requests.get(base_url, headers=headers, timeout=10, verify=False)
        res.encoding = 'utf-8'
        
        # 抓取页面中出现的所有图片 URL 对应的域名列表（包含重复项）
        all_domains = re.findall(COVER_URL_PATTERN, res.text, re.IGNORECASE)
        
        if not all_domains:
            print("❌ 未在官网 HTML 中匹配到任何符合条件的图片域名。")
            return None

        # 计数统计
        domain_counts = Counter(all_domains)
        print("📊 页面图片域名分布频次统计:")
        for dom, count in domain_counts.most_common():
            print(f"  - {dom}: 出现 {count} 次")

        # 选出频次最高（most_common）的那个域名
        most_common_domain, highest_count = domain_counts.most_common(1)[0]
        print(f"🎯 [筛选成功] 确定出现次数最多 ({highest_count}次) 的真实图床域名: {most_common_domain}")
        return most_common_domain

    except Exception as e:
        print(f"❌ 访问真实官网提取封面失败: {e}")
    return None

def process_m3u8_files():
    # 1. 追踪拿到真实官网
    real_base_url = get_valid_base_url()
    
    # 2. 从官网按频次抓取真正的图片域名
    new_cover_domain = fetch_latest_cover_domain(real_base_url)
    if not new_cover_domain:
        print("⛔ 无法定位最频繁的真实封面域名，任务终止。")
        return

    if not os.path.exists(TARGET_DIR):
        print(f"⚠️ 目录 '{TARGET_DIR}' 不存在，跳过处理。")
        return

    # 3. 搜集所有 .m3u8 文件
    all_m3u8_files = []
    for root, _, files in os.walk(TARGET_DIR):
        for file in files:
            if file.endswith('.m3u8'):
                all_m3u8_files.append(os.path.join(root, file))

    if not all_m3u8_files:
        print("⚠️ 未找到任何 .m3u8 文件。")
        return

    replaced_count = 0
    compressed_count = 0
    file_count = len(all_m3u8_files)

    # 4. 全量同步替换旧封面域名并重新压包
    for file_path in all_m3u8_files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # 提取当前文件包含的所有图片域名
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
                print(f"✅ 封面域名更新为 -> {new_cover_domain}: {file_path}")

            # 重新打包生成 .gz 压缩包
            gz_path = f"{file_path}.gz"
            with open(file_path, 'rb') as f_in:
                with gzip.open(gz_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            compressed_count += 1

        except Exception as e:
            print(f"❌ 处理文件失败 {file_path}: {e}")

    print(f"\n==========================================")
    print(f"🎉 自动化处理完成！共扫描 {file_count} 个 .m3u8 文件:")
    print(f" - 追踪到的官网地址: {real_base_url}")
    print(f" - 频次最高（判定为真实）的封面域名: {new_cover_domain}")
    print(f" - 修改文件数: {replaced_count}")
    print(f" - 重新生成 gz 包数: {compressed_count}")
    print(f"==========================================")

if __name__ == "__main__":
    process_m3u8_files()
