import os, re, json, time, requests, urllib.parse
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def load_config():
    default_config = {
        "BASE_URL": "http://ck0d.cc",
        "CATS": [
            {"id": "2", "name": "国产系列"},
            {"id": "21", "name": "欧美高清"},
            {"id": "26", "name": "骑兵破解"},
            {"id": "10", "name": "日本无码"},
            {"id": "7", "name": "日本有码"},
            {"id": "8", "name": "无码中文字幕"},
            {"id": "9", "name": "有码中文字幕"},
            {"id": "4", "name": "动漫"}
        ],
        "STOP_DAYS_AGO": 1
    }
    config_path = "config.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            print("⚠️ config.json 格式错误，使用默认配置")
    return default_config

config = load_config()
BASE_URL = config["BASE_URL"]
CATS = config["CATS"]
# 自动计算刹车日期
target_date = datetime.now() - timedelta(days=config.get("STOP_DAYS_AGO", 1))
STOP_MONTH = target_date.month
STOP_DAY = target_date.day

def get_stable_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Referer": BASE_URL
    })
    return session

def save_and_update(path, new_lines, db_list, db_path):
    """
    终极修复版：确保 #EXTIMG 写入，并彻底解决格式错乱问题
    """
    items_dict = {}

    # 1. 尝试读取现有文件并解析（重点：通过正则精准切分块）
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            # 找到所有的频道块：从 #EXTINF 开始，直到下一个 #EXTINF 或文件末尾
            # 正则解释：匹配 #EXTINF 及其后的所有内容，直到遇到下一个 #EXTINF
            blocks = re.findall(r'(#EXTINF:.*?)(?=#EXTINF:|$)', content, re.S)
            for block in blocks:
                clean_block = block.strip()
                if clean_block:
                    # 用第一行（标题行）作为 Key，确保唯一性
                    title_line = clean_block.split('\n')[0].strip()
                    items_dict[title_line] = clean_block

    # 2. 将本次新抓取的数据合并进去
    for item in new_lines:
        item = item.strip()
        if item:
            title_line = item.split('\n')[0].strip()
            # 新抓取的覆盖旧的，保证信息（包括封面）是最新的
            items_dict[title_line] = item

    # 3. 排序并重新写入（干净整洁的格式）
    sorted_keys = sorted(items_dict.keys())
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n") # 只有开头这一行
        for k in sorted_keys:
            f.write(items_dict[k] + "\n")
    
    # 4. 同步更新 JSON
    with open(db_path, 'w', encoding='utf-8') as f:
        json.dump(db_list, f, ensure_ascii=False)
        
