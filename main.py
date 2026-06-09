import os, re, random, json, time, requests, urllib.parse
import subprocess
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

# 禁用警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. 通知与备份函数 ---

def send_wechat(title, content):
    """通过 Server酱 推送消息"""
    push_key = os.getenv("PUSH_KEY")
    if not push_key:
        print("⚠️ 未配置 PUSH_KEY，取消微信推送")
        return

    url = f"https://sctapi.ftqq.com/{push_key}.send"
    data = {"title": title, "desp": content}
    try:
        res = requests.post(url, data=data, timeout=10)
        if res.status_code == 200:
            print("🔔 微信通知发送成功")
    except Exception as e:
        print(f"❌ 微信通知发送失败: {e}")

def git_push_backup(count):
    """阶段性强制备份"""
    try:
        subprocess.run(["git", "config", "--local", "user.email", "action@github.com"], check=True)
        subprocess.run(["git", "config", "--local", "user.name", "GitHub Action"], check=True)
        subprocess.run(["git", "add", "."], check=True)
        msg = f"自动备份: 累计新增 {count} 条资源并同步配置"
        subprocess.run(["git", "commit", "-m", msg], check=False)
        print("🔄 正在同步远程仓库状态...")
        subprocess.run(["git", "pull", "origin", "main", "--rebase"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print(f"🚀 [同步成功] 数据已推送至仓库")
    except Exception as e:
        print(f"⚠️ [同步跳过] 遇到冲突或网络问题: {e}")
        subprocess.run(["git", "rebase", "--abort"], check=False)

# --- 2. 域名双保险嗅探逻辑 ---
def get_valid_base_url(current_url):
    """双保险：验证当前域名，若失效则基于数字规律自动探测新入口"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."}
    
    print(f"🔍 正在验证预设域名: {current_url}")
    try:
        res = requests.get(f"{current_url}/vodtype/2-1.html", headers=headers, timeout=5, verify=False)
        if res.status_code == 200 and "stui-vodlist" in res.text:
            print("✅ 域名有效，继续执行。")
            return current_url
    except:
        pass

    print("⚠️ 预设域名失效，启动自动寻路...")

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
    """直接从首页源码解析出当前的分类路由格式"""
    try:
        res = session.get(base_url, timeout=10, verify=False)
        res.encoding = 'utf-8'
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
        "CATS": [{"id": "2", "name": "国产系列"}],
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

    old_url = current_config.get("BASE_URL", "")
    new_url = get_valid_base_url(old_url)
    
    if old_url != new_url:
        current_config["BASE_URL"] = new_url
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(current_config, f, indent=4, ensure_ascii=False)
        print(f"📝 域名已从 {old_url} 更新为 {new_url} 并存入 config.json")
    
    return current_config

# --- 4. 网络会话设置 ---
def get_stable_session(base_url):
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
        "Referer": base_url
    })
    return session

# --- 5. 存盘逻辑 (倒序去重版) ---
def save_and_update(path, new_lines, db_list, db_path):
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

    # 2. 合并新数据
    for item in new_lines:
        item = item.strip()
        if item:
            title_line = item.split('\n')[0].strip()
            items_dict[title_line] = item

    # 3. 倒序排列（最新日期在最前）
    sorted_keys = sorted(items_dict.keys(), reverse=True) 

    # 4. 写入文件
    with open(path, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for k in sorted_keys:
            f.write(items_dict[k] + "\n")
    
    # 更新 JSON 数据库
    with open(db_path, 'w', encoding='utf-8') as f:
        json.dump(db_list, f, ensure_ascii=False, indent=4)

# --- 6. 核心收割逻辑 (高精准改版) ---
# --- 6. 核心收割逻辑 (带 Fernet 暴力破解版) ---
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

    # 🔒 检查解密环境
    has_crypto = False
    try:
        from cryptography.fernet import Fernet
        has_crypto = True
    except ImportError:
        print("⚠️ 提示: 未检测到 cryptography 库，将无法破解新版验证墙，请确保 pip install cryptography")

    try:
        for p in range(1, 10000):
            url = f"{BASE_URL}{ROUTE_PATH}{cat_id}-{p}.html"
        
            try:
                res = session.get(url, timeout=15)
                if res.status_code >= 500:
                    print(f"⚠️ 目标服务器异常 (Status: {res.status_code})，触发紧急避险收工...")
                    break
                res.encoding = 'utf-8'
                soup = BeautifulSoup(res.text, 'html.parser')
                
                items = soup.find_all('li')
                if not items: break

                # 快速判断是否有真视频 
                has_real_video = any('/v/' in a.get('href', '') or '/vodplay/' in a.get('href', '') for a in soup.find_all('a'))
                if not has_real_video and p > 1: 
                    print(f"🏁 第 {p} 页全是广告/非视频内容。")
                    break
                
                print(f"🌐 正在扫描第 {p} 页...")
                found_old_content = False
                
                for li in items:
                    # 🎯 精准下沉到 h4.title 节点拿 A 标签，洗掉外链广告
                    h4_title = li.find('h4', class_='title')
                    if not h4_title: continue
                    
                    title_tag = h4_title.find('a')
                    if not title_tag: continue
                    
                    title = title_tag.get('title') or title_tag.get_text(strip=True)
                    title = title.strip()
                    href = title_tag.get('href', '').strip()
                    
                    # 🚫 强力斩杀线：如果是绝对路径外链或带引流特征，直接踢出
                    if href.startswith('http://') or href.startswith('https://'): continue
                    if any(x in href for x in ['javascript', 'about:', 'index.php', 'channelCode']): continue
                    if not title or any(x in title for x in ["勾引", "强上", "性爱"]): continue 

                    # 📅 精准吸附更新日期
                    date_val = "01-01"
                    p_sub = li.find('p', class_='sub')
                    if p_sub:
                        sub_text = p_sub.get_text(strip=True)
                        date_matches = re.findall(r'(\d{2}-\d{2})', sub_text)
                        if date_matches:
                            date_val = date_matches[-1] 
                
                    if date_val == "01-01":
                        all_dates = re.findall(r'(\d{2}-\d{2})', li.get_text(strip=True))
                        if all_dates: date_val = all_dates[-1]

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
                    if v_id in db_set: continue

                    # --- 6. 捕获 M3U8 (解密/常规双保底) ---
                    try:
                        full_link = urllib.parse.urljoin(BASE_URL, href)
                        play_link = full_link + ("&" if "?" in full_link else "?") + "play=1"
                        
                        p_res = session.get(play_link, timeout=12)
                        p_res.encoding = 'utf-8'
                        
                        m3u8 = ""
                        
                        # ✨ 策略 A：如果触发了加密墙，且环境支持，直接硬解
                        if "window.VPCFG" in p_res.text and "window.VPFK" in p_res.text:
                            if has_crypto:
                                try:
                                    vp_cfg = re.search(r"window\.VPCFG\s*=\s*['\"]([^'\"]+)['\"]", p_res.text).group(1)
                                    vp_fk = re.search(r"window\.VPFK\s*=\s*['\"]([^'\"]+)['\"]", p_res.text).group(1)
                                    
                                    f_cipher = Fernet(vp_fk.encode('utf-8'))
                                    decrypted_data = f_cipher.decrypt(vp_cfg.encode('utf-8')).decode('utf-8')
                                    
                                    json_data = json.loads(decrypted_data)
                                    m3u8 = json_data.get('url', '')
                                except Exception as decrypt_err:
                                    print(f"   ❌ 算法破译失败: {decrypt_err}")
                            else:
                                print("   ⚠️ 遭遇验证墙，但因缺乏 cryptography 库，无法解密！")
                        
                        # ✨ 策略 B：老版本兼容（如果没有加密墙，直接正则抓）
                        if not m3u8:
                            m3u8_match = re.search(r'https?[:\\\/]+[^"\']+\.m3u8[^"\']*', p_res.text, re.I)
                            if m3u8_match:
                                m3u8 = m3u8_match.group(0).replace('\\/', '/').replace('\\', '')

                        # 保存逻辑
                        if m3u8:
                            if "%" in m3u8:
                                m3u8 = urllib.parse.unquote(m3u8)

                            img_tag = li.find('img') or li.find('a', class_='lazyload')
                            cover_url = ""
                            if img_tag:
                                cover_url = img_tag.get('data-original') or img_tag.get('src') or ""

                            item_entry = f'#EXTINF:-1 tvg-logo="{cover_url}",{title} [{date_val}]\n{m3u8}\n'
                            all_new_entries.append(item_entry)
                            db.append(v_id)
                            db_set.add(v_id)
                            stats["new"] += 1
                            print(f"  ✅ [解密成功] {date_val} | {title[:15]}...")
                            
                            if stats["new"] > 0 and stats["new"] % 1000 == 0:
                                save_and_update(save_path, all_new_entries, db, db_file)
                                git_push_backup(stats["new"])
                                all_new_entries = [] 
                    except Exception:
                        continue

                if found_old_content: break
                time.sleep(1.5)

            except Exception as e:
                print(f"  🚨 页面出错: {e}")
                break

    except KeyboardInterrupt:
        print("\n\n🛑 检测到手动中断！正在紧急存盘...")
    finally:
        if all_new_entries:
            print(f"💾 正在写入缓存中的 {len(all_new_entries)} 条资源至硬盘...")
            save_and_update(save_path, all_new_entries, db, db_file)
        
    return stats

# --- 7. E2 Bouquet 转换 ---
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

if __name__ == "__main__":
    start_time = time.time()
    
    # 初始化
    config = load_and_fix_config() 
    BASE_URL = config["BASE_URL"] 
    session = get_stable_session(BASE_URL)
    ROUTE_PATH = get_route_path(BASE_URL, session)
    
    report = []
    print(f"🚀 启动收割程序 | 目标域名: {BASE_URL} | 路由模式: {ROUTE_PATH}")
    
    try:
        # 执行抓取
        for cat in config.get("CATS", []):
            try:
                res = crawl_category(cat, session)
                report.append({"name": cat["name"], **res})
            except KeyboardInterrupt:
                print(f"\n⚠️ 手动跳过分类: {cat['name']}")
                continue
            except Exception as e:
                print(f"❌ 分类 {cat['name']} 运行出错: {e}")
                continue
                
    except Exception as e:
        print(f"💥 主程序严重异常: {e}")
        
    finally:
        print(f"\n{'='*30}\n收割总结 (今日日期: {datetime.now().strftime('%m-%d')})\n{'='*30}")
        
        try:
            convert_to_e2_bouquets()
            
            import gzip
            E2_DIR = './E2_Bouquets'
            if os.path.exists(E2_DIR):
                for file_name in os.listdir(E2_DIR):
                    if file_name.endswith('.tv'):
                        tv_path = os.path.join(E2_DIR, file_name)
                        gz_path = tv_path + '.gz'
                        with open(tv_path, 'rb') as f_in:
                            with gzip.open(gz_path, 'wb') as f_out:
                                f_out.writelines(f_in)
                print("🗜️ [压缩成功] E2_Bouquets 目录下的 .tv 文件已全部同步生成 .tv.gz")
            
        except Exception as e:
            print(f"⚠️ E2 节目单转换或压缩失败: {e}")

        # 汇总报告与强制同步
        if 'report' in locals() and report:
            total_all = sum(r.get('new', 0) for r in report if isinstance(r, dict))
            summary_text = "\n".join([f"- {r['name']}: +{r['new']}" for r in report])
            
            print(f"📊 详细汇总:\n{summary_text}")
            
            if total_all > 0:
                if os.getenv("GITHUB_ACTIONS") == "true":
                    msg_title = f"🚀 今日收割完成！新增 {total_all} 条"
                    msg_content = f"### 📥 自动收割汇总\n\n{summary_text}\n\n---\n📅 结束时间：{datetime.now().strftime('%m-%d %H:%M')}"
                    send_wechat(msg_title, msg_content)
                else:
                    print(f"🏠 本地运行检测到新数据...")

                git_push_backup(total_all)
            else:
                print("ℹ️ 库内无数据更新，跳过同步。")
        else:
            print("ℹ️ 任务结束，未生成有效报告。")

        print(f"✅ 流程全部结束，耗时: {time.time()-start_time:.1f}s")
