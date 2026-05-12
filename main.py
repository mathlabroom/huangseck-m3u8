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
        url = f"{BASE_URL}/vodtype/{cat_id}-{p}.html"
        try:
            res = session.get(url, timeout=15)
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 1. 查找列表容器 (针对 Stui 模板优化)
            li_list = soup.select('.stui-vodlist li')
            if not li_list: break

            # 2. 广告过滤逻辑
            # 现在的链接是 /vodplay/，所以我们检查是否存在正常的播放地址
            has_real_video = any('/vodplay/' in a.get('href', '') for a in soup.select('.stui-vodlist a'))
            if not has_real_video:
                print(f"🏁 第 {p} 页全是广告/非视频内容。")
                break
            
            print(f"🌐 正在扫描第 {p} 页...")
            found_old_content = False
            
            # --- 1. 自动定位列表区域 ---
            # 不再死磕具体的 class，找所有包含 <a> 标签的 <li> 
            # 这种排比结构通常就是视频列表
            items = soup.find_all('li')
            
            for li in items:
                # --- 2. 特征嗅探：寻找“真视频”链接 ---
                # 特征 1：a 标签必须有 title 属性（真视频为了 SEO 必带）
                # 特征 2：没有 target="blank"（真视频通常站内跳转，广告必跳出）
                title_tag = li.find('a', attrs={"title": True})
                
                # 如果这个 a 标签带了 target="blank" 或者根本没有 title，大概率是广告
                if not title_tag or title_tag.get('target') == 'blank':
                    continue
                
                title = title_tag.get('title').strip()
                href = title_tag.get('href', '')
                
                # 排除一些常见的系统链接
                if any(x in href for x in ['javascript', 'about:', 'index.php']):
                    continue

                # --- 3. 自动识别日期 ---
                # 不管日期在哪个 <span> 或 <p> 里，直接在当前 li 容器里搜数字格式
                date_val = "01-01"
                li_text = li.get_text(strip=True)
                # 匹配 MM-DD 格式
                date_match = re.search(r'(\d{2}-\d{2})', li_text)
                if date_match:
                    date_val = date_match.group(1)

                # --- 4. 截止判定 ---
                # 依然保留翻页保护逻辑
                if p > 3 and date_val != "01-01":
                    if date_val < stop_date_threshold:
                        print(f"⏱️ 探测到旧日期 {date_val}，收割完成。")
                        found_old_content = True
                        break

                # --- 5. 去重判定 ---
                # 既然路径会变，我们直接拿 href 里的数字 ID 作为唯一识别码
                v_id_match = re.search(r'(\d+)', href)
                if not v_id_match: continue
                v_id = v_id_match.group(1)

                if v_id in db_set:
                    continue

                # --- 6. 捕获 M3U8 (带 play 参数) ---
                try:
                    full_link = urllib.parse.urljoin(BASE_URL, href)
                    # 自动处理带不带问号的参数拼接
                    play_link = full_link + ("&" if "?" in full_link else "?") + "play=1"
                    
                    p_res = session.get(play_link, timeout=12)
                    # 匹配 JS 变量里的 m3u8，并处理转义斜杠
                    m3u8_match = re.search(r'https?[:\\\/]+[^"\']+\.m3u8[^"\']*', p_res.text, re.I)

                    if m3u8_match:
                        m3u8 = m3u8_match.group(0).replace('\\/', '/').replace('\\', '')
                        if "%" in m3u8:
                            m3u8 = urllib.parse.unquote(m3u8)

                        # 获取封面 (找第一个带有图片路径的标签)
                        img_tag = li.find('img') or li.find(attrs={"data-original": True})
                        cover_url = ""
                        if img_tag:
                            cover_url = img_tag.get('data-original') or img_tag.get('src') or ""

                        # 写入逻辑保持不变
                        item_entry = f'#EXTINF:-1 tvg-logo="{cover_url}",{title} [{date_val}]\n{m3u8}\n'
                        all_new_entries.append(item_entry)
                        db.append(v_id)
                        db_set.add(v_id)
                        stats["new"] += 1
                        print(f"  ✅ [嗅探成功] {date_val} | {title[:15]}...")
                        
                        # 5. 每 1000 条自动备份到 Git
                        if stats["new"] > 0 and stats["new"] % 1000 == 0:
                            print(f"📦 累计 1000 条，正在同步仓库...")
                            save_and_update(save_path, all_new_entries, db, db_file)
                            git_push_backup(stats["new"])
                            all_new_entries = [] 
                except Exception as e:
                    continue

            # li 循环结束，判断是否需要因为日期旧而切换分类
            if found_old_content: break
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
