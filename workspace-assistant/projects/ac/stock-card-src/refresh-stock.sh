#!/bin/bash
# stock 卡片定时刷新脚本
# 用法: refresh-stock.sh [quote|full]
#   quote = 只刷实时行情(用K线缓存,盘中高频)
#   full  = 抓全量K线+算指标(收盘后每天一次, 加 --refresh-kline)
MODE="${1:-quote}"
CARD_DIR="/home/ubuntu/.openclaw/user-data/daily-data/stock"
LOG="/home/ubuntu/.openclaw/logs/stock-refresh.log"
mkdir -p "$(dirname "$LOG")"
cd "$CARD_DIR" || exit 1

TS="$(date '+%Y-%m-%d %H:%M:%S')"
if [ "$MODE" = "full" ]; then
  echo "[$TS] full refresh (--refresh-kline)" >> "$LOG"
  python3 generate-display.py --refresh-kline >> "$LOG" 2>&1
else
  echo "[$TS] quote refresh" >> "$LOG"
  python3 generate-display.py >> "$LOG" 2>&1
fi
echo "[$(date '+%H:%M:%S')] done" >> "$LOG"
