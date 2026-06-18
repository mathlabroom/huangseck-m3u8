# -*- coding: utf-8 -*-
import os
import re
import json
import time
import urllib.parse
import urllib3
import sys
from datetime import datetime, timedelta

# 🎯 引入咱所有的精细化分布式组件（加上两个新兄弟）
from utils_notifier import send_wechat, git_push_backup
from utils_crawler import get_valid_base_url, get_route_path, get_stable_session
from utils_exporter import save_and_update, convert_to_e2_bouquets
from utils_parser import parse_page_items
from utils_decryptor import decrypt_m3u8

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def load_and_fix_config():
    config_path = "config.json"
    default_config = {"BASE_URL": "http://456172.xyz", "CATS": [{"id": "2", "name": "国产系列"}], "STOP_DAYS_AGO": 1}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f: current_config = json.load(f)
        except: current_config = default_config
    else: current_config = default_config
    old_url = current_config.get("BASE_URL", "")
    new_url = get_valid_base_url(old_url)
    if old_url != new_url:
        current_config["BASE_URL"] = new_url
        with open(config_path, "w", encoding="utf-8") as f: json.dump(current_config, f, indent=4, ensure_ascii=False)
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
    stop_date_threshold = (datetime.now() - timedelta(days=config.get("STOP_DAYS_AGO", 1))).strftime("%m-%d")

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
                
                # 🕵️‍♂️ 【细分调用】：交给专门的情报员解析
                video_items = parse_page_items(res.text)
                if video_items is None:
                    print(f"\n🏁 第 {p} 页无有效黄金特征或已空，收割完毕。")
                    break

                # 🛑 【刹车判定】：取这一页第一条数据的日期
                if video_items and video_items[0]["date_val"] < stop_date_threshold:
                    print(f"\n🛑 [日期触线刹车] 页首日期 {video_items[0]['date_val']} 落后于设定阈值 {stop_date_threshold}，强制收工！")
                    break

                print(f"🌐 正在扫描第 {p} 页...", end="\r")
                
                for item in video_items:
                    file_name = item["href"].split('/')[-1]  
                    v_id_match = re.search(r'(\d+)', file_name) 
                    if not v_id_match: continue
                    v_id = v_id_match.group(1)
                    
                    if len(v_id) < 4 or v_id in db_set: continue
                            
                    try:
                        full_link = urllib.parse.urljoin(base_url, item["href"])
                        play_link = full_link + ("&" if "?" in full_link else "?") + "play=1"
                        p_res = session.get(play_link, timeout=12, verify=False)
                        p_res.encoding = 'utf-8'
                        
                        # 🔐 【细分调用】：交由首席破译官干活
                        m3u8 = decrypt_m3u8(p_res, play_link, base_url, session, has_crypto)

                        if m3u8:
                            item_entry = f'#EXTINF:-1 tvg-logo="{item["cover_url"]}",{item["title"]} [{item["date_val"]}]\n{m3u8}\n'
                            all_new_entries.append(item_entry)
                            db.append(v_id)
                            db_set.add(v_id)
                            stats["new"] += 1
                            print(f"   ✅ [解密成功] {item['date_val']} | {item['title'][:15]}...")
                            
                            # 🛡️ 截断保护：每 10 条追加写一次盘
                            if len(all_new_entries) >= 10:
                                save_and_update(save_path, all_new_entries, db, db_file)
                                all_new_entries = [] 
                    except: continue
                time.sleep(1.2)
            except Exception as e:
                print(f"  🚨 页面出错: {e}")
                break
                
    except KeyboardInterrupt:
        print(f"\n🛑 捕获到当前分类【{cat_name}】遭遇手动中断！启动紧急避险存盘...")
        if all_new_entries:
            save_and_update(save_path, all_new_entries, db, db_file)
            print(f"💾 已将残余的 {len(all_new_entries)} 条新战果安全刻录进 M3U8 磁盘！")
            all_new_entries = []
        raise KeyboardInterrupt  
        
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
                print(f"⚠️ 已安全切断当前分类: {cat['name']} 的后续扫描。")
                break 
            except Exception as e:
                print(f"❌ 分类 {cat['name']} 运行出错: {e}")
                continue
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
            try: convert_to_e2_bouquets(report)
            except Exception as e: print(f"⚠️ E2 精准转换或压缩失败: {e}")
            print(f"\n📊 详细汇总:\n{summary_text}")
            if os.getenv("GITHUB_ACTIONS") == "true":
                send_wechat(f"🚀 今日收割完成！新增 {total_all} 条", f"### 📥 自动收割汇总\n\n{summary_text}\n\n---\n📅 结束时间：{datetime.now().strftime('%m-%d %H:%M')}")
            git_push_backup(total_all)
        else:
            if report: print("\n".join([f"- {r['name']}: 0" for r in report]))
            print("\nℹ️ 库内无任何数据更新，全量躺平。")
        print(f"✅ 流程全部结束，耗时: {time.time()-start_time:.1f}s")
        sys.exit(0)
