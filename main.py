# -*- coding: utf-8 -*-
import os
import re
import json
import time
import urllib.parse
import urllib3
import sys
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# 🎯 引入咱自己的分布式功能模块
from utils_notifier import send_wechat, git_push_backup
from utils_crawler import get_valid_base_url, get_route_path, get_stable_session
from utils_exporter import save_and_update, convert_to_e2_bouquets

# 禁用安全请求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

def crawl_category(cat, session, config, base_url, route_path):
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

    has_crypto = False
    try:
        from cryptography.fernet import Fernet
        has_crypto = True
    except ImportError:
        print("⚠️ 提示: 未检测到 cryptography 库，将无法破解老版验证墙。")

    try:
        for p in range(1, 10000):
            url = f"{base_url}{route_path}{cat_id}-{p}.html"
            try:
                res = session.get(url, timeout=15, verify=False)
                if res.status_code >= 500:
                    print(f"⚠️ 目标服务器异常 (Status: {res.status_code})，触发紧急避险...")
                    break
                res.encoding = 'utf-8'
                soup = BeautifulSoup(res.text, 'html.parser')
                
                items = soup.find_all('li')
                if not items: 
                    print(f"\n🏁 第 {p} 页已无更多内容，收割完毕。")
                    break

                # 【检测真视频区域】
                has_real_video = any("tutu1.space" in str(li) for li in items)
                if not has_real_video: 
                    print(f"🏁 第 {p} 页未能匹配到黄金特征，判定为纯广告垃圾页。")
                    break
                
                # 【刹车机制】
                page_latest_date = None
                for first_li in items:
                    if "tutu1.space" in str(first_li):
                        p_sub = first_li.find('p', class_='sub')
                        if p_sub:
                            sub_text = p_sub.get_text(" ", strip=True)
                            date_matches = re.findall(r'(\d{2}-\d{2})', sub_text)
                            if date_matches:
                                page_latest_date = date_matches[-1]
                                break

                if page_latest_date and page_latest_date < stop_date_threshold:
                    print(f"\n🛑 [日期触线刹车] 页日期为 {page_latest_date}，落后于设定阈值 {stop_date_threshold}，强制收工！")
                    break

                print(f"🌐 正在扫描第 {p} 页...", end="\r")
                
                for li in items:
                    h4_title = li.find('h4', class_='title')
                    if not h4_title: continue
                    title_tag = h4_title.find('a')
                    if not title_tag: continue
                    
                    title = (title_tag.get('title') or title_tag.get_text(strip=True)).strip()
                    href = title_tag.get('href', '').strip()
                    
                    if href.startswith('http://') or href.startswith('https://'): continue
                    if any(x in href for x in ['javascript', 'about:', 'index.php', 'channelCode']): continue
                    if "tutu1.space" not in str(li): continue

                    # 提取封面图
                    cover_url = ""
                    img_tag = li.find(['img', 'a'], class_='lazyload') or li.find('img')
                    if img_tag:
                        cover_url = (img_tag.get('data-original') or img_tag.get('src') or img_tag.get('data-src') or "")
                    if not cover_url or "tutu1.space" not in cover_url:
                        img_urls = re.findall(r'(https?://[^\s"\']+tutu1\.space[^\s"\']+)', str(li))
                        if img_urls: cover_url = img_urls[0]

                    # 提取更新日期
                    date_val = "01-01"
                    p_sub = li.find('p', class_='sub')
                    if p_sub:
                        sub_text = p_sub.get_text(" ", strip=True)
                        date_matches = re.findall(r'(\d{2}-\d{2})', sub_text)
                        if date_matches: date_val = date_matches[-1] 
                    if date_val == "01-01":
                        all_dates = re.findall(r'(\d{2}-\d{2})', li.get_text(strip=True))
                        if all_dates: date_val = all_dates[-1]

                    # --- 去重判定 ---
                    file_name = href.split('/')[-1]  
                    v_id_match = re.search(r'(\d+)', file_name) 
                    if not v_id_match: continue
                    v_id = v_id_match.group(1)
                    
                    if len(v_id) < 4: 
                        print(f"   ⚠️ 过滤非正常视频ID: {v_id} (文件名: {file_name})，直接跳过。")
                        continue
                    if v_id in db_set: continue
                            
                    # --- 捕获 M3U8 解密战墙 ---
                    try:
                        full_link = urllib.parse.urljoin(base_url, href)
                        play_link = full_link + ("&" if "?" in full_link else "?") + "play=1"
                        p_res = session.get(play_link, timeout=12, verify=False)
                        p_res.encoding = 'utf-8'
                        m3u8 = ""
                        
                        # 防线一：老版本 Fernet
                        if "window.VPCFG" in p_res.text and "window.VPFK" in p_res.text and has_crypto:
                            try:
                                vp_cfg = re.search(r"window\.VPCFG\s*=\s*['\"]([^'\"]+)['\"]", p_res.text).group(1)
                                vp_fk = re.search(r"window\.VPFK\s*=\s*['\"]([^'\"]+)['\"]", p_res.text).group(1)
                                from cryptography.fernet import Fernet
                                f_cipher = Fernet(vp_fk.encode('utf-8'))
                                decrypted_data = f_cipher.decrypt(vp_cfg.encode('utf-8')).decode('utf-8')
                                m3u8 = json.loads(decrypted_data).get('url', '')
                            except: pass
                        
                        # 防线二：新版本 vp_url.php Ajax 截胡
                        elif "vp_url.php" in p_res.text or "VPID" in p_res.text:
                            try:
                                import base64
                                vpid_m = re.search(r"var\s+VPID\s*=\s*'(\d+)'", p_res.text) or re.search(r'data-id="(\d+)"', p_res.text)
                                vpsid_m = re.search(r"var\s+VPSID\s*=\s*'(\d+)'", p_res.text)
                                vpnid_m = re.search(r"var\s+VPNID\s*=\s*'(\d+)'", p_res.text)
                                if vpid_m:
                                    vpid = vpid_m.group(1)
                                    vpsid = vpsid_m.group(1) if vpsid_m else "1"
                                    vpnid = vpnid_m.group(1) if vpnid_m else "1"
                                    ajax_headers = {
                                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                                        "X-Requested-With": "XMLHttpRequest",
                                        "Origin": base_url.rstrip('/'), "Referer": play_link
                                    }
                                    post_data = {"id": vpid, "sid": vpsid, "nid": vpnid, "t": str(int(time.time() * 1000))}
                                    api_res = session.post(f"{base_url.rstrip('/')}/vp_url.php", data=post_data, headers=ajax_headers, timeout=10)
                                    if api_res.status_code == 200 and api_res.json().get("ok"):
                                        m3u8 = base64.b64decode(api_res.json()["u"]).decode('utf-8')
                            except: pass

                        # 防线三：保底直接匹配
                        if not m3u8:
                            m3u8_match = re.search(r'https?[:\\\/]+[^"\']+\.m3u8[^"\']*', p_res.text, re.I)
                            if m3u8_match: m3u8 = m3u8_match.group(0).replace('\\/', '/').replace('\\', '')

                        if m3u8:
                            if "%" in m3u8: m3u8 = urllib.parse.unquote(m3u8)
                            item_entry = f'#EXTINF:-1 tvg-logo="{cover_url}",{title} [{date_val}]\n{m3u8}\n'
                            all_new_entries.append(item_entry)
                            db.append(v_id)
                            db_set.add(v_id)
                            stats["new"] += 1
                            print(f"   ✅ [解密成功] {date_val} | {title[:15]}...")
                            
                            # 🛡️ 【截断核心保护一】：降低积压，每抓到 10 条就立刻强制存盘，防止 Ctrl+C 导致大面积丢失
                            if len(all_new_entries) >= 10:
                                save_and_update(save_path, all_new_entries, db, db_file)
                                all_new_entries = [] 
                                
                            # 每 1000 条进行一次大备份
                            if stats["new"] > 0 and stats["new"] % 1000 == 0:
                                if all_new_entries:
                                    save_and_update(save_path, all_new_entries, db, db_file)
                                    all_new_entries = []
                                git_push_backup(stats["new"])
                    except: continue
                time.sleep(1.2)
            except Exception as e:
                print(f"  🚨 页面出错: {e}")
                break
    # 🛡️ 【截断核心保护二】：如果在分类循环内部直接触发 Ctrl+C
    except KeyboardInterrupt:
        print(f"\n🛑 捕获到当前分类【{cat_name}】遭遇手动中断！启动紧急避险存盘...")
        if all_new_entries:
            save_and_update(save_path, all_new_entries, db, db_file)
            print(f"💾 已将残余的 {len(all_new_entries)} 条新战果安全刻录进 M3U8 磁盘！")
            all_new_entries = []
        raise KeyboardInterrupt  # 继续向上抛出，交给主发动机作大结局结算
        
    finally:
        if all_new_entries:
            save_and_update(save_path, all_new_entries, db, db_file)
    return stats

