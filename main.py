import os, re, random, json, time, requests, urllib.parse
import subprocess
import gzip
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

# 禁用安全请求警告
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
    """阶段性强制备份（带二进制冲突无脑覆盖策略，防止 Actions 挂掉）"""
    try:
        subprocess.run(["git", "config", "--local", "user.email", "action@github.com"], check=True)
        subprocess.run(["git", "config", "--local", "user.name", "GitHub Action"], check=True)
        subprocess.run(["git", "add", "."], check=True)
        msg = f"自动备份: 累计新增 {count} 条资源并同步配置"
        subprocess.run(["git", "commit", "-m", msg], check=False)
        
        print("🔄 正在同步远程仓库状态（如遇二进制冲突，将以本地最新数据为准）...")
        # 🎯 加上 -X ours 参数，遇到 .tv.gz 冲突直接以本地新生成的为准，拒绝远程旧包
        result = subprocess.run(["git", "pull", "origin", "main", "--rebase", "-X", "ours"], check=False)
        
        if result.returncode != 0:
            print("⚠️ 检测到强力冲突，执行强制覆盖策略...")
            subprocess.run(["git", "add", "."], check=False)
            subprocess.run(["git", "rebase", "--continue"], check=False)

        subprocess.run(["git", "push", "origin", "main"], check=True)
        print(f"🚀 [同步成功] 数据已推送至仓库")
    except Exception as e:
        print(f"⚠️ [同步跳过] 遇到冲突或网络问题: {e}")
        subprocess.run(["git", "rebase", "--abort"], check=False)

# --- 2. 完美的自动寻路与域名智能嗅探逻辑 ---

