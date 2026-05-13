import os, re, json, time, requests, urllib.parse
import subprocess
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

# 禁用不安全请求警告（针对某些 .xyz 站点的证书问题）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. Git 自动同步函数 ---
def git_push_backup(count):
    """阶段性强制备份：先落袋为安，再处理冲突"""
    try:
        subprocess.run(["git", "config", "--local", "user.email", "action@github.com"], check=True)
        subprocess.run(["git", "config", "--local", "user.name", "GitHub Action"], check=True)
        
        # 将 config.json 也加入暂存区，确保自动嗅探到的新域名能被上传
        subprocess.run(["git", "add", "."], check=True)
        msg = f"自动备份: 累计新增 {count} 条资源并同步配置"
        subprocess.run(["git", "commit", "-m", msg], check=False)
        
        print("🔄 正在同步远程仓库状态...")
        subprocess.run(["git", "pull", "origin", "main", "--rebase"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print(f"🚀 [同步成功] 已成功分批推送数据至仓库")
        
    except Exception as e:
        print(f"⚠️ [同步跳过] 遇到冲突或网络问题: {e}")
        subprocess.run(["git", "rebase", "--abort"], check=False)

# --- 2. 域名双保险嗅探逻辑 (新增) ---
def get_valid_base_url(current_url):
    """
    双保险：验证当前域名，若失效则基于数字规律自动探测新入口
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."}
    
    # 策略 1: 验证现有域名
    print(f"🔍 正在验证预设域名: {current_url}")
    try:
        # 尝试访问分类页验证连通性
        res = requests.get(f"{current_url}/vodtype/2-1.html", headers=headers, timeout=5, verify=False)
        if res.status_code == 200 and "stui-vodlist" in res.text:
            print("✅ 域名有效，继续执行。")
            return current_url
    except:
        pass

    print("⚠️ 预设域名失效，启动自动寻路...")

    # 策略 2: 自动嗅探 (从当前数字开始往后探测 50 个)
    match = re.search(r'(\d+)', current_url)
    start_num = int(match.group(1)) if match else 456170
    
    for i in range(start_num, start_num + 50):
        test_url = f"http://{i}.xyz"
        try:
            test_res = requests.get(f"{test_url}/vodtype/2-1.html", headers=headers, timeout=3, verify=False)
            if test_res.status_code == 200 and "stui-vodlist" in test_res.text:
                print(f"🚀 发现新入口: {test_url}")
                return test_url
        except:
            continue
    
    return current_url

def get_route_path(base_url, session):
    """
    直接从首页源码解析出当前的分类路由格式
    """
    try:
        # 1. 访问首页
        res = session.get(base_url, timeout=10, verify=False)
        res.encoding = 'utf-8'
        
        # 2. 正则匹配：寻找包含 .html 的链接前缀
        # 这里的正则专门抓取类似 /vodtype/ 或 /p/ 这种出现在数字前面的字符
        match = re.search(r'href="(/[a-z0-9]+/)\d+\.html"', res.text)
        
        if match:
            path = match.group(1)
            print(f"🎯 自动识别路由成功: {path}")
            return path
        else:
            print("⚠️ 首页未发现标准路由，尝试使用默认值 /vodtype/")
            return "/vodtype/"
    except Exception as e:
        print(f"❌ 解析首页失败: {e}")
        return "/vodtype/"
        
# --- 3. 配置加载与更新 ---
def load_and_fix_config():
    config_path = "config.json"
    default_config = {
        "BASE_URL": "http://456172.xyz",
        "CATS": [{"id": "2", "name": "国产系列"}], # 这里仅作示例，实际会读取你的 json
        "STOP_DAYS_AGO": 1
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                current_config = json.load(f)
        except:
            current_config = default_config
    else:
        current_config = default_config

    # 执行双保险检测
    old_url = current_config.get("BASE_URL", "")
    new_url = get_valid_base_url(old_url)
    
    # 如果域名变了，更新 config 对象并写回文件
    if old_url != new_url:
        current_config["BASE_URL"] = new_url
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(current_config, f, indent=4, ensure_ascii=False)
        print(f"📝 域名已从 {old_url} 更新为 {new_url} 并存入 config.json")
    
    return current_config


# --- 4. 网络会话设置 ---
def get_stable_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
        "Referer": BASE_URL
    })
    return session

# --- 5. 存盘逻辑 (倒序去重版 - 修改) ---
def save_and_update(path, new_lines, db_list, db_path):
    """
    修改为倒序排列：今天新抓的在最前面
    """
    items_dict = {}
    
    # 1. 加载旧数据
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            blocks = re.findall(r'(#EXTINF:.*?)(?=#EXTINF:|$)', content, re.S)
            for block in blocks:
                clean_block = block.strip()
                if clean_block:
                    title_line = clean_block.split('\n')[0].strip()
                    items_dict[title_line] = clean_block

    # 2. 合并新数据 (新数据覆盖旧数据，保持 title 唯一)
    for item in new_lines:
        item = item.strip()
        if item:
            title_line = item.split('\n')[0].strip()
            items_dict[title_line] = item

    # 3. 排序逻辑：如果你想让 05-13 在最前，这里使用 reverse=True
    # 这样最新的日期（较大的字符串）会排在前面
    sorted_keys = sorted(items_dict.keys(), reverse=True) 

    # 4. 写入文件
    with open(path, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for k in sorted_keys:
            f.write(items_dict[k] + "\n")
    
    # 更新 JSON 数据库
    with open(db_path, 'w', encoding='utf-8') as f:
        json.dump(db_list, f, ensure_ascii=False, indent=4)

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
    stop_date_threshold = (datetime.now() - timedelta(days=stop_days)).strftime("%m-%d")

    try:
        for p in range(1, 10000):
                # --- 核心改动处 ---
            # 删掉硬编码的 /vodtype/，换成识别出来的 ROUTE_PATH
            # 注意：如果 ROUTE_PATH 是 "/vodtype/"，生成的 url 就是 .../vodtype/2-1.html
            url = f"{BASE_URL}{ROUTE_PATH}{cat_id}-{p}.html"
        
            try:
                res = session.get(url, timeout=15)
                res.encoding = 'utf-8'
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # 检查列表是否存在
                items = soup.find_all('li')
                if not items: break

                # 快速判断是否有真视频 (复用你的逻辑)
                has_real_video = any('/vodplay/' in a.get('href', '') for a in soup.find_all('a'))
                if not has_real_video and p > 1: # 第一页如果有广告很正常，后面页全是广告就停
                    print(f"🏁 第 {p} 页全是广告/非视频内容。")
                    break
                
                print(f"🌐 正在扫描第 {p} 页...")
                found_old_content = False
                
                for li in items:
                    # --- 2. 特征嗅探 ---
                    title_tag = li.find('a', attrs={"title": True})
                    if not title_tag or title_tag.get('target') == 'blank':
                        continue
                    
                    title = title_tag.get('title').strip()
                    href = title_tag.get('href', '')
                    if any(x in href for x in ['javascript', 'about:', 'index.php']):
                        continue

                    # --- 3. 自动识别日期 (防混淆增强版) ---
                    date_val = "01-01"
                
                    # 【关键】不再在整个 li 里盲搜，而是先精准定位到存放日期的 sub 栏目
                    sub_tag = li.find('p', class_='sub')
                    if sub_tag:
                        # 仅在 sub 标签的文字里找日期，这就过滤掉了标题里的 2022-07-10
                        sub_text = sub_tag.get_text(strip=True)
                        # 匹配末尾的 MM-DD
                        date_matches = re.findall(r'(\d{2}-\d{2})', sub_text)
                        if date_matches:
                            # 即使 sub 里有多个符合条件的，日期通常也是最后一个
                            date_val = date_matches[-1]
                
                    # 如果没找到 sub 标签，作为保底，我们搜寻 li 文本中“最后”出现的一个日期格式
                    if date_val == "01-01":
                        li_text = li.get_text(strip=True)
                        all_dates = re.findall(r'(\d{2}-\d{2})', li_text)
                        if all_dates:
                            # 取最后一个，避开标题里可能出现的日期
                            date_val = all_dates[-1]

                    # 打印调试，看看现在识别对了吗
                    # print(f"🔍 标题: {title[:15]}... | 判定日期: {date_val}")

                    # --- 4. 截止判定 ---
                    if p > 3 and date_val != "01-01":
                        if date_val < stop_date_threshold:
                            print(f"⏱️ 探测到旧日期 {date_val}，收割完成。")
                            found_old_content = True
                            break

                    # --- 5. 去重判定 ---
                    v_id_match = re.search(r'(\d+)', href)
                    if not v_id_match: continue
                    v_id = v_id_match.group(1)
                    if v_id in db_set:
                        continue

                    # --- 6. 捕获 M3U8 (带 play 参数) ---
                    try:
                        full_link = urllib.parse.urljoin(BASE_URL, href)
                        play_link = full_link + ("&" if "?" in full_link else "?") + "play=1"
                        
                        p_res = session.get(play_link, timeout=12)
                        m3u8_match = re.search(r'https?[:\\\/]+[^"\']+\.m3u8[^"\']*', p_res.text, re.I)

                        if m3u8_match:
                            m3u8 = m3u8_match.group(0).replace('\\/', '/').replace('\\', '')
                            if "%" in m3u8:
                                m3u8 = urllib.parse.unquote(m3u8)

                            img_tag = li.find('img') or li.find(attrs={"data-original": True})
                            cover_url = ""
                            if img_tag:
                                cover_url = img_tag.get('data-original') or img_tag.get('src') or ""

                            item_entry = f'#EXTINF:-1 tvg-logo="{cover_url}",{title} [{date_val}]\n{m3u8}\n'
                            all_new_entries.append(item_entry)
                            db.append(v_id)
                            db_set.add(v_id)
                            stats["new"] += 1
                            print(f"  ✅ [嗅探成功] {date_val} | {title[:15]}...")
                            
                            if stats["new"] > 0 and stats["new"] % 1000 == 0:
                                print(f"📦 累计 1000 条，同步中...")
                                save_and_update(save_path, all_new_entries, db, db_file)
                                git_push_backup(stats["new"])
                                all_new_entries = [] 
                    except Exception:
                        continue

                if found_old_content: break
                time.sleep(0.5)

            except Exception as e:
                print(f"  🚨 页面出错: {e}")
                break

    except KeyboardInterrupt:
        # --- 核心改进：捕获手动中断 ---
        print("\n\n🛑 检测到手动中断（Ctrl+C）！正在准备紧急存盘...")
    
    finally:
        # --- 无论正常结束还是中断，都会执行这里 ---
        if all_new_entries:
            print(f"💾 正在写入缓存中的 {len(all_new_entries)} 条资源至硬盘...")
            save_and_update(save_path, all_new_entries, db, db_file)
        else:
            print("ℹ️ 无新数据需要保存。")
    
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
    
    # 1. 先加载配置（此时内部会完成域名验证）
    config = load_and_fix_config() 
    
    # 2. 【关键】立即给全局变量 BASE_URL 赋值
    # 这样 get_stable_session 里的 "Referer": BASE_URL 才能找到值
    BASE_URL = config["BASE_URL"] 
    
    # 3. 再初始化会话
    session = get_stable_session()
    
    # 4. 获取路由路径
    ROUTE_PATH = get_route_path(BASE_URL, session)
    
    report = []
    
    print(f"🚀 启动收割程序 | 目标域名: {BASE_URL} | 路由模式: {ROUTE_PATH}")
    
    try:
        # 3. 遍历 config.json 中的分类
        for cat in config.get("CATS", []):
            try:
                # 执行抓取
                res = crawl_category(cat, session)
                report.append({"name": cat["name"], **res})
            except KeyboardInterrupt:
                print(f"\n⚠️ 手动跳过分类: {cat['name']}")
                continue
            except Exception as e:
                print(f"❌ 分类 {cat['name']} 运行出错: {e}")
                continue
                
    finally:
        # 4. 总结与转换
        print(f"\n{'='*30}\n收割总结 (今日日期: {datetime.now().strftime('%m-%d')})\n{'='*30}")
        total_new = 0
        for r in report:
            new_count = r.get('new', 0)
            total_new += new_count
            print(f"  {r['name']}: 新增 {new_count}")
        
        # 5. 阶段性转换 E2 格式
        convert_to_e2_bouquets()
        
        # 6. 如果今天有新货，最后执行一次 Git 推送
        if total_new > 0:
            print(f"📦 今日共收获 {total_new} 条新资源，准备同步至远程仓库...")
            git_push_backup(total_new)
            
        print(f"\n✅ 任务结束! 总耗时: {time.time()-start_time:.1f}s")
