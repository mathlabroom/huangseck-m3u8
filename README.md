🎮 main.py（大总管）：只负责抓取主循环、处理 Ctrl + C 截断保护和收尾。

🌐 utils_crawler.py（网络尖兵）：只负责测活域名、拿 Session。

🕵️‍♂️ utils_parser.py（数据抓取）：负责解析页面、提取基础列表和日期刹车。

🔐 utils_decryptor.py（密码破译）：专注于三道 M3U8 墙的破解。

💾 utils_exporter.py（账房先生）：负责 M3U8/E2 落盘写入、去重。

📢 utils_notifier.py（传令官）：负责微信通知、Git 备份推送。
