# -*- coding: utf-8 -*-
import re
import json
import time
import base64
import random
import urllib.parse

def decrypt_m3u8(p_res, play_link, base_url, session, has_crypto):
    """
    三道防线合一，专治各种加密战墙 (2026最新 static/count.php 倒计时盾击穿版)
    """
    m3u8 = ""
    html_text = p_res.text
    
    # =========================================================================
    # 防线一：老版本 Fernet (保留向下兼容)
    # =========================================================================
    if "window.VPCFG" in html_text and "window.VPFK" in html_text and has_crypto:
        try:
            vp_cfg = re.search(r"window\.VPCFG\s*=\s*['\"]([^'\"]+)['\"]", html_text).group(1)
            vp_fk = re.search(r"window\.VPFK\s*=\s*['\"]([^'\"]+)['\"]", html_text).group(1)
            from cryptography.fernet import Fernet
            f_cipher = Fernet(vp_fk.encode('utf-8'))
            decrypted_data = f_cipher.decrypt(vp_cfg.encode('utf-8')).decode('utf-8')
            m3u8 = json.loads(decrypted_data).get('url', '')
        except: pass
    
    # =========================================================================
    # 防线二：2026新版本 static/count.php 倒计时盾击穿 (重点升级 🔥)
    # =========================================================================
    elif "count.php" in html_text or "AID" in html_text or "AK" in html_text:
        try:
            # 1. 精准抓取改版后的 4 个全新核心验证参数
            aid_m = re.search(r"AID\s*=\s*['\"]([^'\"]+)['\"]", html_text)
            asid_m = re.search(r"ASID\s*=\s*['\"]([^'\"]+)['\"]", html_text)
            anid_m = re.search(r"ANID\s*=\s*['\"]([^'\"]+)['\"]", html_text)
            ak_m = re.search(r"AK\s*=\s*['\"]([^'\"]+)['\"]", html_text)
            
            if aid_m and ak_m:
                aid = aid_m.group(1)
                asid = asid_m.group(1) if asid_m else "1"
                anid = anid_m.group(1) if anid_m else "1"
                ak = ak_m.group(1)
                
                # 动态拼接新版的请求路由
                api_url = f"{base_url.rstrip('/')}/static/count.php"
                
                ajax_headers = {
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": base_url.rstrip('/'), 
                    "Referer": play_link,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                
                # 2. 完美模拟真人：生成随机轨迹与 >6秒的物理倒计时差
                gx = random.randint(150, 350)       # 模拟手机/PC点击的X坐标
                gy = random.randint(400, 600)       # 模拟点击的Y坐标
                dt = random.randint(6100, 7500)     # 核心：突破6秒限制的等待毫秒数
                current_ts = int(time.time() * 1000)
                
                # 3. 严格按照新版 JS 的 xhrBody 格式组装
                post_data = {
                    "id": aid, 
                    "sid": asid, 
                    "nid": anid, 
                    "tk": ak,          # 注意：前端变量叫 AK，但传参字段依然是 tk
                    "g": "1", 
                    "x": str(gx), 
                    "y": str(gy), 
                    "dt": str(dt),     # 成功注入时间差，欺骗后端放行
                    "sw": "390",       # 假装是移动端 iPhone 分辨率，更不容易触发风控
                    "sh": "844", 
                    "tz": "-480",      # 中国标准时区 (UTC+8)
                    "t": str(current_ts)
                }
                
                # 4. 发送请求并解密脱壳
                api_res = session.post(api_url, data=post_data, headers=ajax_headers, timeout=10)
                if api_res.status_code == 200:
                    res_json = api_res.json()
                    if res_json.get("ok") == 1 and "u" in res_json:
                        # 剥离 Base64 外壳
                        m3u8 = base64.b64decode(res_json["u"]).decode('utf-8')
        except: pass

    # =========================================================================
    # 防线三：保底直接匹配
    # =========================================================================
    if not m3u8:
        m3u8_match = re.search(r'https?[:\\\/]+[^"\']+\.m3u8[^"\']*', html_text, re.I)
        if m3u8_match: 
            m3u8 = m3u8_match.group(0).replace('\\/', '/').replace('\\', '')

    if m3u8 and "%" in m3u8: 
        m3u8 = urllib.parse.unquote(m3u8)
        
    return m3u8
