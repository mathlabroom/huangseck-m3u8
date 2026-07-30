# -*- coding: utf-8 -*-
import re
import json
import os
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def get_valid_base_url():
    """智能探路者：不再记忆旧域名，每次均直接通过发布页追踪获取最新域名"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    anchor_host = "http://hsck.us" 
    
    print("⚠️ 启动智能追踪器，直接从发布页搜寻最新入口...")
    try:
        print(f"📡 正在请求永久发布页: {anchor_host}")
        req_res = requests.get(anchor_host, headers=headers, timeout=10, verify=False)
        html = req_res.text
        soup = BeautifulSoup(html, "lxml" if "lxml" in html else "html.parser")

        # 1. 尝试匹配动态跳转接口
        if "strU=" in html and soup.find(id="hao123"):
            match = re.search(r'strU="(https?://[a-zA-Z0-9:/.]+\?u=?)"', html)
            if match:
                redirect_url = f"{match.group(1)}{anchor_host}/&p=/"
                print(f"🔗 捕获到动态跳转接口: {redirect_url}，正在追踪最终归宿...")
                track_res = requests.head(redirect_url, headers=headers, timeout=8, verify=False, allow_redirects=False)
                location = track_res.headers.get("Location")
                if location:
                    loc_match = re.match(r"(https?://[a-zA-Z0-9][-a-zA-Z0-9]{0,62}(\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+)", location)
                    if loc_match:
                        discovered_url = loc_match.group(1)
                        print(f"🚀 [追踪成功] 通过重定向接口捕获到最新官网: {discovered_url}")
                        return discovered_url

        # 2. 如果发布页自身就已经展示了官网内容
        if len(html) > 20000 and soup.find(class_="stui-warp-content"):
            print(f"🚀 [寻路成功] 发布页本身已展现官网特征，直接采用: {anchor_host}")
            return anchor_host
    except Exception as tracker_err:
        print(f"❌ 智能寻路系统发生故障: {tracker_err}")

    print("⚠️ 寻路系统未能探明新域名，后备退回发布页根域名。")
    return anchor_host

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

def get_stable_session(base_url):
    """构建健壮的网络请求 Session"""
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": base_url
    })
    return session