if __name__ == "__main__":
    start_time = time.time()
    
    config = load_and_fix_config() 
    BASE_URL = config["BASE_URL"] 
    session = get_stable_session(BASE_URL)
    ROUTE_PATH = get_route_path(BASE_URL, session)
    
    report = []
    print(f"🚀 启动收割程序 | 目标域名: {BASE_URL} | 路由模式: {ROUTE_PATH}")
    
    try:
        for cat in config.get("CATS", []):
            try:
                res = crawl_category(cat, session, config, BASE_URL, ROUTE_PATH)
                report.append({"name": cat["name"], **res})
            except KeyboardInterrupt:
                # 接收到了内部丢上来的中断信号
                print(f"⚠️ 已安全切断当前分类: {cat['name']} 的后续扫描。")
                break # 直接跳出全部分类大循环，强行进入下面的大结局阶段
            except Exception as e:
                print(f"❌ 分类 {cat['name']} 运行出错: {e}")
                continue
                
    # 🛡️ 【截断核心保护三】：如果是在中间过度空档期按的 Ctrl+C
    except KeyboardInterrupt:
        print("\n🛑 接收到全局终结指令！正在无缝切入总结与打包流程...")
        
    except Exception as e:
        print(f"💥 主程序严重异常: {e}")
        
    finally:
        print(f"\n{'='*30}\n收割总结 (今日日期: {datetime.now().strftime('%m-%d')})\n{'='*30}")
        total_all = sum(r.get('new', 0) for r in report if isinstance(r, dict)) if report else 0
        summary_text = "\n".join([f"- {r['name']}: +{r['new']}" for r in report]) if report else ""

        if total_all > 0:
            print("🔄 正在启动按需精准增量打包...")
            try:
                convert_to_e2_bouquets(report)
            except Exception as e:
                print(f"⚠️ E2 精准转换或压缩失败: {e}")

            print(f"\n📊 详细汇总:\n{summary_text}")
            if os.getenv("GITHUB_ACTIONS") == "true":
                send_wechat(f"🚀 今日收割完成！新增 {total_all} 条", f"### 📥 自动收割汇总\n\n{summary_text}\n\n---\n📅 结束时间：{datetime.now().strftime('%m-%d %H:%M')}")
            else:
                print(f"🏠 本地运行检测到新数据...")
            git_push_backup(total_all)
        else:
            if report: print("\n".join([f"- {r['name']}: 0" for r in report]))
            print("\nℹ️ 库内无任何数据更新，全量躺平。")

        print(f"✅ 流程全部结束，耗时: {time.time()-start_time:.1f}s")
        sys.exit(0)
