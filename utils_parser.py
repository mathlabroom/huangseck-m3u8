# -*- coding: utf-8 -*-
import re
import urllib.parse
from bs4 import BeautifulSoup

def parse_page_items(html_text):
    """
    负责把一整页的 HTML 啃掉，吐出里面所有的视频条目生肉
    """
    soup = BeautifulSoup(html_text, 'html.parser')
    items = soup.find_all('li')
    
    # 特征检查
    if not items or not any("tutu1.space" in str(li) for li in items):
        return None  # 空页或者广告垃圾页

    parsed_list = []
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

        # 提取封面
        cover_url = ""
        img_tag = li.find(['img', 'a'], class_='lazyload') or li.find('img')
        if img_tag:
            cover_url = (img_tag.get('data-original') or img_tag.get('src') or img_tag.get('data-src') or "")
        if not cover_url or "tutu1.space" not in cover_url:
            img_urls = re.findall(r'(https?://[^\s"\']+tutu1\.space[^\s"\']+)', str(li))
            if img_urls: cover_url = img_urls[0]

        # 提取日期
        date_val = "01-01"
        p_sub = li.find('p', class_='sub')
        if p_sub:
            sub_text = p_sub.get_text(" ", strip=True)
            date_matches = re.findall(r'(\d{2}-\d{2})', sub_text)
            if date_matches: date_val = date_matches[-1]

        parsed_list.append({
            "title": title, "href": href, "cover_url": cover_url, "date_val": date_val
        })
        
    return parsed_list
