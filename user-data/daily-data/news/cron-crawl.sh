#!/bin/bash
# 新闻卡片定时抓取 — ac-news-card-design-V1.0 (08/12/18/22)
LOG=/home/ubuntu/.openclaw/user-data/daily-data/news/crawl.log
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 开始抓取 =====" >> "$LOG"
/usr/bin/python3 /home/ubuntu/.openclaw/user-data/daily-data/news/crawl.py >> "$LOG" 2>&1
echo "" >> "$LOG"
