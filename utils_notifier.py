# -*- coding: utf-8 -*-
import os
import requests
import subprocess

def send_wechat(title, content):
    """通过 Server酱 推送消息"""
    push_key = os.getenv("PUSH_KEY")
    if not push_key:
        print("⚠️ 未配置 PUSH_KEY，取消微信推送")
        return

    url = f"https://sctapi.ftqq.com/{push_key}.send"
    data = {"title": title, "desp": content}
    try:
        res = requests.post(url, data=data, timeout=10)
        if res.status_code == 200:
            print("🔔 微信通知发送成功")
    except Exception as e:
        print(f"❌ 微信通知发送失败: {e}")

def git_push_backup(count):
    """阶段性强制备份（带二进制冲突无脑覆盖策略，防止 Actions 挂掉）"""
    try:
        subprocess.run(["git", "config", "--local", "user.email", "action@github.com"], check=True)
        subprocess.run(["git", "config", "--local", "user.name", "GitHub Action"], check=True)
        subprocess.run(["git", "add", "."], check=True)
        msg = f"自动备份: 累计新增 {count} 条资源并同步配置"
        subprocess.run(["git", "commit", "-m", msg], check=False)
        
        print("🔄 正在同步远程仓库状态（如遇二进制冲突，将以本地最新数据为准）...")
        result = subprocess.run(["git", "pull", "origin", "main", "--rebase", "-X", "ours"], check=False)
        
        if result.returncode != 0:
            print("⚠️ 检测到强力冲突，执行强制覆盖策略...")
            subprocess.run(["git", "add", "."], check=False)
            subprocess.run(["git", "rebase", "--continue"], check=False)

        subprocess.run(["git", "push", "origin", "main"], check=True)
        print(f"🚀 [同步成功] 数据已推送至仓库")
    except Exception as e:
        print(f"⚠️ [同步跳过] 遇到冲突或网络问题: {e}")
        subprocess.run(["git", "rebase", "--abort"], check=False)
