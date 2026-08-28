# -*- coding: utf-8 -*-
import re
from bs4 import BeautifulSoup

def parse_page_items(html_text):
    soup = BeautifulSoup(html_text, 'html.parser')
    items = soup.find_all('li')
    
    # 特征检查：只要包含视频列表类名 stui-vodlist__box 或 pic-text 即可
    if not items or not any("pic-text" in str(li) for li in items):
        return None

    parsed_list = []
    for li in items:
        h4_title = li.find('h4', class_='title')
        if not h4_title: continue
        title_tag = h4_title.find('a')
        if not title_tag: continue
        
        title = (title_tag.get('title') or title_tag.get_text(strip=True)).strip()
        href = title_tag.get('href', '').strip()
        
        # 过滤无效/外部链接
        if href.startswith(('http://', 'https://', 'javascript', 'about:')): continue
        if any(x in href for x in ['index.php', 'channelCode']): continue
        
        # 【修改 1】移除硬编码的 tukaka.space 判断，使用更通用的封面提取 logic
        cover_url = ""
        img_tag = li.find('a', class_='lazyload') or li.find('img')
        if img_tag:
            cover_url = (img_tag.get('data-original') or img_tag.get('src') or img_tag.get('data-src') or "").strip()
        
        # 如果依旧没提取到，正则保底提取各类常见图片后缀
        if not cover_url:
            img_urls = re.findall(r'https?://[^\s"\']+\.(?:jpg|jpeg|png|webp|gif)', str(li), re.IGNORECASE)
            if img_urls: cover_url = img_urls[0]

        # 【修改 2】精准提取日期（排除点赞和播放量数字的干扰）
        date_val = "01-01"
        p_sub = li.find('p', class_='sub')
        if p_sub:
            # 仅获取 p 标签直接包含的文本节点（避开 span 内的浏览量和点赞数）
            direct_text = "".join(p_sub.find_all(string=True, recursive=False)).strip()
            date_match = re.search(r'\d{2}-\d{2}', direct_text)
            if date_match:
                date_val = date_match.group(0)
            else:
                # 保底逻辑：从整体文本最后尝试匹配
                sub_text = p_sub.get_text(" ", strip=True)
                date_matches = re.findall(r'(\d{2}-\d{2})', sub_text)
                if date_matches: date_val = date_matches[-1]

        parsed_list.append({
            "title": title, 
            "href": href, 
            "cover_url": cover_url, 
            "date_val": date_val
        })
        
    return parsed_list
