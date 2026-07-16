# -*- coding: utf-8 -*-
# 🎯 支持 URL 日期精准倒序 + 自动生成 m3u8.gz + Enigma2 按月自动创建 Marks 分隔符完全体
import os
import re
import json
import gzip

def extract_date_from_url(url):
    """
    🎯 核心辅助：从 URL 中提取日期
    例如: https://t33.cdn2020.com/video/m3u8/2025/05/28/2f8a2c8b/index.m3u8
    提取出: '2025/05/28'，如果提取失败则返回空字符串
    """
    match = re.search(r'/m3u8/(\d{4}/\d{2}/\d{2})/', url)
    if match:
        return match.group(1)
    # 备用匹配：如果路径结构有变，直接抓取 8 位日期级联路径
    match_loose = re.search(r'/(\d{4}/\d{2}/\d{2})/', url)
    if match_loose:
        return match_loose.group(1)
    return ""

def convert_to_e2_bouquets(report_list=None):
    """
    🎯 Enigma2 专属：提取 M3U8 数据，按月份自动在 TV 列表中生成 Marks 分隔符 (修复 & 健壮重构版)
    """
    BASE_DIR = './VideoResults'
    OUTPUT_DIR = './E2_Bouquets'
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    CATEGORY_MAP = {
        "国产系列": "65", "骑兵破解": "66", "无码中文字幕": "67", "有码中文字幕": "68",
        "日本有码": "69", "日本无码": "6A", "欧美高清": "6B", "动漫": "6C"
    }

    report_dict = {r['name']: r.get('new', 0) for r in report_list if isinstance(r, dict)} if report_list else {}

    for cat_name, hex_id in CATEGORY_MAP.items():
        # 🎯 m3u8 直接在 VideoResults 目录下定位
        m3u8_path = os.path.join(BASE_DIR, f"{cat_name}.m3u8")
        tv_path = os.path.join(OUTPUT_DIR, f"subbouquet.{cat_name}.tv")
        gz_path = tv_path + '.gz'
        
        if not os.path.exists(m3u8_path): 
            continue
        
        # 🎯 【精准拦截】如果该分类今日更新数为 0，且本地已有打包好的 .tv.gz，直接跳过
        if report_dict.get(cat_name, 0) == 0 and os.path.exists(gz_path):
            print(f"      ℹ️ 分类【{cat_name}】今日无新增，完美跳过 E2 转换与打包。")
            continue

        print(f"      🗜️ 分类【{cat_name}】探测到新资源，正在按月划定 Marks 并重新打包...")
        
        # 解析出所有的有效节目条目
        parsed_items = []
        try:
            with open(m3u8_path, 'r', encoding='utf-8', errors='ignore') as f:
                current_title = "未命名频道"
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#EXTM3U"):
                        continue
                    
                    if line.startswith("#EXTINF:"):
                        # 提取频道名称（逗号后面的内容）
                        parts = line.split(",", 1)
                        if len(parts) > 1:
                            current_title = parts[1].strip()
                    elif line.startswith("http"):
                        url = line
                        date_str = extract_date_from_url(url)  # 提取 '2025/05/28'
                        # 提取年-月作为分组标记
                        month_group = date_str[:7].replace('/', '-') if len(date_str) >= 7 else "其他时间"
                        parsed_items.append({
                            "title": current_title,
                            "url": url,
                            "month": month_group
                        })
                        current_title = "未命名频道"  # 重置状态
        except Exception as e:
            print(f"      ❌ 读取/解析 M3U8 失败: {e}")
            continue
        
        # 💡 生成 Enigma2 TV 列表（由于 M3U8 已在 save_and_update 里排好序，此处直接按序遍历即可）
        output_lines = [f"#NAME {cat_name}"]
        current_active_month = None
        sid = 1
        
        for p_item in parsed_items:
            # 🎯 检查月份是否发生变化，如果变了，立马打一个月份 Marker
            if p_item["month"] != current_active_month:
                current_active_month = p_item["month"]
                # Enigma2 标准 Marker 格式: #SERVICE 1:64:序号:0:0:0:0:0:0:0::--- 标题 ---
                marker_text = f"====== 【 {current_active_month} 】 ======"
                output_lines.append(f"#SERVICE 1:64:{sid}:0:0:0:0:0:0:0::{marker_text}")
                output_lines.append(f"#DESCRIPTION {marker_text}")
                sid += 1
            
            # 🎯 插入正常的直播源频道，完美转义 URL 冒号（统一小写转义，防止部分机顶盒报错）
            h_sid = hex(sid)[2:].upper().zfill(4)
            safe_url = p_item["url"].replace(':', '%3a').replace('%3A', '%3a')
            
            # 服务引用格式：服务类型(4097):0:服务组ID(1):频道自增ID(h_sid):子分类组ID(0):0:大分类ID(hex_id):0:0:0:转义URL:频道名
            output_lines.append(f"#SERVICE 4097:0:1:{h_sid}:0:0:{hex_id}:0:0:0:{safe_url}:{p_item['title']}")
            output_lines.append(f"#DESCRIPTION {p_item['title']}")
            sid += 1
        
        # 写入 .tv 文件并打包为 .tv.gz
        try:
            with open(tv_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(output_lines) + "\n")
                
            with open(tv_path, 'rb') as f_in:
                with gzip.open(gz_path, 'wb', compresslevel=9) as f_out:
                    f_out.writelines(f_in)
                    
            print(f"      ✅ 分类【{cat_name}】转换成功，Marks 注入完毕，.tv.gz 压缩包已更新。")
        except Exception as e:
            print(f"      ❌ 分类【{cat_name}】保存或压缩失败: {e}")