def get_valid_base_url(current_url):
    """
    智能探路者：验证当前域名，若失效则通过固定发布页自动追踪并抓取最新的跳转域名。
    不再进行愚蠢的数字循环拼运气。
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    print(f"🔍 正在验证当前预设域名: {current_url}")
    try:
        if current_url:
            res = requests.get(f"{current_url}/vodtype/2-1.html", headers=headers, timeout=6, verify=False)
            if res.status_code == 200 and "stui-vodlist" in res.text:
                print("✅ 预设域名依然稳健有效，继续执行。")
                return current_url
    except:
        pass

    # 🚨 走到这里说明预设域名已经寿终正寝，启动核心自动寻路机制
    print("⚠️ 预设域名已失效！启动智能追踪器搜寻新入口...")
    
    # 固定的永久发布页/导航页（如果这个变了，只需改这里）
    anchor_host = "http://hsck.us" 
    try:
        print(f"📡 正在请求永久发布页: {anchor_host}")
        req_res = requests.get(anchor_host, headers=headers, timeout=10, verify=False)
        html = req_res.text
        soup = BeautifulSoup(html, "lxml" if "lxml" in html else "html.parser")

        # 🎯 策略一：检查是否身处带有跳转代码的引导页
        if "strU=" in html and soup.find(id="hao123"):
            match = re.search(r'strU="(https?://[a-zA-Z0-9:/.]+\?u=?)"', html)
            if match:
                redirect_url = f"{match.group(1)}{anchor_host}/&p=/"
                print(f"🔗 捕获到动态跳转接口: {redirect_url}，正在追踪最终归宿...")
                # 追踪 302 重定向响应头里的 Location
                track_res = requests.head(redirect_url, headers=headers, timeout=8, verify=False, allow_redirects=False)
                location = track_res.headers.get("Location")
                if location:
                    loc_match = re.match(r"(https?://[a-zA-Z0-9][-a-zA-Z0-9]{0,62}(\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+)", location)
                    if loc_match:
                        discovered_url = loc_match.group(1)
                        print(f"🚀 [追踪成功] 通过重定向接口捕获到最新官网: {discovered_url}")
                        return discovered_url

        # 🎯 策略二：如果发布页已经直接展现了官网内容（没有拦截墙）
        if len(html) > 20000 and soup.find(class_="stui-warp-content"):
            print(f"🚀 [寻路成功] 发布页本身已展现官网特征，直接采用: {anchor_host}")
            return anchor_host

    except Exception as tracker_err:
        print(f"❌ 智能寻路系统发生故障: {tracker_err}")

    # 🍂 实在找不到的终极摆烂保底：返回原域名，寄希望于下次网络恢复
    print("⚠️ 寻路系统未能探明新域名，维持原域名进入观察期。")
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
        print(f"📝 智能雷达已将新域名 {new_url} 写入持久化配置文件 config.json")
    
    return current_config

# --- 4. 网络会话设置 ---
def get_stable_session(base_url):
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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

# --- 6. 核心收割逻辑 (带 Fernet 密码破解版) ---
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
                res = session.get(url, timeout=15, verify=False)
                if res.status_code >= 500:
                    print(f"⚠️ 目标服务器异常 (Status: {res.status_code})，触发紧急避险收工...")
                    break
                res.encoding = 'utf-8'
                soup = BeautifulSoup(res.text, 'html.parser')
                
                items = soup.find_all('li')
                if not items: 
                    print(f"\n🏁 第 {p} 页已无更多内容，全量收割完毕。")
                    break

                # 🎯 【步骤一】全页真视频大检测（全区域模糊匹配，广告页直接绝杀）
                has_real_video = any(
                    "tutu1.space" in str(li) for li in items
                )

                if not has_real_video: 
                    print(f"🏁 第 {p} 页未能匹配到任何 tutu1.space 黄金特征，判定为纯广告垃圾页，收工。")
                    break
                
                # 🎯 【步骤二】有真货！立刻提取这一页“最新真视频的日期”用来判定刹车
                page_latest_date = None
                for first_li in items:
                    # 只要这个 li 包含黄金域名，说明它是这一页排在最上面的真视频（刨除置顶广告）
                    if "tutu1.space" in str(first_li):
                        p_sub = first_li.find('p', class_='sub')
                        if p_sub:
                            sub_text = p_sub.get_text(" ", strip=True)
                            date_matches = re.findall(r'(\d{2}-\d{2})', sub_text)
                            if date_matches:
                                page_latest_date = date_matches[-1]
                                break  # 剥离出最新日期，功成身退

                # 🎯 【步骤三】对比截止日期，决定是否一脚踩死刹车
                if page_latest_date:
                    if page_latest_date < stop_date_threshold:
                        print(f"\n🛑 [日期触线刹车] 第 {p} 页最新资源日期为 {page_latest_date}，已落后于设定阈值 {stop_date_threshold}，强制收工！")
                        break
                else:
                    print(f"⚠️ 未能提取到第 {p} 页的头部日期标签，安全起见继续扫描...")

                print(f"🌐 正在扫描第 {p} 页...", end="\r")
                
                # --- 开始单条收割 ---
                for li in items:
                    h4_title = li.find('h4', class_='title')
                    if not h4_title: continue
                    
                    title_tag = h4_title.find('a')
                    if not title_tag: continue
                    
                    title = title_tag.get('title') or title_tag.get_text(strip=True)
                    title = title.strip()
                    href = title_tag.get('href', '').strip()
                    
                    # 🚫 强力斩杀线：绝对路径外链（广告）直接踢出
                    if href.startswith('http://') or href.startswith('https://'): continue
                    if any(x in href for x in ['javascript', 'about:', 'index.php', 'channelCode']): continue

                    # 🎯 【图片防线】单条精准区域过滤
                    # 只要整个 <li> 块的 HTML 源码里不包含核心域名，百分之百是牛皮癣，直接扔掉！
                    if "tutu1.space" not in str(li): 
                        continue

                    # 📸 【智能多手保底】安全提取封面图
                    cover_url = ""
                    img_tag = li.find(['img', 'a'], class_='lazyload') or li.find('img')
                    if img_tag:
                        # 广撒网属性提取
                        cover_url = (img_tag.get('data-original') or 
                                     img_tag.get('src') or 
                                     img_tag.get('data-src') or "")
                    
                    # 🛡️ 终极正则保底：如果属性没捞着，直接从 HTML 源码中生吞带特征的 URL
                    if not cover_url or "tutu1.space" not in cover_url:
                        img_urls = re.findall(r'(https?://[^\s"\']+tutu1\.space[^\s"\']+)', str(li))
                        if img_urls:
                            cover_url = img_urls[0]

                    # 📅 【精准吸附更新日期】（老哥你原版这段正则保底写得很好，保留）
                    date_val = "01-01"
                    p_sub = li.find('p', class_='sub')
                    if p_sub:
                        sub_text = p_sub.get_text(" ", strip=True)
                        date_matches = re.findall(r'(\d{2}-\d{2})', sub_text)
                        if date_matches: 
                            date_val = date_matches[-1] 
                
                    if date_val == "01-01":
                        all_dates = re.findall(r'(\d{2}-\d{2})', li.get_text(strip=True))
                        if all_dates: 
                            date_val = all_dates[-1]

                    # --- 去重判定与后续解密 ---
                    v_id_match = re.search(r'(\d+)', href)
                    if not v_id_match: continue
                    v_id = v_id_match.group(1)
                    if v_id in db_set: continue

                    # --- 捕获 M3U8 ---
                    try:
                        full_link = urllib.parse.urljoin(BASE_URL, href)
                        play_link = full_link + ("&" if "?" in full_link else "?") + "play=1"
                        
                        p_res = session.get(play_link, timeout=12, verify=False)
                        p_res.encoding = 'utf-8'
                        
                        m3u8 = ""
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
                        
                        if not m3u8:
                            m3u8_match = re.search(r'https?[:\\\/]+[^"\']+\.m3u8[^"\']*', p_res.text, re.I)
                            if m3u8_match:
                                m3u8 = m3u8_match.group(0).replace('\\/', '/').replace('\\', '')

                        if m3u8:
                            if "%" in m3u8:
                                m3u8 = urllib.parse.unquote(m3u8)

                            # 🌟 日期在这里被完美重新组装进台单！
                            item_entry = f'#EXTINF:-1 tvg-logo="{cover_url}",{title} [{date_val}]\n{m3u8}\n'
                            all_new_entries.append(item_entry)
                            db.append(v_id)
                            db_set.add(v_id)
                            stats["new"] += 1
                            print(f"   ✅ [解密成功] {date_val} | {title[:15]}...")
                            
                            if stats["new"] > 0 and stats["new"] % 1000 == 0:
                                save_and_update(save_path, all_new_entries, db, db_file)
                                git_push_backup(stats["new"])
                                all_new_entries = [] 
                    except Exception:
                        continue


                time.sleep(1.2)

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
def convert_to_e2_bouquets(report_list=None):
    BASE_DIR = './VideoResults'
    OUTPUT_DIR = './E2_Bouquets'
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    CATEGORY_MAP = {
        "国产系列": "65", "骑兵破解": "66", "无码中文字幕": "67", "有码中文字幕": "68",
        "日本有码": "69", "日本无码": "6A", "欧美高清": "6B", "动漫": "6C"
    }

    # 把报告转换成字典方便快速查询，如 {"国产系列": 0, "日本有码": 3}
    report_dict = {r['name']: r.get('new', 0) for r in report_list if isinstance(r, dict)} if report_list else {}

    for cat_name, hex_id in CATEGORY_MAP.items():
        m3u8_path = os.path.join(BASE_DIR, cat_name, f"{cat_name}.m3u8")
        tv_path = os.path.join(OUTPUT_DIR, f"subbouquet.{cat_name}.tv")
        gz_path = tv_path + '.gz'
        
        if not os.path.exists(m3u8_path): continue
        
        # 🎯 【精准拦截点】如果这个分类今天新增为 0，且本地早就有打包好的 .tv.gz 了，直接无视，绝不重写！
        if report_dict.get(cat_name, 0) == 0 and os.path.exists(gz_path):
            print(f"      ℹ️ 分类【{cat_name}】今日无新增，完美跳过 E2 转换与打包。")
            continue

        # 只有有新货的分类，才会走到下面的重写逻辑
        print(f"      🗜️ 分类【{cat_name}】探测到新资源，正在刷新 .tv 并重新打包 .tv.gz...")
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
        
        # 写入 .tv
        with open(tv_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(output_lines) + "\n")
            
        # 顺手直接把这个变动的分类打成 .tv.gz
        with open(tv_path, 'rb') as f_in:
            with gzip.open(gz_path, 'wb') as f_out:
                f_out.writelines(f_in)

if __name__ == "__main__":
    start_time = time.time()
    
    # 智能寻路，并初始化配置
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
        
        total_all = sum(r.get('new', 0) for r in report if isinstance(r, dict)) if 'report' in locals() and report else 0
        summary_text = "\n".join([f"- {r['name']}: +{r['new']}" for r in report]) if 'report' in locals() and report else ""

        if total_all > 0:
            print("🔄 正在启动按需精准增量打包...")
            try:
                # 🎯 传入今日战果报告，里面会自动判定谁该打包，谁该躺平
                convert_to_e2_bouquets(report)
            except Exception as e:
                print(f"⚠️ E2 精准转换或压缩失败: {e}")

            print(f"\n📊 详细汇总:\n{summary_text}")
            if os.getenv("GITHUB_ACTIONS") == "true":
                msg_title = f"🚀 今日收割完成！新增 {total_all} 条"
                msg_content = f"### 📥 自动收割汇总\n\n{summary_text}\n\n---\n📅 结束时间：{datetime.now().strftime('%m-%d %H:%M')}"
                send_wechat(msg_title, msg_content)
            else:
                print(f"🏠 本地运行检测到新数据...")

            git_push_backup(total_all)
            
        else:
            if 'report' in locals() and report:
                print("\n".join([f"- {r['name']}: 0" for r in report]))
            print("\nℹ️ 库内无任何数据更新，全量躺平，跳过所有写入与 Git 同步。")

        print(f"✅ 流程全部结束，耗时: {time.time()-start_time:.1f}s")
