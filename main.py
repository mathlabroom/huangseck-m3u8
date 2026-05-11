import os, re, json, time, requests, urllib.parse
import subprocess
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- 1. Git 自动同步函数 ---
def git_push_backup(count):
    """阶段性强制备份：先落袋为安，再处理冲突"""
    try:
        # 1. 配置基础信息
        subprocess.run(["git", "config", "--local", "user.email", "action@github.com"], check=True)
        subprocess.run(["git", "config", "--local", "user.name", "GitHub Action"], check=True)
        
        # 2. 先把本地抓到的 1000 条锁死（Add & Commit）
        # 这样工作区就“干净”了，可以安全执行 pull --rebase
        subprocess.run(["git", "add", "."], check=True)
        msg = f"自动备份: 累计新增 {count} 条资源"
        # check=False 是因为如果没有变动 commit 会返回 1，我们不希望它报错
        subprocess.run(["git", "commit", "-m", msg], check=False)
        
        # 3. 这时候再拉取远程更新，解决多人（或多次 Actions）同时运行的冲突
        print("🔄 正在同步远程仓库状态...")
        subprocess.run(["git", "pull", "origin", "main", "--rebase"], check=True)
        
        # 4. 最后推送到云端
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print(f"🚀 [同步成功] 已成功分批推送 {count} 条数据至仓库")
        
    except Exception as e:
        print(f"⚠️ [同步跳过] 遇到冲突或网络问题: {e}")
        # 万一 rebase 失败了，尝试强行退出 rebase 状态，防止脚本卡死
        subprocess.run(["git", "rebase", "--abort"], check=False)
        
# --- 2. 配置加载 ---
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

# --- 3. 网络会话设置 ---
def get_stable_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Referer": BASE_URL
    })
    return session

# --- 4. 存盘逻辑 (精准去重版) ---
def save_and_update(path, new_lines, db_list, db_path):
    items_dict = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            blocks = re.findall(r'(#EXTINF:.*?)(?=#EXTINF:|$)', content, re.S)
            for block in blocks:
                clean_block = block.strip()
                if clean_block:
                    title_line = clean_block.split('\n')[0].strip()
                    items_dict[title_line] = clean_block

    for item in new_lines:
        item = item.strip()
        if item:
            title_line = item.split('\n')[0].strip()
            items_dict[title_line] = item

    sorted_keys = sorted(items_dict.keys())
    with open(path, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for k in sorted_keys:
            f.write(items_dict[k] + "\n")
    
    with open(db_path, 'w', encoding='utf-8') as f:
        json.dump(db_list, f, ensure_ascii=False)

# --- 5. 核心收割逻辑 ---
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
    all_new_entries = []
    stop_days = config.get("STOP_DAYS_AGO", 1)
    # 计算 N 天前的日期字符串 (格式 MM-DD)
    stop_date_threshold = (datetime.now() - timedelta(days=stop_days)).strftime("%m-%d")

    for p in range(1, 10000):
        url = f"{BASE_URL}/t/{cat_id}-{p}.html"
        try:
            res = session.get(url, timeout=15)
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            li_list = soup.select('.wall-list li')
            if not li_list: break

            # 广告页检测
            has_real_video = any('/p/' in a.get('href', '') for a in soup.select('.wall-list a'))
            if not has_real_video:
                print(f"🏁 第 {p} 页全是广告，判定为分类终点。")
                break
            
            print(f"🌐 正在扫描第 {p} 页...")
            found_old_content = False
            
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
                date_val = "01-01" # 默认值
                if sub_tag:
                    date_match = re.search(r'(\d{2}-\d{2})', sub_tag.get_text())
                    if date_match: date_val = date_match.group(1)
                
                v_id_match = re.search(r'/p/(\d+)', href)
                if not v_id_match: continue
                
                v_id = v_id_match.group(1)
                if p > 3 and date_val < stop_date_threshold:
                    print(f"⏱️ 发现旧资源 ({date_val})，已达到增量截止日期 ({stop_date_threshold})。")
                    found_old_content = True
                    break
                
                if v_id in db_set: continue

                try:
                    full_link = urllib.parse.urljoin(BASE_URL, href) + "?play=1"
                    p_res = session.get(full_link, timeout=10)
                    m3u8_find = re.search(r'https?[:\\]+[^"\']+\.m3u8[^"\']*', p_res.text, re.I)
                    if m3u8_find:
                        m3u8 = m3u8_find.group(0).replace('\\', '')
                        if "%3A" in m3u8: m3u8 = urllib.parse.unquote(m3u8)
                        
                        # --- 修改这里的拼接逻辑 ---
                        # 逻辑：如果存在封面图，则注入 tvg-logo 属性；否则保持原样
                        if cover_url:
                            item_entry = f'#EXTINF:-1 tvg-logo="{cover_url}",{title} [{date_val}]\n'
                        else:
                            item_entry = f'#EXTINF:-1,{title} [{date_val}]\n'
        
                        item_entry += f"{m3u8}\n"
                        # --- 修改结束 ---
                        
                        all_new_entries.append(item_entry)
                        db.append(v_id)
                        db_set.add(v_id)
                        stats["new"] += 1
                        print(f"  ✅ [捕获] {date_val} | {title[:15]}...")
                        
                        # 每 1000 条强制备份
                        if stats["new"] > 0 and stats["new"] % 1000 == 0:
                            print(f"📦 达到 1000 条阈值，开启分批同步...")
                            save_and_update(save_path, all_new_entries, db, db_file)
                            git_push_backup(stats["new"])
                            all_new_entries = [] # 关键：存完清空内存，防止重复
                except: continue
            if found_old_content:
                break # 彻底退出 range(1, 10000) 循环，切换到下一个分类
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  🚨 页面出错: {e}")
            break

    # 循环结束后的最后一次物理存盘
    if all_new_entries:
        print(f"💾 正在写入该分类剩余的 {len(all_new_entries)} 条资源...")
        save_and_update(save_path, all_new_entries, db, db_file)
    
    return stats

# --- 6. E2 Bouquet 转换 ---
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
        
        items = content.split("#EXTINF")
        output_lines = [f"#NAME {cat_name}"]
        sid = 1
        for item in items:
            if not item.strip(): continue
            lines = item.strip().split('\n')
            title = lines[0].split(',')[-1].strip()
            url = lines[-1].strip()
            if url.startswith('http'):
                h_sid = hex(sid)[2:].upper()
                output_lines.append(f"#SERVICE 4097:0:1:{h_sid}:0:0:{hex_id}:0:0:0:{url.replace(':', '%3a')}:{title}")
                output_lines.append(f"#DESCRIPTION {title}")
                sid += 1
        
        with open(os.path.join(OUTPUT_DIR, f"subbouquet.{cat_name}.tv"), 'w', encoding='utf-8') as f:
            f.write("\n".join(output_lines) + "\n")

# --- 7. 入口 ---
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
