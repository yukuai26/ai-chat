#!/bin/bash
# stock 卡片定时刷新脚本
# 用法: refresh-stock.sh [quote|full|comment]
#   quote   = 只刷实时行情(用K线缓存,盘中高频)
#   full    = 抓全量K线+算指标(收盘后每天一次, 加 --refresh-kline)
#   comment = 先 full 刷一次拿最新指标，再调 card-assistant(卡片喵)写 AI 点评(早晚各一次)
MODE="${1:-quote}"
CARD_DIR="/home/ubuntu/.openclaw/user-data/daily-data/stock"
LOG="/home/ubuntu/.openclaw/logs/stock-refresh.log"
mkdir -p "$(dirname "$LOG")"
cd "$CARD_DIR" || exit 1

TS="$(date '+%Y-%m-%d %H:%M:%S')"

if [ "$MODE" = "full" ]; then
  echo "[$TS] full refresh (--refresh-kline)" >> "$LOG"
  python3 generate-display.py --refresh-kline >> "$LOG" 2>&1

elif [ "$MODE" = "comment" ]; then
  # 1) 先 full 刷新拿最新 K线+指标(不通知前端，等点评写完一起刷)
  echo "[$TS] comment: full refresh first" >> "$LOG"
  python3 generate-display.py --refresh-kline --no-notify >> "$LOG" 2>&1
  # 2) 调卡片喵(card-assistant)按最新指标写 AI 点评，写回 data.json + 刷 display + 通知前端
  echo "[$(date '+%H:%M:%S')] comment: invoking card-assistant" >> "$LOG"
  timeout 300 openclaw agent --agent card-assistant --timeout 280 \
    --message "【定时任务·股票点评】请给 stock 卡片(${CARD_DIR}/)的全部自选股写 AI 点评：1) 读 data.json 的 quotes+klines 和 prompt.json 的 ai_comment_prompt；2) 给 watchlist 每支股票按 prompt 写 2-4 句大白话点评(客观中性、提示风险、不荐股不预测)；3) 写回 data.json 的 ai_comment[code]={text,ts}；4) 跑 python3 generate-display.py --no-notify 刷 display；5) curl 通知前端 card=stock。完成后简要回复改了哪几支。" \
    >> "$LOG" 2>&1
  echo "[$(date '+%H:%M:%S')] comment: card-assistant done" >> "$LOG"

else
  echo "[$TS] quote refresh" >> "$LOG"
  python3 generate-display.py >> "$LOG" 2>&1
fi

echo "[$(date '+%H:%M:%S')] done" >> "$LOG"
