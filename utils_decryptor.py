# -*- coding: utf-8 -*-
import re
import json
import time
import base64
import random
import urllib.parse

def decrypt_m3u8(p_res, play_link, base_url, session, has_crypto):
    """
    三道防线合一，专治各种加密战墙 (手势动态盾击穿版)
    """
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
    
    # 防线二：新版本 vp_url.php Ajax 截胡 (已针对 2026 最新手势倒计时盾升级)
    elif "vp_url.php" in p_res.text or "VPID" in p_res.text:
        try:
            # 1. 严格剥离出 4 个核心核心验证参数（新增 VPT 抓取）
            vpid_m = re.search(r"VPID\s*=\s*['\"]([^'\"]+)['\"]", p_res.text) or re.search(r'data-id="(\d+)"', p_res.text)
            vpsid_m = re.search(r"VPSID\s*=\s*['\"]([^'\"]+)['\"]", p_res.text)
            vpnid_m = re.search(r"VPNID\s*=\s*['\"]([^'\"]+)['\"]", p_res.text)
            vpt_m = re.search(r"VPT\s*=\s*['\"]([^'\"]+)['\"]", p_res.text)  # 🎯 抓取隐藏的动态 Token
            
            if vpid_m:
                vpid = vpid_m.group(1)
                vpsid = vpsid_m.group(1) if vpsid_m else "1"
                vpnid = vpnid_m.group(1) if vpnid_m else "1"
                vpt = vpt_m.group(1) if vpt_m else ""
                
                ajax_headers = {
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": base_url.rstrip('/'), 
                    "Referer": play_link,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                
                # 2. 🎯 核心升级：欺骗后端。假装过了 6 秒倒计时，并生成随机的屏幕点击轨迹
                gx = random.randint(120, 380)       # 模拟点击 X 轴坐标
                gy = random.randint(450, 580)       # 模拟点击 Y 轴坐标
                dt = random.randint(6200, 7800)     # 模拟停留了 6 秒以上才点击的反应时间(毫秒)
                current_ts = int(time.time() * 1000)
                
                # 3. 完整组装最新的动态荷载数据
                post_data = {
                    "id": vpid, 
                    "sid": vpsid, 
                    "nid": vpnid, 
                    "tk": vpt,       # 💥 必须带上这个动态安全权杖
                    "g": "1", 
                    "x": str(gx), 
                    "y": str(gy), 
                    "dt": str(dt),   # 💥 物理过载倒计时
                    "sw": "1920", 
                    "sh": "1080", 
                    "tz": "-480", 
                    "t": str(current_ts)
                }
                
                api_res = session.post(f"{base_url.rstrip('/')}/vp_url.php", data=post_data, headers=ajax_headers, timeout=10)
                if api_res.status_code == 200:
                    res_json = api_res.json()
                    if res_json.get("ok") == 1 and "u" in res_json:
                        # 执行 Base64 解密脱壳
                        m3u8 = base64.b64decode(res_json["u"]).decode('utf-8')
        except: pass

    # 防线三：保底直接匹配
    if not m3u8:
        m3u8_match = re.search(r'https?[:\\\/]+[^"\']+\.m3u8[^"\']*', p_res.text, re.I)
        if m3u8_match: m3u8 = m3u8_match.group(0).replace('\\/', '/').replace('\\', '')

    if m3u8 and "%" in m3u8: 
        m3u8 = urllib.parse.unquote(m3u8)
        
    return m3u8