def crawl_category(cat, session):
    cat_id, cat_name = cat["id"], cat["name"]
    db_file = f"./{cat_name}.json"
    save_dir = f"./VideoResults/{cat_name}"
    save_path = f"{save_dir}/{cat_name}.m3u8"
    os.makedirs(save_dir, exist_ok=True)
    
    db = json.load(open(db_file, 'r', encoding='utf-8')) if os.path.exists(db_file) else []
    db_set = set(str(i) for i in db)
    
    print(f"\n📂 启动分类: 【{cat_name}】 | 库内: {len(db_set)}")

    stats = {"new": 0, "existed": len(db_set)}
    all_new_entries = []  # <--- 新增：用来收集该分类下所有页面的新资源

    for p in range(1, 10000):
        url = f"{BASE_URL}/t/{cat_id}-{p}.html"
        try:
            res = session.get(url, timeout=15)
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 1. 依然先抓 li 列表
            li_list = soup.select('.wall-list li')
            if not li_list: break

            # 2. 【关键新增】检查这一页有没有包含有效视频路径 /p/ 的链接
            # 如果整页一个真视频都没有（全是广告），直接跳出，不再往后扫
            has_real_video = any('/p/' in a.get('href', '') for a in soup.select('.wall-list a'))
            
            if not has_real_video:
                print(f"🏁 第 {p} 页全是广告，判定为分类终点。")
                break
            
            print(f"🌐 正在扫描第 {p} 页...")
            
            # ... 后续解析逻辑 ...
            
            li_list = soup.select('.wall-list li')
            if not li_list: 
                print(f"🏁 第 {p} 页无内容，【{cat_name}】收割完毕。")
                break

            for li in li_list:
                cover_tag = li.select_one('a.card-cover')
                cover_url = ""
                if cover_tag:
                    cover_url = cover_tag.get('data-original') or ""
                    if cover_url.startswith('//'): cover_url = 'https:' + cover_url
                    elif cover_url.startswith('/') and not cover_url.startswith('//'):
                        cover_url = urllib.parse.urljoin(BASE_URL, cover_url)

                title_tag = li.select_one('.card-info .title a')
                if not title_tag: continue
                title = title_tag.get_text(strip=True)
                href = title_tag.get('href', '')

                if not href.startswith('/p/'): continue

                sub_tag = li.select_one('p.sub')
                if not sub_tag: continue
                date_match = re.search(r'(\d{2}-\d{2})', sub_tag.get_text())
                if not date_match: continue
                date_val = date_match.group(1)
                
                v_id_match = re.search(r'/p/(\d+)', href)
                if not v_id_match: continue
                v_id = v_id_match.group(1)

                # --- 全量收割建议关闭 is_old 判断 ---
                if v_id in db_set:
                    continue

                try:
                    full_link = urllib.parse.urljoin(BASE_URL, href) + "?play=1"
                    p_res = session.get(full_link, timeout=10)
                    m3u8_find = re.search(r'https?[:\\]+[^"\']+\.m3u8[^"\']*', p_res.text, re.I)
                    if m3u8_find:
                        m3u8 = m3u8_find.group(0).replace('\\', '')
                        if "%3A" in m3u8: m3u8 = urllib.parse.unquote(m3u8)
                        
                        item_entry = f"#EXTINF:-1,{title} [{date_val}]\n"
                        if cover_url: item_entry += f"#EXTIMG:{cover_url}\n"
                        item_entry += f"{m3u8}\n"
                        
                        all_new_entries.append(item_entry) # <--- 存入大列表
                        db.append(v_id)
                        db_set.add(v_id)
                        stats["new"] += 1
                        print(f"  ✅ [捕获] {date_val} | {title[:15]}...")
                except: continue

            # --- 删掉了这里的每页存盘逻辑 ---
            time.sleep(0.5) # 全量收割可以稍微缩短一点延迟，建议 0.5s-1s
            
        except Exception as e:
            print(f"  🚨 页面出错: {e}")
            break

    # --- 关键修改：在这里一次性存盘 ---
    if all_new_entries:
        print(f"💾 正在将新增的 {len(all_new_entries)} 条资源写入磁盘...")
        save_and_update(save_path, all_new_entries, db, db_file)
    
    return stats

def convert_to_e2_bouquets():
    BASE_DIR = './VideoResults'
    OUTPUT_DIR = './E2_Bouquets'
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    CATEGORY_MAP = {
        "国产系列": "65", "骑兵破解": "66", "无码中文字幕": "67", "有码中文字幕": "68",
        "日本有码": "69", "日本无码": "6A", "欧美高清": "6B", "动漫": "6C"
    }

    for cat_name, hex_id in CATEGORY_MAP.items():
        m3u8_path = os.path.join(BASE_DIR, cat_name, f"{cat_name}.m3u8")
        if not os.path.exists(m3u8_path): continue
        with open(m3u8_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 兼容带海报的 m3u8 解析逻辑
        items = content.split("#EXTINF")
        output_lines = [f"#NAME {cat_name}"]
        sid = 1
        for item in items:
            if not item.strip(): continue
            lines = item.strip().split('\n')
            title = lines[0].split(',')[-1].strip()
            # 获取最后一行（通常是 URL）
            url = lines[-1].strip()
            if url.startswith('http'):
                h_sid = hex(sid)[2:].upper()
                output_lines.append(f"#SERVICE 4097:0:1:{h_sid}:0:0:{hex_id}:0:0:0:{url.replace(':', '%3a')}:{title}")
                output_lines.append(f"#DESCRIPTION {title}")
                sid += 1
        
        with open(os.path.join(OUTPUT_DIR, f"subbouquet.{cat_name}.tv"), 'w', encoding='utf-8') as f:
            f.write("\n".join(output_lines) + "\n")

if __name__ == "__main__":
    start_time = time.time()
    session = get_stable_session()
    report = []
    
    try:
        for cat in CATS:
            try:
                res = crawl_category(cat, session)
                report.append({"name": cat["name"], **res})
            except KeyboardInterrupt:
                print(f"\n⚠️ 手动跳过 {cat['name']}")
                report.append({"name": cat["name"], "new": 0, "existed": "N/A"})
                continue
    finally:
        print(f"\n{'='*30}\n收割总结\n{'='*30}")
        for r in report:
            print(f"{r['name']}: 新增 {r['new']}")
        convert_to_e2_bouquets()
        print(f"\n✅ 完成! 耗时: {time.time()-start_time:.1f}s")
