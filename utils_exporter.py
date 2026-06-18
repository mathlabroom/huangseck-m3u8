# -*- coding: utf-8 -*-
import os
import re
import json
import gzip

def save_and_update(path, new_lines, db_list, db_path):
    """M3U8 倒序去重更新，并写入 JSON 数据库"""
    items_dict = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            blocks = re.findall(r'(#EXTINF:.*?)(?=#EXTINF:|$)', content, re.S)
            for block in blocks:
                clean_block = block.strip()
                if clean_block:
                    title_line = clean_block.split('\n')[0].strip()
                    items_dict[title_line] = clean_block

    for item in new_lines:
        item = item.strip()
        if item:
            title_line = item.split('\n')[0].strip()
            items_dict[title_line] = item

    sorted_keys = sorted(items_dict.keys(), reverse=True) 

    with open(path, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for k in sorted_keys:
            f.write(items_dict[k] + "\n")
    
    with open(db_path, 'w', encoding='utf-8') as f:
        json.dump(db_list, f, ensure_ascii=False, indent=4)

def convert_to_e2_bouquets(report_list=None):
    """Enigma2 适用的 Bouquet 精准按需打包"""
    BASE_DIR = './VideoResults'
    OUTPUT_DIR = './E2_Bouquets'
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    CATEGORY_MAP = {
        "国产系列": "65", "骑兵破解": "66", "无码中文字幕": "67", "有码中文字幕": "68",
        "日本有码": "69", "日本无码": "6A", "欧美高清": "6B", "动漫": "6C"
    }

    report_dict = {r['name']: r.get('new', 0) for r in report_list if isinstance(r, dict)} if report_list else {}

    for cat_name, hex_id in CATEGORY_MAP.items():
        m3u8_path = os.path.join(BASE_DIR, cat_name, f"{cat_name}.m3u8")
        tv_path = os.path.join(OUTPUT_DIR, f"subbouquet.{cat_name}.tv")
        gz_path = tv_path + '.gz'
        
        if not os.path.exists(m3u8_path): continue
        
        if report_dict.get(cat_name, 0) == 0 and os.path.exists(gz_path):
            print(f"      ℹ️ 分类【{cat_name}】今日无新增，完美跳过 E2 转换与打包。")
            continue

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
        
        with open(tv_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(output_lines) + "\n")
            
        with open(tv_path, 'rb') as f_in:
            with gzip.open(gz_path, 'wb') as f_out:
                f_out.writelines(f_in)
