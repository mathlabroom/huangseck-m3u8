# -*- coding: utf-8 -*-
import re
import json
import time
import base64
import random
import urllib.parse
from urllib.parse import urljoin

def decrypt_m3u8(p_res, play_link, base_url, session):
    """
    通用智能自适应解密算法 (专治各种变体手势倒计时盾)
    放弃硬编码，改用行为特征和动态流盲搜
    """
    m3u8 = ""
    html_text = p_res.text
    base_url_clean = base_url.rstrip('/')

    # =========================================================================
    # 策略一：行为特征盲搜 (智能破盾)
    # =========================================================================
    try:
        # 1. 智能探测 Ajax 计数/请求接口
        # 匹配诸如: /static/count.php, vp_url.php, /api/play.php 等
        api_path_match = re.search(r"['\"]([^'\"]+\.php)['\"]", html_text)
        if not api_path_match:
            # 备用探测：如果找不到.php，寻找 js 拼接的路径数组如 ['st','atic','/','count','.php']
            array_path = re.findall(r"['\"]([a-zA-Z0-9_\-/]+)['\"]", html_text)
            reconstructed = "".join([p for p in array_path if p in ['st', 'atic', '/', 'count', 'click', 'play', '.php', 'url']])
            api_url = urljoin(base_url_clean, reconstructed) if '.php' in reconstructed else None
        else:
            api_url = urljoin(base_url_clean, api_path_match.group(1))

        # 如果实在找不到接口路径，使用当前最频繁的几种默认变体保底
        if not api_url or api_url == base_url_clean:
            for fallback in ["/static/count.php", "/vp_url.php", "/static/play.php"]:
                if fallback.split('/')[-1] in html_text:
                    api_url = f"{base_url_clean}{fallback}"
                    break

        if api_url:
            # 2. 泛解析页面中所有可能的 16进制/高强度 Token 和 ID 数字
            # 提取所有 var XXX = 'xxxx' 形式的字符串
            string_vars = re.findall(r"(?:var|=)\s*[A-Z_0-9a-z]+\s*=\s*['\"]([^'\"]+)['\"]", html_text)
            # 提取所有类似于 ID 的数字 (1-7位)
            digit_vars = re.findall(r"(?:var|=|\b)\s*[A-Z_0-9a-z]+\s*=\s*['\"]?(\d{1,7})['\"]?", html_text)
            
            # 筛选出最像 Token 的长字符串（通常是 MD5 或长散列）
            potential_tokens = [v for v in string_vars if len(v) >= 32]
            # 筛选出最像当前播放 ID 的数字（通常页面里会重复出现多次）
            potential_ids = [v for v in digit_vars if v != "1" and v != "0"]
            
            # 智能提取关键权杖
            target_token = potential_tokens[0] if potential_tokens else ""
            target_id = potential_ids[0] if potential_ids else "0"
            
            # 如果从变量没捞到，尝试从 DOM 属性捞（比如 data-id="221520"）
            if target_id == "0":
                dom_id = re.search(r'data-id="(\d+)"', html_text)
                if dom_id: target_id = dom_id.group(1)

            # 3. 构造具有欺骗性的“智能全参数荷载”
            # 无论后端接收字段叫 id/sid/nid 还是 aid/asid/anid，我们把两套常用键名全部推过去！
            # 这样无论后端怎么改，总有一套键名能对上，富余的参数会被后端自动忽略。
            gx = str(random.randint(150, 360))
            gy = str(random.randint(420, 580))
            dt = str(random.randint(6200, 7600))
            current_ts = str(int(time.time() * 1000))
            
            post_data = {
                # 第一套键名变体 (新版)
                "id": target_id,
                "sid": "1",
                "nid": "1",
                "tk": target_token,
                # 第二套键名变体 (防止它两头堵)
                "aid": target_id,
                "asid": "1",
                "anid": "1",
                "ak": target_token,
                # 核心风控行为参数 (无论怎么改版，由于生物识别逻辑需要，这些键名绝不敢变)
                "g": "1",
                "x": gx,
                "y": gy,
                "dt": dt,
                "sw": "390",
                "sh": "844",
                "tz": "-480",
                "t": current_ts
            }

            ajax_headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": base_url_clean,
                "Referer": play_link,
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
            }

            # 发送请求
            api_res = session.post(api_url, data=post_data, headers=ajax_headers, timeout=10)
            if api_res.status_code == 200:
                # 判断返回的是 JSON 还是直接返回字符串
                try:
                    res_json = api_res.json()
                    # 动态探测加密串位置，不管叫 'u' 还是叫 'url' 或 'data'
                    encoded_str = ""
                    for key in ['u', 'url', 'data', 'video']:
                        if key in res_json:
                            encoded_str = res_json[key]
                            break
                    if encoded_str:
                        m3u8 = base64.b64decode(encoded_str).decode('utf-8')
                except:
                    # 如果返回的不是标准 JSON，而是直接返回了 Base64 字符串
                    if len(api_res.text) > 20 and not api_res.text.startswith("http"):
                        try: m3u8 = base64.b64decode(api_res.text).decode('utf-8')
                        except: pass
    except:
        pass

    # =========================================================================
    # 策略二：传统加解密保底 (Fernet 等)
    # =========================================================================
    if not m3u8 and "VPCFG" in html_text:
        try:
            cfg = re.search(r"VP[A-Z_]+\s*=\s*['\"]([^'\"]+)['\"]", html_text).findall()
            if len(cfg) >= 2:
                from cryptography.fernet import Fernet
                f_cipher = Fernet(cfg[1].encode('utf-8'))
                decrypted_data = f_cipher.decrypt(cfg[0].encode('utf-8')).decode('utf-8')
                m3u8 = json.loads(decrypted_data).get('url', '')
        except: pass

    # =========================================================================
    # 策略三：全页面暴力正则扫尾 (如果对方后端风控没开，只是前端吓唬人)
    # =========================================================================
    if not m3u8:
        m3u8_match = re.search(r'https?[:\\\/]+[^"\']+\.m3u8[^"\']*', html_text, re.I)
        if m3u8_match: 
            m3u8 = m3u8_match.group(0).replace('\\/', '/').replace('\\', '')

    if m3u8 and "%" in m3u8: 
        m3u8 = urllib.parse.unquote(m3u8)
        
    return m3u8
