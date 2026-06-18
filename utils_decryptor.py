# -*- coding: utf-8 -*-
import re
import json
import time
import base64
import urllib.parse

def decrypt_m3u8(p_res, play_link, base_url, session, has_crypto):
    """
    三道防线合一，专治各种加密战墙
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
    
    # 防线二：新版本 vp_url.php Ajax 截胡
    elif "vp_url.php" in p_res.text or "VPID" in p_res.text:
        try:
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

    if m3u8 and "%" in m3u8: 
        m3u8 = urllib.parse.unquote(m3u8)
        
    return m3u8
